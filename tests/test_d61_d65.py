"""D61-D65 单元测试: 实时特征工程"""

import sys
import time

import pytest
from src.infrastructure.feature_engine import (
    ClickHouseFeatureStore,
    FeatureEngine,
    LocalFeatureSnapshotStore,
    ProductFeatures,
    RedisFeatureStore,
    SlidingWindow,
    TrendDetector,
    TrendDirection,
)


class TestSlidingWindow:
    """测试滑动窗口(D62)"""

    def test_window_creation(self):
        window = SlidingWindow(window_size_seconds=3600, slide_interval_seconds=60)
        assert window._window_size == 3600

    def test_add_value(self):
        window = SlidingWindow()
        window.add(10.0)
        window.add(20.0)
        agg = window.get_aggregates()
        assert agg["count"] == 2
        assert agg["sum"] == 30.0

    def test_get_aggregates(self):
        window = SlidingWindow()
        for i in range(10):
            window.add(float(i))
        agg = window.get_aggregates()
        assert agg["count"] == 10
        assert agg["avg"] == 4.5
        assert agg["std"] > 0

    def test_window_expiry(self):
        window = SlidingWindow(window_size_seconds=1, slide_interval_seconds=1)
        window.add(10.0, time.time() - 10)
        window._cleanup()
        agg = window.get_aggregates()
        assert agg["count"] == 0


class TestTrendDetector:
    """测试趋势检测(D63)"""

    def test_detect_upward_trend(self):
        values = [10, 12, 14, 16, 18, 20]
        trend, slope = TrendDetector.detect_trend(values)
        assert trend == TrendDirection.UP
        assert slope > 0

    def test_detect_downward_trend(self):
        values = [20, 18, 16, 14, 12, 10]
        trend, slope = TrendDetector.detect_trend(values)
        assert trend == TrendDirection.DOWN
        assert slope < 0

    def test_detect_stable_trend(self):
        values = [10, 10.1, 9.9, 10.0, 10.1, 9.9]
        trend, slope = TrendDetector.detect_trend(values)
        assert trend == TrendDirection.STABLE

    def test_detect_single_value(self):
        trend, slope = TrendDetector.detect_trend([10])
        assert trend == TrendDirection.STABLE
        assert slope == 0.0

    def test_detect_anomaly(self):
        history = [10, 11, 10, 12, 11, 10, 11]
        is_anomaly = TrendDetector.detect_anomaly(100, history)
        assert is_anomaly is True

    def test_detect_no_anomaly(self):
        history = [10, 11, 10, 12, 11, 10, 11]
        is_anomaly = TrendDetector.detect_anomaly(11, history)
        assert is_anomaly is False


class TestRedisFeatureStore:
    """测试Redis特征存储(D65)"""

    def setup_method(self):
        self.store = RedisFeatureStore()

    def test_set_and_get(self):
        features = {"product_id": "P001", "sales_7d": 100}
        self.store.set("P001", features)
        result = self.store.get("P001")
        assert result["sales_7d"] == 100

    def test_get_missing(self):
        result = self.store.get("UNKNOWN")
        assert result is None

    def test_delete(self):
        self.store.set("P001", {"sales": 100})
        self.store.delete("P001")
        result = self.store.get("P001")
        assert result is None

    def test_get_stats(self):
        self.store.set("P001", {"sales": 100})
        stats = self.store.get_stats()
        assert stats["total_keys"] == 1


class TestClickHouseFeatureStore:
    """测试ClickHouse特征存储(D65)"""

    def setup_method(self):
        self.store = ClickHouseFeatureStore()

    def test_insert(self):
        features = {"product_id": "P001", "sales_7d": 100}
        self.store.insert(features)
        assert len(self.store._history) == 1

    def test_query_by_product(self):
        self.store.insert({"product_id": "P001", "sales": 100})
        self.store.insert({"product_id": "P002", "sales": 200})
        results = self.store.query(product_id="P001")
        assert len(results) == 1
        assert results[0]["product_id"] == "P001"

    def test_query_with_limit(self):
        for i in range(10):
            self.store.insert({"product_id": f"P{i:03d}"})
        results = self.store.query(limit=5)
        assert len(results) == 5

    def test_get_stats(self):
        self.store.insert({"product_id": "P001"})
        stats = self.store.get_stats()
        assert stats["total_records"] == 1


