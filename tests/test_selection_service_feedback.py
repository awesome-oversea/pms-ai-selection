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


@pytest.mark.asyncio
async def test_add_feedback_updates_decision_output():
    service = SelectionTaskService(
        _DummySession(),
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin"], "username": "ops-admin"},
    )
    task_id = uuid.uuid4()
    repo_task = SimpleNamespace(
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
        config={
            "execution_result": {
                "decision_output": {
                    "decision": {"decision": "GO", "recommendation": "蓝牙耳机 Pro"},
                    "pricing": {"recommended_price": 39.99},
                    "risks": [],
                    "recommendation_reasons": ["趋势向上"],
                }
            }
        },
    )

    async def _fake_get_task(task_uuid):
        assert task_uuid == task_id
        return repo_task

    service.repo.get_task = _fake_get_task

    result = await service.add_feedback(
        str(task_id),
        {
            "source": "crm",
            "rating": 2,
            "sentiment": "negative",
            "tags": ["quality_issue", "refund"],
            "comment": "退货偏多",
        },
    )

    assert result is not None
    assert result["feedback_entry"]["feedback_label"] == "negative"
    assert result["decision_output"]["customer_feedback"]["latest_label"] == "negative"
    assert result["decision_output"]["pricing"]["feedback_adjustment_applied"] is True
    assert result["decision_output"]["pricing"]["recommended_price"] < 39.99


@pytest.mark.asyncio
async def test_adopt_recommendation_persists_adoption_state():
    service = SelectionTaskService(
        _DummySession(),
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin"], "username": "ops-admin"},
    )
    task_id = uuid.uuid4()
    repo_task = SimpleNamespace(
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
                    "pricing": {"recommended_price": 39.99},
                    "supply_chain": {"primary_supplier": "SUP-001"},
                }
            },
        },
    )

    async def _fake_get_task(task_uuid):
        assert task_uuid == task_id
        return repo_task

    service.repo.get_task = _fake_get_task

    result = await service.adopt_recommendation(
        str(task_id),
        quantity=240,
        scm_name="scm-default",
        supplier_code=None,
        notes="转采购建议",
    )

    assert result is not None
    assert result["adoption"]["status"] == "adopted"
    assert result["adoption"]["quantity"] == 240
    assert result["adoption"]["supplier_code"] == "SUP-001"
    assert result["adoption"]["recommended_price"] == 39.99
    assert repo_task.config["status_reason"] == "已采纳推荐，等待采购执行"


@pytest.mark.asyncio
async def test_reject_recommendation_persists_rejection_state_and_model_feedback():
    service = SelectionTaskService(
        _DummySession(),
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin"], "username": "ops-admin"},
    )
    task_id = uuid.uuid4()
    repo_task = SimpleNamespace(
        id=task_id,
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.MEDIUM,
        title="钃濈墮鑰虫満",
        target_category="electronics",
        target_market="US",
        budget_max=1000.0,
        created_at=None,
        updated_at=None,
        completed_at=None,
        result_summary="鎵ц瀹屾垚",
        created_by=None,
        config={
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "execution_result": {
                "decision_output": {
                    "decision": {"decision": "GO", "recommendation": "钃濈墮鑰虫満 Pro"},
                    "pricing": {"recommended_price": 39.99},
                    "recommendation_reasons": ["瓒嬪娍鍚戜笂"],
                }
            },
        },
    )

    async def _fake_get_task(task_uuid):
        assert task_uuid == task_id
        return repo_task

    service.repo.get_task = _fake_get_task

    result = await service.reject_recommendation(
        str(task_id),
        reason="利润空间不足",
        feedback_tags=[],
        notes="先不进入采购评审",
    )

    assert result is not None
    assert result["rejection"]["status"] == "rejected"
    assert result["rejection"]["reason"] == "利润空间不足"
    assert repo_task.config["model_feedback"]["latest_action"] == "reject"
    assert repo_task.config["model_feedback"]["feedback_tags"] == ["margin_risk"]
    assert repo_task.config["rejection_history"][0]["notes"] == "先不进入采购评审"
    assert repo_task.config["execution_result"]["decision_output"]["rejection_feedback"]["label"] == "rejected"
    assert "用户拒绝原因: 利润空间不足" in repo_task.config["execution_result"]["decision_output"]["recommendation_reasons"]
    assert repo_task.config["status_reason"] == "已拒绝推荐: 利润空间不足"


