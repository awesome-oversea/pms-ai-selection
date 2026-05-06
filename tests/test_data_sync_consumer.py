from __future__ import annotations

import pytest
from src.infrastructure.kafka import build_dlq_topic
from src.workers.data_sync_consumer import DataSyncConsumer


@pytest.mark.asyncio
async def test_data_sync_consumer_consumes_batch():
    consumer = DataSyncConsumer(topic="pms-agent-event", consumer_group="pms-multi-entity-consumer-group")
    result = await consumer.consume_batch([
        {"event_id": "evt-001", "topic": "pms-agent-event", "entity_type": "product"},
        {"event_id": "evt-002", "topic": "pms-agent-event", "entity_type": "document"},
        {"event_id": "evt-003", "topic": "pms-agent-event", "entity_type": "inventory"},
    ])
    assert result["consumed"] == 3
    assert result["consumer_group"] == "pms-multi-entity-consumer-group"
    assert set(result["entity_types"]) == {"product", "document", "inventory"}
    assert result["last_event_id"] == "evt-003"
    assert build_dlq_topic("pms-agent-event") == "pms-agent-event.dlq"


@pytest.mark.asyncio
async def test_data_sync_consumer_consumes_feature_events(monkeypatch, tmp_path):
    monkeypatch.setattr("src.infrastructure.feature_engine._FEATURE_DB_PATH", tmp_path / "consumer_feature_store.db")
    consumer = DataSyncConsumer(topic="pms-agent-event", consumer_group="pms-feature-consumer-group")
    result = await consumer.consume_feature_events([
        {
            "event_id": "evt-order-001",
            "topic": "pms-agent-event",
            "entity_type": "order",
            "event_type": "order.updated",
            "aggregate_id": "task-001",
            "payload": {"task_id": "task-001", "units": 8, "unit_price": 49.9},
        },
        {
            "event_id": "evt-review-001",
            "topic": "pms-agent-event",
            "entity_type": "review",
            "event_type": "review.updated",
            "aggregate_id": "crm-001",
            "payload": {"task_id": "task-001", "rating": 4.2, "review_count": 2, "feedback": "总体满意，包装可优化。"},
        }
    ])
    assert result["consumed"] == 2
    assert result["updated_count"] == 2
    assert result["feature_store_updated"] is True
    assert result["product_ids"] == ["task-001"]
    assert result["updated_features"][0]["features"]["product_id"] == "task-001"


@pytest.mark.asyncio
async def test_data_sync_consumer_ingests_review_events(monkeypatch, tmp_path):
    monkeypatch.setattr("src.services.local_knowledge_service._DB_PATH", tmp_path / "consumer_review_case.db")
    consumer = DataSyncConsumer(topic="pms-agent-event", consumer_group="pms-review-consumer-group")
    result = await consumer.consume_review_events([
        {
            "event_id": "evt-review-001",
            "topic": "pms-agent-event",
            "entity_type": "review",
            "event_type": "review.updated",
            "aggregate_id": "crm-001",
            "payload": {
                "review_id": "crm-001",
                "task_id": "task-001",
                "product_id": "prod-001",
                "product_name": "蓝牙耳机企业联调样本",
                "asin": "B0ERP0001",
                "rating": 4.6,
                "review_count": 13,
                "feedback": "客户评价良好，但出现少量退货投诉，需要优化包装。",
            },
        }
    ])
    assert result["consumed"] == 1
    assert result["ingested_count"] == 1
    assert result["vector_updated_count"] == 1
    assert result["case_type"] == "crm_review_case"
    assert result["ingested_cases"][0]["case_type"] == "crm_review_case"
    assert result["ingested_cases"][0]["vector_sync"]["is_incremental"] is True
    assert result["vector_updates"][0]["chunk_count"] >= 1
