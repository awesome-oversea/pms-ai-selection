from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from src.services.data_lake_service import DataLakeService

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")


class _ScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _ExecuteResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _ScalarResult(self._items)


class _FakeSession:
    async def execute(self, stmt):
        text = str(stmt)
        if "selection_tasks" in text:
            return _ExecuteResult(
                [
                    SimpleNamespace(
                        id="task-001",
                        tenant_id="tenant-001",
                        title="蓝牙耳机",
                        status=SimpleNamespace(value="completed"),
                        priority=SimpleNamespace(value="high"),
                        target_market="US",
                        target_category="electronics",
                        expected_margin=22.5,
                        completed_at=SimpleNamespace(isoformat=lambda: "2026-01-02T00:00:00+00:00"),
                        config={
                            "feedback_feature_asset_ready": True,
                            "execution_result": {
                                "decision_output": {
                                    "decision": {"decision": "GO"},
                                    "pricing": {"recommended_price": 39.9},
                                    "profitability": {"roi_year1_percent": 31.5, "payback_period_months": 5.0, "expected_margin": 22.5},
                                    "risks": [{"category": "competition"}],
                                    "recommendation_reasons": ["growth", "margin"],
                                    "rescore_summary": {"score": 88.0},
                                }
                            },
                        },
                        created_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00+00:00"),
                    )
                ]
            )
        return _ExecuteResult(
            [
                SimpleNamespace(
                    id="evt-001",
                    tenant_id="tenant-001",
                    entity_type="product",
                    event_type="product.updated",
                    topic="pms-agent-event",
                    status="sent",
                    created_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00+00:00"),
                )
            ]
        )

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_data_lake_service_exports_snapshot_to_object_store():
    session = _FakeSession()
    service = DataLakeService(session)

    result = await service.export_selection_task_snapshot()
    assert result["asset"] == "selection_tasks_snapshot"
    assert result["asset_type"] == "offline-snapshot"
    assert result["storage"] == "local"
    assert result["path"]
    assert result["relative_path"].endswith("selection_tasks.jsonl")

    event_result = await service.export_data_sync_events_snapshot()
    assert event_result["asset"] == "data_sync_events_snapshot"
    assert event_result["asset_type"] == "offline-snapshot"
    assert event_result["storage"] == "local"
    assert event_result["relative_path"].endswith("data_sync_events.jsonl")

    metrics_result = await service.export_selection_task_metrics_dataset()
    assert metrics_result["asset"] == "selection_task_metrics"
    assert metrics_result["asset_type"] == "offline-metric-dataset"
    assert metrics_result["table_format"] == "iceberg-compatible"
    assert metrics_result["path"].endswith("selection_task_metrics.jsonl")
    assert metrics_result["manifest_path"].endswith("selection_task_metrics.manifest.json")

    status = await service.build_status()
    assert status["offline"]["asset_count"] >= 2
    assert "data_sync_events_snapshot" in status["offline"]["assets"]
    assert "data_sync_events_snapshot" in status["catalog"]["offline_assets"]
    assert status["offline"]["assets"]["selection_task_metrics"].endswith("selection_task_metrics.jsonl")
    assert "table_formats" in status
    assert "processing_engines" in status
    assert status["pipeline_readiness"]["batch_ready"] is True
    assert status["pipeline_readiness"]["stream_ready"] is True
    assert "downstream_consumers" in status
    assert "selection_tasks_snapshot" in status["bi_ready_assets"]
    assert status["processing_engines"]["batch_engine"]["latest_run"]["status"] == "completed"
    assert status["processing_engines"]["stream_engine"]["latest_run"]["status"] == "completed"
    assert status["lakehouse"]["ods_ready"] is True
    assert status["lakehouse"]["table_format_ready"] is True
    assert status["lakehouse"]["iceberg_compatible_ready"] is True
    assert status["lakehouse"]["local_query_ready"] is True
    assert status["lakehouse"]["selection_task_metrics_manifest"].endswith("selection_task_metrics.manifest.json")
    assert status["layering"]["ods"]["ready"] is True
    assert status["layering"]["ads"]["ready"] is True

    selection_query = service.query_selection_tasks_snapshot(status="completed", target_market="US", limit=10)
    assert selection_query["asset"] == "selection_tasks_snapshot"
    assert selection_query["total"] == 1
    assert selection_query["items"][0]["task_id"] == "task-001"

    event_query = service.query_data_sync_events_snapshot(entity_type="product", event_type="product.updated", limit=10)
    assert event_query["asset"] == "data_sync_events_snapshot"
    assert event_query["total"] == 1
    assert event_query["items"][0]["event_id"] == "evt-001"

    metrics_query = service.query_selection_task_metrics_dataset(status="completed", target_market="US", decision="GO", limit=10)
    assert metrics_query["asset"] == "selection_task_metrics"
    assert metrics_query["table_format"] == "iceberg-compatible"
    assert metrics_query["total"] == 1
    assert metrics_query["items"][0]["task_id"] == "task-001"
    assert metrics_query["items"][0]["decision"] == "GO"
    assert metrics_query["manifest"]["table_name"] == "selection_task_metrics"
