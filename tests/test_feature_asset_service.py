from __future__ import annotations

import pytest
from src.infrastructure.feature_engine import FeatureEngine, LocalFeatureSnapshotStore
from src.services.feature_asset_service import FeatureAssetService


@pytest.mark.asyncio
async def test_feature_asset_service_ingest_and_query(tmp_path):
    engine = FeatureEngine(snapshot_store=LocalFeatureSnapshotStore(tmp_path / "feature-store.db"))
    service = FeatureAssetService(engine=engine)

    await service.ingest_event({"product_id": "sku-001", "event_type": "sales", "sales": 12, "price": 39.9})
    await service.ingest_event({"product_id": "sku-001", "event_type": "review", "rating": 4.5, "review_count": 2, "sentiment": 0.75})
    await service.ingest_event({"product_id": "sku-001", "event_type": "rank", "rank": 15})

    feature = await service.get_feature("sku-001")
    assert feature is not None
    assert feature["product_id"] == "sku-001"
    assert "sales_growth_rate_7d" in feature
    assert "review_sentiment_score" in feature
    assert "price_volatility" in feature
    assert feature["feature_asset"]["product_id"] == "sku-001"

    batch = await service.get_features_batch(["sku-001"])
    assert "sku-001" in batch
    assert batch["sku-001"]["feature_asset"]["product_id"] == "sku-001"

    history = service.get_feature_history("sku-001", limit=10)
    assert len(history) >= 1
    assert history[0]["feature_asset"]["product_id"] == "sku-001"

    status = service.get_status()
    assert status["feature_store"]["engine"] == "local_feature_engine"
    assert "sales_growth_rate_7d" in status["feature_keys"]
