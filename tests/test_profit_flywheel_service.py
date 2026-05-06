from __future__ import annotations

from types import SimpleNamespace

import pytest
from src.models.enums import TaskStatus
from src.services.profit_flywheel_service import ProfitFlywheelService


@pytest.mark.asyncio
async def test_profit_flywheel_service_build_status():
    service = ProfitFlywheelService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca")

    async def _fake_list_tasks(limit=1, offset=0, status=None):
        task = SimpleNamespace(
            id="task-001",
            title="蓝牙耳机选品",
            status=TaskStatus.COMPLETED,
            target_market="US",
            target_category="electronics",
            completed_at=None,
            config={
                "status_reason": "任务完成",
                "execution_result": {
                    "decision_output": {
                        "rescore_summary": {"score": 88.0, "decision": "GO"}
                    },
                    "results": {
                        "commercial_evaluation": {
                            "go_no_go": {"decision": "GO"}
                        }
                    }
                },
            },
        )
        return [task], 1

    async def _fake_get_config(system_type, name="default"):
        return SimpleNamespace(id=f"cfg-{system_type.value}", name=name, system_type=system_type)

    async def _fake_list_sync_logs(system_type, limit=1):
        log = SimpleNamespace(status="completed", sync_type="export", finished_at=None)
        return [(log, SimpleNamespace(system_type=system_type, name="default", id=f"cfg-{system_type.value}"))]

    async def _fake_build_status():
        return {
            "bi_ready_assets": ["selection_tasks_snapshot", "data_sync_events_snapshot"],
            "downstream_consumers": {"bi": ["selection_tasks_snapshot", "data_sync_events_snapshot"]},
            "offline": {"assets": {"selection_tasks_snapshot": "selection.jsonl", "data_sync_events_snapshot": "events.jsonl"}},
        }

    service.selection_repo = SimpleNamespace(list_tasks=_fake_list_tasks)
    service.erp_repo = SimpleNamespace(get_config=_fake_get_config, list_sync_logs=_fake_list_sync_logs)
    service.data_lake_service = SimpleNamespace(build_status=_fake_build_status)

    status = await service.build_status()
    assert status["selection"]["can_drive_downstream"] is True
    assert status["feedback_loop"]["auto_rescore_completed"] is True
    assert status["feedback_loop"]["feature_asset_ready"] is True
    assert status["selection"]["task"]["status_reason"] == "任务完成"
    assert status["feedback_loop"]["loop_closed"] is True
    assert status["route_status"]["selection_to_scm"] is True
    assert status["route_status"]["fms_to_bi"] is True
    assert status["loop_gaps"] == []
    assert status["recycle_actions"][0]["target"] == "selection"
    assert set(status["score_feedback_inputs"]["signals"]) == {"crm_feedback", "fms_profit", "wms_inventory", "bi_metrics"}
    assert status["score_feedback_inputs"]["can_rescore_selection"] is True
    assert status["overall_status"] == "closed_loop_ready"
    assert status["recommended_actions"] == []
