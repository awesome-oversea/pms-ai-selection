from __future__ import annotations

from typing import Any

from src.infrastructure.feature_engine import FeatureEngine


class FeatureAssetService:
    def __init__(self, engine: FeatureEngine | None = None) -> None:
        self.engine = engine or FeatureEngine()

    @staticmethod
    def _normalize_feature_payload(product_id: str, features: dict[str, Any]) -> dict[str, Any]:
        payload = dict(features)
        payload.setdefault("product_id", product_id)
        payload["review_sentiment_score"] = payload.get("review_sentiment")
        payload["price_volatility"] = payload.get("price_std_30d")
        payload["feature_asset"] = {
            "product_id": payload.get("product_id", product_id),
            "sales_growth_rate_7d": payload.get("sales_growth_rate_7d"),
            "review_sentiment_score": payload.get("review_sentiment_score"),
            "price_volatility": payload.get("price_volatility"),
            "rank_current": payload.get("rank_current"),
            "market_share_estimate": payload.get("market_share_estimate"),
            "updated_at": payload.get("updated_at"),
        }
        return payload

    async def ingest_event(self, event: dict[str, Any]) -> dict[str, Any]:
        result = await self.engine.process_event(event)
        product_id = str(result.get("product_id") or event.get("product_id") or "")
        features = result.get("features") if isinstance(result.get("features"), dict) else {}
        normalized = self._normalize_feature_payload(product_id, features)
        return {
            **result,
            "features": normalized,
            "feature_asset": normalized.get("feature_asset"),
        }

    async def get_feature(self, product_id: str) -> dict[str, Any] | None:
        features = await self.engine.get_features(product_id)
        if features is None:
            return None
        return self._normalize_feature_payload(product_id, features)

    async def get_features_batch(self, product_ids: list[str]) -> dict[str, dict[str, Any]]:
        raw = await self.engine.get_features_batch(product_ids)
        return {
            product_id: self._normalize_feature_payload(product_id, features)
            for product_id, features in raw.items()
        }

    def get_feature_history(self, product_id: str, limit: int = 20) -> list[dict[str, Any]]:
        history = self.engine.get_feature_history(product_id, limit=limit)
        results: list[dict[str, Any]] = []
        for item in history:
            inserted_at = item.get("inserted_at")
            features = item.get("features") if isinstance(item.get("features"), dict) else {}
            normalized = self._normalize_feature_payload(product_id, features)
            results.append({
                "inserted_at": inserted_at,
                "features": normalized,
                "feature_asset": normalized.get("feature_asset"),
            })
        return results

    def get_status(self) -> dict[str, Any]:
        stats = self.engine.get_stats()
        snapshot_store = stats.get("snapshot_store") if isinstance(stats.get("snapshot_store"), dict) else {}
        return {
            "feature_store": {
                "engine": "local_feature_engine",
                "query_mode": "formal_api",
                "snapshot_count": snapshot_store.get("snapshot_count", 0),
                "history_count": snapshot_store.get("history_count", 0),
                "db_path": snapshot_store.get("db_path"),
                "cache_hit_rate": stats.get("cache_hit_rate", 0.0),
                "events_processed": stats.get("events_processed", 0),
                "features_computed": stats.get("features_computed", 0),
            },
            "feature_keys": [
                "sales_7d",
                "sales_30d",
                "sales_growth_rate_7d",
                "avg_price_30d",
                "price_volatility",
                "rank_current",
                "rank_change_7d",
                "review_sentiment_score",
                "review_count_30d",
                "market_share_estimate",
            ],
            "platform_ready": bool(snapshot_store.get("db_path")),
        }
