from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from src.models.enums import TaskPriority, TaskStatus
from src.services.selection_service import SelectionTaskService


class _DummySession:
    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


def _build_service() -> SelectionTaskService:
    return SelectionTaskService(
        _DummySession(),
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin"], "username": "ops-admin"},
    )


def _build_repo_task(task_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=task_id,
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.MEDIUM,
        title="蓝牙耳机",
        target_category="electronics",
        target_market="US",
        budget_max=1000.0,
        created_at=None,
        updated_at=None,
        completed_at=None,
        result_summary="执行完成",
        created_by=None,
        config={
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "execution_result": {
                "decision_output": {
                    "decision": {"decision": "GO", "recommendation": "蓝牙耳机 Pro"},
                    "quality_summary": {"signal_governance_status": "local_validation_only"},
                    "data_source_governance": {
                        "governance_status": "local_validation_only",
                        "local_validation_only_sources": ["amazon", "ali1688"],
                        "enterprise_ready_sources": ["gdelt"],
                        "mock_only_sources": ["tiktok"],
                        "not_ready_sources": ["google_trends"],
                        "next_action": "优先补齐 Amazon/TikTok/Google Trends 正式凭证与供应侧正式连接",
                    },
                }
            },
        },
    )


def test_serialize_task_surfaces_signal_governance_fields():
    service = _build_service()
    repo_task = _build_repo_task(uuid.uuid4())

    serialized = service._serialize_task(repo_task)

    assert serialized["signal_governance_status"] == "local_validation_only"
    assert serialized["signal_governance_summary"]["requires_enterprise_connectors"] is True
    assert "本地业务验证" in serialized["signal_governance_summary"]["summary_text"]
    assert serialized["data_source_governance"]["local_validation_only_sources"] == ["amazon", "ali1688"]
    assert serialized["data_source_governance"]["enterprise_ready_sources"] == ["gdelt"]


@pytest.mark.asyncio
async def test_get_task_result_keeps_signal_governance_summary():
    service = _build_service()
    serialized_task = service._serialize_task(_build_repo_task(uuid.uuid4()))

    async def _fake_get_task(_task_id: str):
        return serialized_task

    async def _fake_cases(_task: dict):
        return {"total_found": 0, "results": []}

    service.get_task = _fake_get_task  # type: ignore[method-assign]
    service._load_similar_history_cases = _fake_cases  # type: ignore[method-assign]
    service._load_similar_review_cases = _fake_cases  # type: ignore[method-assign]
    service._load_historical_performance = _fake_cases  # type: ignore[method-assign]

    result = await service.get_task_result("task-governance-001")

    assert result is not None
    assert result["signal_governance_status"] == "local_validation_only"
    assert result["signal_governance_summary"]["requires_enterprise_connectors"] is True
    assert result["data_source_governance"]["mock_only_sources"] == ["tiktok"]
