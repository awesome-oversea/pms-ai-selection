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
async def test_rescore_task_from_execution_feedback_updates_decision_output():
    service = SelectionTaskService(_DummySession(), tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca")
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
                    "profitability": {"expected_margin": 28.5, "roi_year1_percent": 42.0},
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

    result = await service.rescore_task_from_execution_feedback(
        str(task_id),
        {
            "sales_7d": 160,
            "review_rating": 4.6,
            "review_count": 28,
            "gross_profit": 880.0,
            "margin_rate": 0.31,
            "available_inventory": 42,
            "stockout_risk": False,
            "source": "close_loop",
            "notes": "执行后表现优于预期",
        },
    )

    assert result is not None
    assert result["rescore_summary"]["decision"] == "GO"
    assert result["decision_output"]["execution_feedback"]["sales"]["sales_7d"] == 160
    assert result["decision_output"]["profitability"]["actual_gross_profit"] == 880.0
    assert result["decision_output"]["pricing"]["rescore_adjustment_applied"] is True
    assert result["decision_output"]["decision"]["rescore_source"] == "close_loop"


@pytest.mark.asyncio
async def test_rescore_task_from_execution_feedback_includes_complaint_risk():
    service = SelectionTaskService(_DummySession(), tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca")
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
                    "profitability": {"expected_margin": 28.5, "roi_year1_percent": 42.0},
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

    result = await service.rescore_task_from_execution_feedback(
        str(task_id),
        {
            "sales_7d": 60,
            "review_rating": 3.8,
            "review_count": 10,
            "gross_profit": 120.0,
            "margin_rate": 0.18,
            "available_inventory": 20,
            "stockout_risk": False,
            "complaint_count": 2,
            "complaint_reason_breakdown": {"logistics": 1, "quality": 1},
            "source": "close_loop",
        },
    )

    assert result is not None
    assert result["decision_output"]["execution_feedback"]["complaints"]["count"] == 2
    assert any(risk.get("category") == "customer_complaint" for risk in result["decision_output"]["risks"])


@pytest.mark.asyncio
async def test_export_feedback_feature_asset_returns_feature_and_eval_sample():
    service = SelectionTaskService(_DummySession(), tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca")
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
            "feedback_loop_rescore": {"score": 91.0, "decision": "GO"},
            "execution_result": {
                "decision_output": {
                    "pricing": {"recommended_price": 40.39},
                    "execution_feedback": {
                        "sales": {"sales_7d": 160},
                        "reviews": {"rating": 4.6, "count": 28},
                        "inventory": {"available_inventory": 42, "stockout_risk": False},
                    },
                }
            },
        },
    )

    async def _fake_get_task(task_uuid):
        assert task_uuid == task_id
        return repo_task

    service.repo.get_task = _fake_get_task
    result = await service.export_feedback_feature_asset(str(task_id))
    assert result is not None
    assert result["feature_asset"]["asset_type"] == "feedback_feature_asset"
    assert result["feature_asset"]["features"]["sales_7d"] == 160
    assert result["feature_asset"]["evaluation_sample"]["decision"] == "GO"
    assert repo_task.config["feedback_feature_asset_ready"] is True
    assert repo_task.config["feedback_feature_asset"]["asset_type"] == "feedback_feature_asset"
