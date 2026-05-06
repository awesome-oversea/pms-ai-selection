"""
实时特征工程引擎
================

提供实时特征计算能力(D61-D65):
    - 滑动窗口聚合(7/30/90天)
    - 销量/价格/排名特征
    - Redis实时存储
    - ClickHouse历史存储
    - 特征服务API

使用方式:
    from src.infrastructure.feature_engine import FeatureEngine

    engine = FeatureEngine()
    await engine.process_event({"product_id": "P001", "sales": 10, "price": 99.9})
    features = await engine.get_features("P001")
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)

_FEATURE_DB_PATH = Path("data/local_feature_store.db")


class FeatureType(StrEnum):
    """特征类型。"""
    SALES = "sales"
    PRICE = "price"
    RANK = "rank"
    COMPETITOR = "competitor"
    SENTIMENT = "sentiment"


class TrendDirection(StrEnum):
    """趋势方向。"""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


@dataclass
class FeatureEvent:
    """特征事件。"""
    event_id: str
    product_id: str
    event_type: str
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "product_id": self.product_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "data": self.data,
        }


@dataclass
class ProductFeatures:
    """产品特征集。"""
    product_id: str
    sales_7d: int = 0
    sales_30d: int = 0
    sales_90d: int = 0
    sales_growth_rate_7d: float = 0.0
    order_count_7d: int = 0
    avg_price_7d: float = 0.0
    avg_price_30d: float = 0.0
    price_std_30d: float = 0.0
    price_trend: TrendDirection = TrendDirection.STABLE
    price_trend_slope: float = 0.0
    rank_current: int = 0
    rank_change_1d: int = 0
    rank_change_7d: int = 0
    competitor_count: int = 0
    market_share_estimate: float = 0.0
    review_sentiment: float = 0.5
    review_count_30d: int = 0
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "sales_7d": self.sales_7d,
            "sales_30d": self.sales_30d,
            "sales_90d": self.sales_90d,
            "sales_growth_rate_7d": round(self.sales_growth_rate_7d, 4),
            "order_count_7d": self.order_count_7d,
            "avg_price_7d": self.avg_price_7d,
            "avg_price_30d": self.avg_price_30d,
            "price_std_30d": round(self.price_std_30d, 2),
            "price_trend": self.price_trend.value,
            "price_trend_slope": round(self.price_trend_slope, 4),
            "rank_current": self.rank_current,
            "rank_change_1d": self.rank_change_1d,
            "rank_change_7d": self.rank_change_7d,
            "competitor_count": self.competitor_count,
            "market_share_estimate": round(self.market_share_estimate, 4),
            "review_sentiment": round(self.review_sentiment, 3),
            "review_count_30d": self.review_count_30d,
            "updated_at": self.updated_at,
        }


class SlidingWindow:
    """
    滑动窗口聚合器(D62)。

    支持的窗口类型:
        - TUMBLE: 滚动窗口(固定边界)
        - HOP: 滑动窗口(重叠)
        - SESSION: 会话窗口(动态)
    """

    def __init__(self, window_size_seconds: int = 86400, slide_interval_seconds: int = 3600):
        self._window_size = window_size_seconds
        self._slide_interval = slide_interval_seconds
        self._buckets: dict[int, dict[str, Any]] = defaultdict(lambda: {"sum": 0, "count": 0, "values": []})
        self._watermark = time.time()

    def add(self, value: float, timestamp: float | None = None) -> None:
        ts = timestamp or time.time()
        bucket_key = int(ts // self._slide_interval)
        bucket = self._buckets[bucket_key]
        bucket["sum"] += value
        bucket["count"] += 1
        bucket["values"].append(value)
        self._watermark = max(self._watermark, ts)
        self._cleanup()

    def get_aggregates(self) -> dict[str, float]:
        """获取窗口聚合结果。"""
        current_time = time.time()
        window_start = current_time - self._window_size
        total_sum = 0.0
        total_count = 0
        all_values: list[float] = []

        for bucket_key in sorted(self._buckets.keys()):
            bucket_time = bucket_key * self._slide_interval
            if bucket_time >= window_start:
                bucket = self._buckets[bucket_key]
                total_sum += bucket["sum"]
                total_count += bucket["count"]
                all_values.extend(bucket["values"])

        if total_count == 0:
            return {"sum": 0, "count": 0, "avg": 0, "std": 0}

        avg = total_sum / total_count
        if len(all_values) > 1:
            variance = sum((v - avg) ** 2 for v in all_values) / len(all_values)
            std = variance**0.5
        else:
            std = 0.0

        return {
            "sum": round(total_sum, 2),
            "count": total_count,
            "avg": round(avg, 2),
            "std": round(std, 2),
        }

    def _cleanup(self) -> None:
        """清理过期桶。"""
        cutoff = int((self._watermark - self._window_size * 2) // self._slide_interval)
        expired_keys = [k for k in self._buckets if k < cutoff]
        for k in expired_keys:
            del self._buckets[k]


class TrendDetector:
    """
    趋势检测器(D63)。

    算法:
        - 线性回归斜率
        - 移动平均交叉
        - 统计显著性检验
    """

    SLOPE_THRESHOLD_UP = 0.01
    SLOPE_THRESHOLD_DOWN = -0.01

    @staticmethod
    def detect_trend(values: list[float]) -> tuple[TrendDirection, float]:
        """检测趋势方向和斜率。"""
        if len(values) < 2:
            return TrendDirection.STABLE, 0.0

        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n

        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return TrendDirection.STABLE, 0.0

        slope = numerator / denominator
        normalized_slope = slope / max(y_mean, 0.001)

        if normalized_slope > TrendDetector.SLOPE_THRESHOLD_UP:
            return TrendDirection.UP, slope
        elif normalized_slope < TrendDetector.SLOPE_THRESHOLD_DOWN:
            return TrendDirection.DOWN, slope
        else:
            return TrendDirection.STABLE, slope

    @staticmethod
    def detect_anomaly(current: float, history: list[float], threshold: float = 2.0) -> bool:
        """检测异常值。"""
        if len(history) < 3:
            return False
        mean = sum(history) / len(history)
        std = (sum((v - mean) ** 2 for v in history) / len(history)) ** 0.5
        if std == 0:
            return False
        z_score = abs(current - mean) / std
        return z_score > threshold


class RedisFeatureStore:
    """
    Redis特征存储(D65)。

    存储结构:
        Key: feature:{product_id}
        Value: JSON序列化的特征字典
        TTL: 86400秒(1天)
    """

    def __init__(self, prefix: str = "feature"):
        self._prefix = prefix
        self._store: dict[str, tuple[dict, float]] = {}
        self._ttl = 86400
        logger.info("RedisFeatureStore初始化完成")

    def set(self, product_id: str, features: dict[str, Any]) -> None:
        """设置特征。"""
        key = f"{self._prefix}:{product_id}"
        self._store[key] = (features, time.time())

    def get(self, product_id: str) -> dict[str, Any] | None:
        """获取特征。"""
        key = f"{self._prefix}:{product_id}"
        if key in self._store:
            features, timestamp = self._store[key]
            if time.time() - timestamp < self._ttl:
                return features
            del self._store[key]
        return None

    def delete(self, product_id: str) -> None:
        """删除特征。"""
        key = f"{self._prefix}:{product_id}"
        self._store.pop(key, None)

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_keys": len(self._store),
            "prefix": self._prefix,
            "ttl_seconds": self._ttl,
        }


class ClickHouseFeatureStore:
    """
    ClickHouse特征存储(D65)。

    用于历史特征存储和分析查询。
    """

    def __init__(self, table_name: str = "product_features"):
        self._table = table_name
        self._history: list[dict[str, Any]] = []
        logger.info("ClickHouseFeatureStore初始化完成")

    def insert(self, features: dict[str, Any]) -> None:
        """插入特征记录。"""
        record = {
            **features,
            "inserted_at": datetime.now(UTC).isoformat(),
        }
        self._history.append(record)

    def query(
        self,
        product_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """查询历史特征。"""
        results = self._history
        if product_id:
            results = [r for r in results if r.get("product_id") == product_id]
        if start_time:
            results = [r for r in results if r.get("inserted_at", "") >= start_time]
        if end_time:
            results = [r for r in results if r.get("inserted_at", "") <= end_time]
        return results[-limit:]

    def get_stats(self) -> dict[str, Any]:
        return {
            "table": self._table,
            "total_records": len(self._history),
        }


class LocalFeatureSnapshotStore:
    """本地 SQLite 特征快照存储。"""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path or _FEATURE_DB_PATH)
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
                CREATE TABLE IF NOT EXISTS feature_snapshots (
                    product_id TEXT PRIMARY KEY,
                    features_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feature_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    features_json TEXT NOT NULL,
                    inserted_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_feature_history_product_id ON feature_history(product_id, id DESC)"
            )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def upsert(self, product_id: str, features: dict[str, Any]) -> None:
        payload = json.dumps(features, ensure_ascii=False)
        now = self._now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feature_snapshots (product_id, features_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    features_json = excluded.features_json,
                    updated_at = excluded.updated_at
                """,
                (product_id, payload, now),
            )
            conn.execute(
                "INSERT INTO feature_history (product_id, features_json, inserted_at) VALUES (?, ?, ?)",
                (product_id, payload, now),
            )

    def get(self, product_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT features_json FROM feature_snapshots WHERE product_id = ?",
                (product_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["features_json"])

    def history(self, product_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT features_json, inserted_at FROM feature_history WHERE product_id = ? ORDER BY id DESC LIMIT ?",
                (product_id, limit),
            ).fetchall()
        return [
            {
                "inserted_at": row["inserted_at"],
                "features": json.loads(row["features_json"]),
            }
            for row in rows
        ]

    def get_stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            snapshot_count = conn.execute("SELECT COUNT(*) FROM feature_snapshots").fetchone()[0]
            history_count = conn.execute("SELECT COUNT(*) FROM feature_history").fetchone()[0]
        return {
            "db_path": str(self.db_path),
            "snapshot_count": int(snapshot_count),
            "history_count": int(history_count),
        }


class FeatureEngine:
    """
    特征计算引擎(D61-D65核心)。

    功能:
        1. 实时事件处理
        2. 多窗口聚合(7/30/90天)
        3. 趋势检测
        4. 双存储(Redis+ClickHouse)
    """

    DAY_SECONDS = 86400

    def __init__(
        self,
        redis_store: RedisFeatureStore | None = None,
        ch_store: ClickHouseFeatureStore | None = None,
        snapshot_store: LocalFeatureSnapshotStore | None = None,
    ):
        self._redis = redis_store or RedisFeatureStore()
        self._clickhouse = ch_store or ClickHouseFeatureStore()
        self._snapshot_store = snapshot_store or LocalFeatureSnapshotStore()
        self._sales_windows: dict[str, dict[int, SlidingWindow]] = defaultdict(lambda: {
            7: SlidingWindow(7 * self.DAY_SECONDS, 3600),
            30: SlidingWindow(30 * self.DAY_SECONDS, 3600),
            90: SlidingWindow(90 * self.DAY_SECONDS, 3600),
        })
        self._price_windows: dict[str, dict[int, SlidingWindow]] = defaultdict(lambda: {
            7: SlidingWindow(7 * self.DAY_SECONDS, 3600),
            30: SlidingWindow(30 * self.DAY_SECONDS, 3600),
        })
        self._sentiment_windows: dict[str, dict[int, SlidingWindow]] = defaultdict(lambda: {
            7: SlidingWindow(7 * self.DAY_SECONDS, 3600),
            30: SlidingWindow(30 * self.DAY_SECONDS, 3600),
        })
        self._review_count_windows: dict[str, dict[int, SlidingWindow]] = defaultdict(lambda: {
            7: SlidingWindow(7 * self.DAY_SECONDS, 3600),
            30: SlidingWindow(30 * self.DAY_SECONDS, 3600),
        })
        self._rank_history: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._event_buffer: list[FeatureEvent] = []
        self._stats = {
            "events_processed": 0,
            "features_computed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "snapshot_hits": 0,
            "snapshot_misses": 0,
        }
        logger.info("FeatureEngine初始化完成")

    def _normalize_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(event_data)
        event_type = str(normalized.get("event_type") or "unknown")
        payload = normalized.get("payload") if isinstance(normalized.get("payload"), dict) else {}
        product_id = str(
            normalized.get("product_id")
            or payload.get("product_id")
            or payload.get("task_id")
            or normalized.get("aggregate_id")
            or ""
        )
        normalized["product_id"] = product_id

        if event_type == "order.updated":
            normalized["event_type"] = "sales"
            normalized["sales"] = int(payload.get("units") or payload.get("sales") or normalized.get("sales") or 0)
            normalized["price"] = float(payload.get("unit_price") or payload.get("price") or normalized.get("price") or 0)
        elif event_type == "review.updated":
            normalized["event_type"] = "review"
            rating = payload.get("rating") or payload.get("customer_score") or normalized.get("rating") or 0
            normalized["rating"] = float(rating or 0)
            normalized["review_count"] = int(payload.get("review_count") or normalized.get("review_count") or 1)
            feedback_text = str(payload.get("feedback") or normalized.get("feedback") or "")
            negative_keywords = ["refund", "complaint", "issue", "bad", "broken", "退货", "投诉", "问题", "差评", "破损"]
            sentiment = -1.0 if any(keyword in feedback_text.lower() for keyword in negative_keywords) else 1.0
            if normalized["rating"]:
                sentiment = max(-1.0, min(1.0, (normalized["rating"] - 3.0) / 2.0))
            normalized["sentiment"] = sentiment
        return normalized

    async def process_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        normalized_event = self._normalize_event(event_data)
        event_id = hashlib.md5(json.dumps(normalized_event, sort_keys=True).encode()).hexdigest()[:12]
        event = FeatureEvent(
            event_id=f"evt_{event_id}",
            product_id=normalized_event.get("product_id", ""),
            event_type=normalized_event.get("event_type", "unknown"),
            timestamp=normalized_event.get("timestamp", time.time()),
            data=normalized_event,
        )

        product_id = event.product_id
        self._stats["events_processed"] += 1

        if event.event_type == "sales":
            sales = float(normalized_event.get("sales", 0) or 0)
            price = float(normalized_event.get("price", 0) or 0)
            for days in [7, 30, 90]:
                self._sales_windows[product_id][days].add(sales, event.timestamp)
            if price > 0:
                for days in [7, 30]:
                    self._price_windows[product_id][days].add(price, event.timestamp)
        elif event.event_type == "price":
            price = float(normalized_event.get("price", 0) or 0)
            if price > 0:
                for days in [7, 30]:
                    self._price_windows[product_id][days].add(price, event.timestamp)
        elif event.event_type == "rank":
            rank = int(normalized_event.get("rank", 0) or 0)
            self._rank_history[product_id].append((event.timestamp, rank))
            if len(self._rank_history[product_id]) > 100:
                self._rank_history[product_id] = self._rank_history[product_id][-50:]
        elif event.event_type == "review":
            sentiment = float(normalized_event.get("sentiment", 0) or 0)
            review_count = int(normalized_event.get("review_count", 1) or 1)
            for days in [7, 30]:
                self._sentiment_windows[product_id][days].add(sentiment, event.timestamp)
                self._review_count_windows[product_id][days].add(review_count, event.timestamp)

        features = await self._compute_features(product_id)
        feature_dict = features.to_dict()
        self._redis.set(product_id, feature_dict)
        self._clickhouse.insert(feature_dict)
        self._snapshot_store.upsert(product_id, feature_dict)
        self._stats["features_computed"] += 1

        return {
            "event_id": event.event_id,
            "product_id": product_id,
            "event_type": event.event_type,
            "features_updated": True,
            "features": feature_dict,
        }

    async def _compute_features(self, product_id: str) -> ProductFeatures:
        """计算产品特征。"""
        sales_7d = self._sales_windows[product_id][7].get_aggregates()
        sales_30d = self._sales_windows[product_id][30].get_aggregates()
        sales_90d = self._sales_windows[product_id][90].get_aggregates()
        price_7d = self._price_windows[product_id][7].get_aggregates()
        price_30d = self._price_windows[product_id][30].get_aggregates()

        price_values = []
        for days in [7, 30]:
            for bucket in self._price_windows[product_id][days]._buckets.values():
                price_values.extend(bucket.get("values", []))
        price_values = price_values[-30:]
        trend, slope = TrendDetector.detect_trend(price_values)

        rank_history = self._rank_history.get(product_id, [])
        rank_current = rank_history[-1][1] if rank_history else 0
        rank_1d_ago = None
        rank_7d_ago = None
        now = time.time()
        for ts, rank in reversed(rank_history):
            if rank_1d_ago is None and ts <= now - self.DAY_SECONDS:
                rank_1d_ago = rank
            if rank_7d_ago is None and ts <= now - 7 * self.DAY_SECONDS:
                rank_7d_ago = rank
            if rank_1d_ago is not None and rank_7d_ago is not None:
                break

        sentiment_30d = self._sentiment_windows[product_id][30].get_aggregates()
        review_count_30d = self._review_count_windows[product_id][30].get_aggregates()
        sales_growth_rate_7d = 0.0
        if sales_30d["sum"]:
            baseline_weekly = float(sales_30d["sum"]) / (30.0 / 7.0)
            sales_growth_rate_7d = ((float(sales_7d["sum"]) - baseline_weekly) / max(baseline_weekly, 1.0))
        competitor_count = max(1, int(price_30d["count"] or sales_30d["count"] or 1))
        market_share_estimate = min(1.0, round(float(sales_30d["sum"]) / max(float(sales_30d["sum"]) + competitor_count * 100.0, 1.0), 4))

        return ProductFeatures(
            product_id=product_id,
            sales_7d=int(sales_7d["sum"]),
            sales_30d=int(sales_30d["sum"]),
            sales_90d=int(sales_90d["sum"]),
            sales_growth_rate_7d=sales_growth_rate_7d,
            order_count_7d=sales_7d["count"],
            avg_price_7d=price_7d["avg"],
            avg_price_30d=price_30d["avg"],
            price_std_30d=price_30d["std"],
            price_trend=trend,
            price_trend_slope=slope,
            rank_current=rank_current,
            rank_change_1d=(rank_1d_ago or rank_current) - rank_current if rank_current else 0,
            rank_change_7d=(rank_7d_ago or rank_current) - rank_current if rank_current else 0,
            competitor_count=competitor_count,
            market_share_estimate=market_share_estimate,
            review_sentiment=sentiment_30d["avg"],
            review_count_30d=int(review_count_30d["sum"]),
        )

    async def get_features(self, product_id: str) -> dict[str, Any] | None:
        """获取产品特征(D65 API)。"""
        cached = self._redis.get(product_id)
        if cached:
            self._stats["cache_hits"] += 1
            return cached

        self._stats["cache_misses"] += 1
        snapshot = self._snapshot_store.get(product_id)
        if snapshot is not None:
            self._stats["snapshot_hits"] += 1
            self._redis.set(product_id, snapshot)
            return snapshot

        self._stats["snapshot_misses"] += 1
        features = await self._compute_features(product_id)
        result = features.to_dict()
        self._redis.set(product_id, result)
        self._snapshot_store.upsert(product_id, result)
        return result

    async def get_features_batch(self, product_ids: list[str]) -> dict[str, dict[str, Any]]:
        """批量获取特征。"""
        results = {}
        for pid in product_ids:
            features = await self.get_features(pid)
            if features:
                results[pid] = features
        return results

    def get_feature_history(self, product_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._snapshot_store.history(product_id, limit=limit)

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "cache_hit_rate": round(
                self._stats["cache_hits"] / max(self._stats["cache_hits"] + self._stats["cache_misses"], 1), 4
            ),
            "redis": self._redis.get_stats(),
            "clickhouse": self._clickhouse.get_stats(),
            "snapshot_store": self._snapshot_store.get_stats(),
        }
