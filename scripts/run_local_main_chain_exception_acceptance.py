from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.enums import TaskPriority, TaskStatus
from src.services.profit_flywheel_service import ProfitFlywheelService
from src.services.selection_service import SelectionTaskService

ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "local_main_chain_exceptions"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    evidence: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.evidence is None:
            payload.pop("evidence")
        return payload


class _DummySession:
    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


def _build_run_dir() -> Path:
    run_dir = ARTIFACT_ROOT / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def _run_checks() -> tuple[list[CheckResult], dict[str, Any]]:
    task_id = uuid4()
    session = _DummySession()

    reject_task = SimpleNamespace(
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
                "flow": SelectionTaskService._build_approval_flow(),
                "approval_count": 0,
            },
            "approval_history": [],
        },
    )
    reject_task.config["approval"]["flow"][0]["status"] = "approved"
    reject_task.config["approval"]["flow"][1]["status"] = "approved"

    reject_service = SelectionTaskService(
        session,
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin", "manager"], "username": "manager-1"},
    )
    reject_service.repo.get_task = lambda _task_uuid: __import__('asyncio').sleep(0, result=reject_task)
    reject_result = await reject_service.approve_task(str(task_id), action="reject", reviewer="manager-1", comment="利润风险过高", stage="manager_review")

    no_go_task = SimpleNamespace(
        id=uuid4(),
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.MEDIUM,
        title="高风险品类",
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
            "execution_result": {"decision_output": {"decision": {"decision": "NO_GO"}}},
        },
    )
    adopt_service = SelectionTaskService(
        session,
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin"], "username": "ops-admin"},
    )
    adopt_service.repo.get_task = lambda _task_uuid: __import__('asyncio').sleep(0, result=no_go_task)
    adopt_error = None
    try:
        await adopt_service.adopt_recommendation(str(no_go_task.id), quantity=100, scm_name="default")
    except Exception as exc:
        adopt_error = str(exc)

    missing_execution_task = SimpleNamespace(
        id=uuid4(),
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.MEDIUM,
        title="缺失回流结果任务",
        target_category="electronics",
        target_market="US",
        budget_max=1000.0,
        created_at=None,
        updated_at=None,
        completed_at=None,
        result_summary="执行完成",
        created_by=None,
        config={},
    )
    missing_service = SelectionTaskService(session, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca")
    missing_service.repo.get_task = lambda _task_uuid: __import__('asyncio').sleep(0, result=missing_execution_task)
    rescore_result = await missing_service.rescore_task_from_execution_feedback(str(missing_execution_task.id), {"sales_7d": 10})
    feature_asset_result = await missing_service.export_feedback_feature_asset(str(missing_execution_task.id))

    flywheel_service = ProfitFlywheelService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca")
    partial_task = SimpleNamespace(
        id="task-partial-001",
        title="蓝牙耳机选品",
        status=TaskStatus.COMPLETED,
        target_market="US",
        target_category="electronics",
        completed_at=None,
        config={"status_reason": "任务完成", "execution_result": {"results": {"commercial_evaluation": {"go_no_go": {"decision": "GO"}}}}},
    )

    async def _fake_list_tasks(limit=1, offset=0, status=None):
        return [partial_task], 1

    async def _fake_get_config(system_type, name="default"):
        if getattr(system_type, 'value', str(system_type)) == 'crm':
            return None
        return SimpleNamespace(id=f"cfg-{getattr(system_type, 'value', str(system_type))}", name=name, system_type=system_type)

    async def _fake_list_sync_logs(system_type, limit=1):
        if getattr(system_type, 'value', str(system_type)) == 'crm':
            return []
        log = SimpleNamespace(status="completed", sync_type="export", finished_at=None)
        return [(log, SimpleNamespace(system_type=system_type, name="default", id=f"cfg-{getattr(system_type, 'value', str(system_type))}"))]

    async def _fake_build_status():
        return {"bi_ready_assets": ["selection_tasks_snapshot", "data_sync_events_snapshot"], "downstream_consumers": {"bi": ["selection_tasks_snapshot"]}}

    flywheel_service.selection_repo = SimpleNamespace(list_tasks=_fake_list_tasks)
    flywheel_service.erp_repo = SimpleNamespace(get_config=_fake_get_config, list_sync_logs=_fake_list_sync_logs)
    flywheel_service.data_lake_service = SimpleNamespace(build_status=_fake_build_status)
    flywheel_status = await flywheel_service.build_status()

    checks = [
        CheckResult(
            "approval_reject_closed",
            reject_result is not None and reject_result.get("status") == "rejected" and reject_result.get("approval", {}).get("final_decision") == "rejected",
            f"reject_status={reject_result.get('status') if reject_result else None}",
            {"approval": reject_result.get("approval") if reject_result else None},
        ),
        CheckResult(
            "non_go_adoption_blocked",
            adopt_error == "当前任务不满足采纳推荐条件",
            adopt_error or "no_error",
            {"error": adopt_error},
        ),
        CheckResult(
            "missing_execution_result_safe_exit",
            rescore_result is None and feature_asset_result is None,
            f"rescore={rescore_result is None}, feature_asset={feature_asset_result is None}",
            {"rescore_result": rescore_result, "feature_asset_result": feature_asset_result},
        ),
        CheckResult(
            "partial_feedback_loop_exposes_gap",
            bool(
                flywheel_status.get("overall_status") == "partial"
                and "wms_to_crm" in (flywheel_status.get("loop_gaps") or [])
                and len(flywheel_status.get("recommended_actions") or []) > 0
            ),
            f"overall_status={flywheel_status.get('overall_status')}",
            {"loop_gaps": flywheel_status.get("loop_gaps"), "recommended_actions": flywheel_status.get("recommended_actions")},
        ),
    ]

    details = {
        "approval_reject": reject_result,
        "non_go_adoption_error": adopt_error,
        "missing_execution_result": {"rescore_result": rescore_result, "feature_asset_result": feature_asset_result},
        "profit_flywheel_partial": flywheel_status,
    }
    return checks, details


async def _run_acceptance() -> dict[str, Any]:
    run_dir = _build_run_dir()
    checks, details = await _run_checks()
    summary = {
        "status": "passed" if all(item.passed for item in checks) else "failed",
        "accepted": all(item.passed for item in checks),
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run_dir.name,
        "checks": [item.to_dict() for item in checks],
        "details": details,
        "artifacts": {
            "summary": str(run_dir / "summary.json"),
            "details": str(run_dir / "details.json"),
        },
    }
    _write_json(run_dir / "details.json", details)
    _write_json(run_dir / "summary.json", summary)
    return summary


def main() -> int:
    summary = __import__('asyncio').run(_run_acceptance())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
