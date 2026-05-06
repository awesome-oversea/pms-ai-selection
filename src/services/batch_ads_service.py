from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BATCH_ADS_DB_PATH = Path("data/local_batch_ads.db")


class LocalBatchAdsStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or _BATCH_ADS_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ads_selection_daily_features (
                    product_id TEXT PRIMARY KEY,
                    features_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ads_selection_daily_features_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    features_json TEXT NOT NULL,
                    executed_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ads_selection_overview (
                    overview_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def upsert_feature_row(self, product_id: str, features: dict[str, Any], *, executed_at: str | None = None) -> None:
        payload = json.dumps(features, ensure_ascii=False)
        now = executed_at or self._now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ads_selection_daily_features (product_id, features_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    features_json = excluded.features_json,
                    updated_at = excluded.updated_at
                """,
                (product_id, payload, now),
            )
            conn.execute(
                "INSERT INTO ads_selection_daily_features_history (product_id, features_json, executed_at) VALUES (?, ?, ?)",
                (product_id, payload, now),
            )

    def upsert_overview(self, payload: dict[str, Any], *, overview_key: str = "selection_overview_ads", updated_at: str | None = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False)
        now = updated_at or self._now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ads_selection_overview (overview_key, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(overview_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (overview_key, raw, now),
            )

    def get_feature_row(self, product_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT features_json, updated_at FROM ads_selection_daily_features WHERE product_id = ?",
                (product_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["features_json"])
        if isinstance(payload, dict):
            payload.setdefault("updated_at", row["updated_at"])
        return payload

    def list_feature_rows(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT features_json, updated_at FROM ads_selection_daily_features ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["features_json"])
            if isinstance(payload, dict):
                payload.setdefault("updated_at", row["updated_at"])
                results.append(payload)
        return results

    def get_feature_history(self, product_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT features_json, executed_at FROM ads_selection_daily_features_history WHERE product_id = ? ORDER BY id DESC LIMIT ?",
                (product_id, limit),
            ).fetchall()
        return [
            {
                "executed_at": row["executed_at"],
                "features": json.loads(row["features_json"]),
            }
            for row in rows
        ]

    def get_overview(self, overview_key: str = "selection_overview_ads") -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, updated_at FROM ads_selection_overview WHERE overview_key = ?",
                (overview_key,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        if isinstance(payload, dict):
            payload.setdefault("updated_at", row["updated_at"])
        return payload

    def get_stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            feature_count = conn.execute("SELECT COUNT(*) FROM ads_selection_daily_features").fetchone()[0]
            history_count = conn.execute("SELECT COUNT(*) FROM ads_selection_daily_features_history").fetchone()[0]
            overview_count = conn.execute("SELECT COUNT(*) FROM ads_selection_overview").fetchone()[0]
        return {
            "db_path": str(self.db_path),
            "feature_row_count": int(feature_count),
            "history_count": int(history_count),
            "overview_count": int(overview_count),
        }


class BatchAdsService:
    def __init__(self, store: LocalBatchAdsStore | None = None) -> None:
        self.store = store or LocalBatchAdsStore()

    def build_status(self) -> dict[str, Any]:
        stats = self.store.get_stats()
        return {
            "engine": "spark-compatible-local-ads",
            "storage": "sqlite-local-ads",
            "db_path": stats.get("db_path"),
            "feature_row_count": stats.get("feature_row_count", 0),
            "history_count": stats.get("history_count", 0),
            "overview_count": stats.get("overview_count", 0),
            "platform_ready": bool(stats.get("db_path")),
        }

    def get_latest_features(self, limit: int = 50) -> dict[str, Any]:
        items = self.store.list_feature_rows(limit=limit)
        return {
            "total": len(items),
            "items": items,
        }

    def get_feature(self, product_id: str) -> dict[str, Any] | None:
        return self.store.get_feature_row(product_id)

    def get_feature_history(self, product_id: str, limit: int = 20) -> dict[str, Any]:
        items = self.store.get_feature_history(product_id, limit=limit)
        return {
            "product_id": product_id,
            "total": len(items),
            "items": items,
        }

    def get_selection_overview_ads(self) -> dict[str, Any] | None:
        return self.store.get_overview()