class TestProductFeatures:
    """测试产品特征"""

    def test_features_creation(self):
        features = ProductFeatures(
            product_id="P001",
            sales_7d=100,
            sales_30d=500,
            avg_price_7d=99.9,
        )
        assert features.product_id == "P001"
        assert features.sales_7d == 100

    def test_features_to_dict(self):
        features = ProductFeatures(
            product_id="P001",
            sales_7d=100,
            price_trend=TrendDirection.UP,
        )
        d = features.to_dict()
        assert d["product_id"] == "P001"
        assert d["price_trend"] == "up"


class TestFeatureEngine:
    """测试特征引擎(D61-D65)"""

    def setup_method(self):
        self.engine = FeatureEngine()

    @pytest.mark.asyncio
    async def test_process_sales_event(self):
        event = {
            "product_id": "P001",
            "event_type": "sales",
            "sales": 10,
            "price": 99.9,
        }
        result = await self.engine.process_event(event)
        assert result["features_updated"] is True

    @pytest.mark.asyncio
    async def test_process_price_event(self):
        event = {
            "product_id": "P001",
            "event_type": "price",
            "price": 89.9,
        }
        result = await self.engine.process_event(event)
        assert result["product_id"] == "P001"

    @pytest.mark.asyncio
    async def test_process_rank_event(self):
        event = {
            "product_id": "P001",
            "event_type": "rank",
            "rank": 15,
        }
        result = await self.engine.process_event(event)
        assert result["features_updated"] is True

    @pytest.mark.asyncio
    async def test_get_features(self):
        await self.engine.process_event({
            "product_id": "P001",
            "event_type": "sales",
            "sales": 50,
            "price": 99.9,
        })
        features = await self.engine.get_features("P001")
        assert features is not None
        assert features["product_id"] == "P001"
        assert "sales_7d" in features

    @pytest.mark.asyncio
    async def test_get_features_batch(self):
        for i in range(3):
            await self.engine.process_event({
                "product_id": f"P{i:03d}",
                "event_type": "sales",
                "sales": 10 * (i + 1),
            })
        results = await self.engine.get_features_batch(["P000", "P001", "P002"])
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.engine.process_event({
            "product_id": "P001",
            "event_type": "sales",
            "sales": 10,
        })
        stats = self.engine.get_stats()
        assert stats["events_processed"] == 1
        assert stats["features_computed"] == 1


    @pytest.mark.asyncio
    async def test_process_order_and_review_events_with_snapshot_store(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.infrastructure.feature_engine._FEATURE_DB_PATH", tmp_path / "feature_engine_test.db")
        engine = FeatureEngine(snapshot_store=LocalFeatureSnapshotStore())
        await engine.process_event({
            "event_type": "order.updated",
            "aggregate_id": "task-001",
            "payload": {"task_id": "task-001", "units": 12, "unit_price": 39.9},
        })
        await engine.process_event({
            "event_type": "review.updated",
            "aggregate_id": "crm-001",
            "payload": {"task_id": "task-001", "rating": 4.5, "review_count": 3, "feedback": "客户整体满意，物流稍慢。"},
        })
        features = await engine.get_features("task-001")
        assert features is not None
        assert features["sales_7d"] == 12
        assert features["review_count_30d"] == 3
        assert "sales_growth_rate_7d" in features
        history = engine.get_feature_history("task-001", limit=5)
        assert len(history) >= 2


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        engine = FeatureEngine()

        events = [
            {"product_id": "P001", "event_type": "sales", "sales": 10, "price": 100},
            {"product_id": "P001", "event_type": "sales", "sales": 15, "price": 98},
            {"product_id": "P001", "event_type": "sales", "sales": 20, "price": 95},
            {"product_id": "P001", "event_type": "rank", "rank": 50},
            {"product_id": "P001", "event_type": "rank", "rank": 45},
        ]

        for event in events:
            await engine.process_event(event)

        features = await engine.get_features("P001")
        assert features["sales_7d"] == 45
        assert features["rank_current"] == 45

        stats = engine.get_stats()
        assert stats["events_processed"] == 5
        assert stats["cache_hit_rate"] >= 0


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