@pytest.mark.asyncio
async def test_reject_recommendation_blocks_when_task_already_adopted():
    service = SelectionTaskService(
        _DummySession(),
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin"], "username": "ops-admin"},
    )
    task_id = uuid.uuid4()
    repo_task = SimpleNamespace(
        id=task_id,
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.MEDIUM,
        title="钃濈墮鑰虫満",
        target_category="electronics",
        target_market="US",
        budget_max=1000.0,
        created_at=None,
        updated_at=None,
        completed_at=None,
        result_summary="鎵ц瀹屾垚",
        created_by=None,
        config={
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "adoption": {"status": "adopted", "quantity": 240},
            "execution_result": {"decision_output": {"decision": {"decision": "GO"}}},
        },
    )

    async def _fake_get_task(task_uuid):
        assert task_uuid == task_id
        return repo_task

    service.repo.get_task = _fake_get_task

    with pytest.raises(ValueError, match="已采纳推荐"):
        await service.reject_recommendation(str(task_id), reason="利润空间不足")


@pytest.mark.asyncio
async def test_approve_task_builds_multistage_history_and_pending_next_stage():
    service = SelectionTaskService(
        _DummySession(),
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "roles": ["tenant_admin", "operator"],
            "username": "ops-admin",
        },
    )
    task_id = uuid.uuid4()
    repo_task = SimpleNamespace(
        id=task_id,
        status=TaskStatus.RUNNING,
        priority=TaskPriority.MEDIUM,
        title="蓝牙耳机",
        target_category="electronics",
        target_market="US",
        budget_max=1000.0,
        created_at=None,
        updated_at=None,
        completed_at=None,
        result_summary="执行中",
        created_by=None,
        config={
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "approval": {
                "status": "pending",
                "current_stage": "operator_review",
                "current_stage_order": 1,
                "flow": SelectionTaskService._build_approval_flow(),
                "approval_count": 0,
            },
            "approval_history": [],
        },
    )

    async def _fake_get_task(task_uuid):
        assert task_uuid == task_id
        return repo_task

    service.repo.get_task = _fake_get_task

    result = await service.approve_task(
        str(task_id),
        action="approve",
        reviewer="ops-admin",
        comment="运营通过",
        stage="operator_review",
    )

    assert result is not None
    assert result["status"] == "pending"
    assert result["current_stage"] == "procurement_review"
    assert len(result["approval_history"]) == 1
    assert repo_task.config["approval"]["flow"][0]["status"] == "approved"
    assert repo_task.config["approval"]["flow"][1]["status"] == "pending"


@pytest.mark.asyncio
async def test_approve_task_rejects_and_records_history():
    service = SelectionTaskService(
        _DummySession(),
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "roles": ["tenant_admin", "manager"],
            "username": "manager-1",
        },
    )
    task_id = uuid.uuid4()
    flow = SelectionTaskService._build_approval_flow()
    flow[0]["status"] = "approved"
    flow[1]["status"] = "approved"
    repo_task = SimpleNamespace(
        id=task_id,
        status=TaskStatus.RUNNING,
        priority=TaskPriority.MEDIUM,
        title="蓝牙耳机",
        target_category="electronics",
        target_market="US",
        budget_max=1000.0,
        created_at=None,
        updated_at=None,
        completed_at=None,
        result_summary="执行中",
        created_by=None,
        config={
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "approval": {
                "status": "pending",
                "current_stage": "manager_review",
                "current_stage_order": 3,
                "flow": flow,
                "approval_count": 2,
            },
            "approval_history": [],
        },
    )

    async def _fake_get_task(task_uuid):
        assert task_uuid == task_id
        return repo_task

    service.repo.get_task = _fake_get_task

    result = await service.approve_task(
        str(task_id),
        action="reject",
        reviewer="manager-1",
        comment="利润风险过高",
        stage="manager_review",
    )

    assert result is not None
    assert result["status"] == "rejected"
    assert result["approval"]["final_decision"] == "rejected"
    assert repo_task.config["approval"]["flow"][2]["status"] == "rejected"
    assert repo_task.config["approval_history"][0]["comment"] == "利润风险过高"
