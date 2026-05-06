from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SEC_SECRET_KEY", "local-selection-main-chain-32chars")
sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient

from src.core.auth import create_access_token
from src.core.security import clear_audit_logs, list_audit_logs
from src.main import create_app
from src.models.enums import TaskPriority, TaskStatus
from src.services.selection_service import SelectionTaskService


ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "local_main_chain"


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
    async def commit(self) -> None:
        return None

    async def refresh(self, _obj: Any) -> None:
        return None

    async def close(self) -> None:
        return None

    async def flush(self) -> None:
        return None


class _InMemorySelectionRepo:
    def __init__(self) -> None:
        self.tasks: dict[UUID, SimpleNamespace] = {}

    async def create_task(
        self,
        *,
        title: str,
        category: str,
        target_market: str,
        budget_min: float | None,
        budget_max: float | None,
        description: str,
        priority: TaskPriority,
        config: dict[str, Any],
        created_by: UUID | None,
        tenant_id: str | None,
    ) -> SimpleNamespace:
        now = datetime.now(UTC)
        task_id = uuid4()
        task = SimpleNamespace(
            id=task_id,
            title=title,
            target_category=category,
            target_market=target_market,
            budget_min=budget_min,
            budget_max=budget_max,
            description=description,
            priority=priority,
            status=TaskStatus.PENDING,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            completed_at=None,
            result_summary="任务已创建",
            config=dict(config or {}),
        )
        if tenant_id is not None:
            task.config["tenant_id"] = tenant_id
        self.tasks[task_id] = task
        return task

    async def list_tasks(
        self,
        *,
        status: TaskStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SimpleNamespace], int]:
        tasks = sorted(self.tasks.values(), key=lambda item: item.created_at, reverse=True)
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        total = len(tasks)
        return tasks[offset : offset + limit], total

    async def get_task(self, task_id: UUID, tenant_id: str | None = None) -> SimpleNamespace | None:
        task = self.tasks.get(task_id)
        if task is None:
            return None
        config = task.config or {}
        task_tenant_id = config.get("tenant_id") if isinstance(config, dict) else None
        if tenant_id and task_tenant_id and str(task_tenant_id) != str(tenant_id):
            return None
        return task

    async def update_task_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        result_summary: str | None = None,
        phase: str | None = None,
        reason: str | None = None,
    ) -> bool:
        task = self.tasks.get(task_id)
        if task is None:
            return False
        task.status = status
        task.updated_at = datetime.now(UTC)
        if result_summary is not None:
            task.result_summary = result_summary
        config = task.config or {}
        if reason is not None:
            config["status_reason"] = reason
        if phase is not None:
            history = list(config.get("status_history", []))
            history.append(
                {
                    "status": status.value,
                    "phase": phase,
                    "reason": reason,
                    "updated_at": task.updated_at.isoformat(),
                }
            )
            config["status_history"] = history[-20:]
        task.config = config
        if status == TaskStatus.COMPLETED:
            task.completed_at = task.updated_at
        return True


class AcceptanceSelectionTaskService(SelectionTaskService):
    shared_repo = _InMemorySelectionRepo()

    def __init__(self, session: Any, executor: Any = None, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        actual_session = session or _DummySession()
        super().__init__(actual_session, executor=executor, tenant_id=tenant_id, actor=actor)
        self.repo = self.shared_repo

    async def submit_task_for_execution(self, context: Any) -> None:
        task = await self.repo.get_task(UUID(str(context.task_id)))
        if task is None:
            return
        now = datetime.now(UTC)
        config = task.config or {}
        config["execution_result"] = {
            "decision_output": {
                "market_summary": {
                    "trend_direction": "up",
                    "market_size_index": 0.82,
                },
                "decision": {
                    "decision": "GO",
                    "confidence": 0.91,
                    "recommendation": "蓝牙耳机 Pro",
                },
                "product": {
                    "name": "蓝牙耳机 Pro",
                    "asin": "B0LOCALMAIN001",
                },
                "pricing": {
                    "recommended_price": 39.99,
                    "currency": "USD",
                },
                "supply_chain": {
                    "primary_supplier": "SUP-001",
                    "lead_time_days": 7,
                },
                "risks": [
                    {"type": "competition", "level": "medium"},
                ],
                "execution_summary": {
                    "steps": [
                        "collect_market_signals",
                        "score_candidate",
                        "prepare_recommendation",
                    ]
                },
            },
            "state_summary": {
                "current_phase": "completed",
                "completed": True,
            },
        }
        config["status_reason"] = "选品分析完成，等待运营初审"
        task.status = TaskStatus.COMPLETED
        task.result_summary = "主链路本地验收结果已生成"
        task.updated_at = now
        task.completed_at = now
        task.config = config


class AcceptanceErpIntegrationService:
    repo = AcceptanceSelectionTaskService.shared_repo

    def __init__(self, session: Any, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id
        self.actor = actor or {}

    async def execute_selection_adoption(
        self,
        *,
        task_id: str,
        scm_name: str = "default",
        wms_name: str = "default",
        oms_name: str = "default",
        quantity: int = 200,
        supplier_code: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        task = await self.repo.get_task(UUID(task_id))
        if task is None:
            raise ValueError(f"任务不存在: {task_id}")
        now = datetime.now(UTC).isoformat()
        adoption = dict((task.config or {}).get("adoption") or {})
        scm_receipt = {
            "purchase_order_id": f"PO-{task_id[:8]}",
            "status": "pending_review",
        }
        wms_reservation = {
            "reservation_id": f"RSV-{task_id[:8]}",
            "status": "reserved",
            "location_code": "WH-A-01",
        }
        oms_listing_draft = {
            "listing_draft_id": f"LST-{task_id[:8]}",
            "status": "draft_created",
        }
        execution_status = {
            "scm": {
                "config_name": scm_name,
                "purchase_order_id": scm_receipt["purchase_order_id"],
                "status": scm_receipt["status"],
            },
            "wms": {
                "config_name": wms_name,
                "reservation_id": wms_reservation["reservation_id"],
                "location_code": wms_reservation["location_code"],
                "status": wms_reservation["status"],
            },
            "oms": {
                "config_name": oms_name,
                "listing_draft_id": oms_listing_draft["listing_draft_id"],
                "status": oms_listing_draft["status"],
            },
        }
        adoption.update(
            {
                "status": "executed",
                "scm_name": scm_name,
                "quantity": int(quantity),
                "supplier_code": supplier_code or adoption.get("supplier_code") or "SUP-001",
                "purchase_order_id": scm_receipt["purchase_order_id"],
                "warehouse_reservation": wms_reservation,
                "listing_draft": oms_listing_draft,
                "execution_status": execution_status,
                "executed_at": now,
                "notes": notes,
            }
        )
        task.config["adoption"] = adoption
        task.config["status_reason"] = "已采纳推荐并完成SCM/WMS/OMS执行编排"
        task.updated_at = datetime.now(UTC)
        return {
            "task_id": task_id,
            "trace_id": f"selection-adopt-{task_id}",
            "purchase_suggestion": {
                "quantity": int(quantity),
                "supplier_code": adoption["supplier_code"],
            },
            "scm_receipt": scm_receipt,
            "wms_reservation": wms_reservation,
            "oms_listing_draft": oms_listing_draft,
            "execution_status": execution_status,
            "adoption": adoption,
            "message": "采纳推荐并完成SCM/WMS/OMS执行编排",
        }


def _build_headers(*roles: str, user_id: str, username: str) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": username,
            "user_id": user_id,
            "is_superuser": False,
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "tenant_key": "default",
            "tenant_name": "Default Tenant",
            "roles": list(roles),
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_run_dir(output_root: Path) -> Path:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _status_from_checks(checks: list[CheckResult]) -> str:
    return "passed" if all(item.passed for item in checks) else "failed"


def _json_data(response: Any) -> dict[str, Any]:
    payload = response.json()
    return payload["data"] if isinstance(payload, dict) and "data" in payload else payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local selection main chain acceptance.")
    parser.add_argument("--output-root", default=str(ARTIFACT_ROOT), help="Artifact root directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    run_dir = _build_run_dir(output_root)
    clear_audit_logs()
    AcceptanceSelectionTaskService.shared_repo = _InMemorySelectionRepo()
    AcceptanceErpIntegrationService.repo = AcceptanceSelectionTaskService.shared_repo

    operation_records: list[dict[str, Any]] = []
    checks: list[CheckResult] = []

    async def _noop_init_db() -> None:
        return None

    async def _healthy_db() -> dict[str, str]:
        return {"status": "healthy"}

    async def _healthy_redis() -> dict[str, str]:
        return {"status": "healthy"}

    async def _healthy_qdrant() -> dict[str, str]:
        return {"status": "healthy"}

    async def _fake_session() -> _DummySession:
        return _DummySession()

    async def _noop_persist_audit_log(_entry: dict[str, Any]) -> None:
        return None

    operator_headers = _build_headers("operator", user_id="00000000-0000-0000-0000-000000000011", username="operator-1")
    procurement_headers = _build_headers("procurement", user_id="00000000-0000-0000-0000-000000000021", username="procurement-1")
    manager_headers = _build_headers("manager", user_id="00000000-0000-0000-0000-000000000031", username="manager-1")
    admin_headers = _build_headers("tenant_admin", user_id="00000000-0000-0000-0000-000000000041", username="tenant-admin-1")

    with ExitStack() as stack:
        stack.enter_context(patch("src.infrastructure.database.init_db", _noop_init_db))
        stack.enter_context(patch("src.infrastructure.database.check_db_health", _healthy_db))
        stack.enter_context(patch("src.infrastructure.redis.check_redis_health", _healthy_redis))
        stack.enter_context(patch("src.infrastructure.qdrant.check_qdrant_health", _healthy_qdrant))
        stack.enter_context(patch("src.core.security._persist_audit_log", _noop_persist_audit_log))
        stack.enter_context(patch("src.api.v1.endpoints.bff._get_db_session", _fake_session))
        stack.enter_context(patch("src.api.v1.endpoints.bff.SelectionTaskService", AcceptanceSelectionTaskService))
        stack.enter_context(patch("src.api.v1.endpoints.bff.ErpIntegrationService", AcceptanceErpIntegrationService))
        stack.enter_context(
            patch(
                "src.api.v1.endpoints.bff.get_settings",
                lambda: SimpleNamespace(selection_execution=SimpleNamespace(enable_api_background_dispatch=True)),
            )
        )

        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            create_response = client.post(
                "/api/v1/bff/workbench/selection/tasks",
                headers=operator_headers,
                json={
                    "query": "蓝牙耳机",
                    "category": "electronics",
                    "target_market": "US",
                    "investment_budget": 50000,
                    "priority": "high",
                    "auto_approve": False,
                },
            )
            create_data = _json_data(create_response)
            task_id = str(create_data["task_id"])
            operation_records.append(
                {
                    "step": "create_task",
                    "actor": "operator-1",
                    "request": {"method": "POST", "path": "/api/v1/bff/workbench/selection/tasks"},
                    "response_status_code": create_response.status_code,
                    "response_data": create_data,
                }
            )

            detail_after_create_response = client.get(
                f"/api/v1/bff/workbench/selection/tasks/{task_id}",
                headers=operator_headers,
            )
            detail_after_create = _json_data(detail_after_create_response)
            operation_records.append(
                {
                    "step": "detail_after_create",
                    "actor": "operator-1",
                    "request": {"method": "GET", "path": f"/api/v1/bff/workbench/selection/tasks/{task_id}"},
                    "response_status_code": detail_after_create_response.status_code,
                    "response_data": detail_after_create,
                }
            )

            approval_steps = [
                ("operator_review", "operator-1", operator_headers, "运营初审通过"),
                ("procurement_review", "procurement-1", procurement_headers, "采购复审通过"),
                ("manager_review", "manager-1", manager_headers, "管理终审通过"),
            ]
            approval_responses: list[dict[str, Any]] = []
            for stage, actor_name, headers, comment in approval_steps:
                response = client.post(
                    f"/api/v1/bff/workbench/selection/tasks/{task_id}/approve",
                    headers=headers,
                    json={
                        "action": "approve",
                        "stage": stage,
                        "comment": comment,
                        "reviewer": actor_name,
                    },
                )
                data = _json_data(response)
                approval_responses.append(data)
                operation_records.append(
                    {
                        "step": f"approve_{stage}",
                        "actor": actor_name,
                        "request": {"method": "POST", "path": f"/api/v1/bff/workbench/selection/tasks/{task_id}/approve"},
                        "response_status_code": response.status_code,
                        "response_data": data,
                    }
                )

            approval_history_response = client.get(
                f"/api/v1/bff/workbench/selection/tasks/{task_id}/approval-history",
                headers=manager_headers,
            )
            approval_history = _json_data(approval_history_response)
            operation_records.append(
                {
                    "step": "approval_history",
                    "actor": "manager-1",
                    "request": {"method": "GET", "path": f"/api/v1/bff/workbench/selection/tasks/{task_id}/approval-history"},
                    "response_status_code": approval_history_response.status_code,
                    "response_data": approval_history,
                }
            )

            intervene_response = client.post(
                f"/api/v1/bff/workbench/selection/tasks/{task_id}/intervene",
                headers=admin_headers,
                json={"action": "pause_and_review", "comment": "管理补充复核后继续推进"},
            )
            intervene_data = _json_data(intervene_response)
            operation_records.append(
                {
                    "step": "manual_intervene",
                    "actor": "tenant-admin-1",
                    "request": {"method": "POST", "path": f"/api/v1/bff/workbench/selection/tasks/{task_id}/intervene"},
                    "response_status_code": intervene_response.status_code,
                    "response_data": intervene_data,
                }
            )

            adopt_response = client.post(
                f"/api/v1/bff/workbench/selection/tasks/{task_id}/adopt",
                headers=admin_headers,
                json={
                    "scm_name": "local-scm",
                    "wms_name": "local-wms",
                    "oms_name": "local-oms",
                    "quantity": 240,
                    "supplier_code": "SUP-001",
                    "notes": "N1-01 local main chain drill",
                },
            )
            adopt_data = _json_data(adopt_response)
            operation_records.append(
                {
                    "step": "adopt_recommendation",
                    "actor": "tenant-admin-1",
                    "request": {"method": "POST", "path": f"/api/v1/bff/workbench/selection/tasks/{task_id}/adopt"},
                    "response_status_code": adopt_response.status_code,
                    "response_data": adopt_data,
                }
            )

            final_detail_response = client.get(
                f"/api/v1/bff/workbench/selection/tasks/{task_id}",
                headers=admin_headers,
            )
            final_detail = _json_data(final_detail_response)
            operation_records.append(
                {
                    "step": "final_detail",
                    "actor": "tenant-admin-1",
                    "request": {"method": "GET", "path": f"/api/v1/bff/workbench/selection/tasks/{task_id}"},
                    "response_status_code": final_detail_response.status_code,
                    "response_data": final_detail,
                }
            )

    audit_logs = list_audit_logs(target_id=task_id, limit=20)

    checks.append(
        CheckResult(
            "task_created_and_dispatched",
            create_response.status_code == 200 and detail_after_create_response.status_code == 200,
            f"create_status={create_response.status_code}, detail_status={detail_after_create_response.status_code}",
            {
                "task_id": task_id,
                "detail_status": detail_after_create.get("status"),
                "decision": ((detail_after_create.get("decision_output") or {}).get("decision") or {}).get("decision"),
            },
        )
    )
    checks.append(
        CheckResult(
            "task_execution_completed_locally",
            detail_after_create.get("status") == "completed"
            and ((detail_after_create.get("decision_output") or {}).get("decision") or {}).get("decision") == "GO",
            f"status={detail_after_create.get('status')}",
            {"status_reason": detail_after_create.get("status_reason")},
        )
    )
    checks.append(
        CheckResult(
            "multistage_approval_chain",
            all(item.get("status") in {"pending", "approved"} for item in approval_responses)
            and approval_history.get("approval", {}).get("status") == "approved"
            and approval_history.get("total") == 3,
            f"approval_total={approval_history.get('total')}",
            {"approval": approval_history.get("approval"), "approval_history": approval_history.get("approval_history")},
        )
    )
    checks.append(
        CheckResult(
            "manual_intervention_recorded",
            intervene_response.status_code == 200
            and (intervene_data.get("manual_intervention") or {}).get("action") == "pause_and_review",
            f"intervene_status={intervene_response.status_code}",
            {"manual_intervention": intervene_data.get("manual_intervention")},
        )
    )
    checks.append(
        CheckResult(
            "adoption_execution_completed",
            adopt_response.status_code == 200
            and adopt_data.get("adoption", {}).get("status") == "executed"
            and bool((adopt_data.get("scm_receipt") or {}).get("purchase_order_id"))
            and bool((adopt_data.get("wms_reservation") or {}).get("reservation_id"))
            and bool((adopt_data.get("oms_listing_draft") or {}).get("listing_draft_id")),
            f"adopt_status={adopt_response.status_code}",
            {"adoption": adopt_data.get("adoption"), "execution_status": adopt_data.get("execution_status")},
        )
    )
    checks.append(
        CheckResult(
            "final_task_detail_consistent",
            final_detail_response.status_code == 200
            and (final_detail.get("adoption") or {}).get("status") == "executed"
            and len(final_detail.get("approval_history") or []) == 3,
            f"final_status={final_detail.get('status')}",
            {"final_detail": final_detail},
        )
    )
    actions = [log.get("action") for log in audit_logs]
    checks.append(
        CheckResult(
            "audit_logs_captured",
            create_response.status_code == 200
            and actions.count("bff.selection.task.approve") == 3
            and "bff.selection.task.create" in actions
            and "bff.selection.task.intervene" in actions
            and "bff.selection.task.adopt" in actions,
            f"audit_count={len(audit_logs)}",
            {"actions": actions, "audit_logs": audit_logs},
        )
    )

    operation_path = run_dir / "operation_records.json"
    approval_history_path = run_dir / "approval_history.json"
    audit_logs_path = run_dir / "audit_logs.json"
    final_detail_path = run_dir / "final_task_detail.json"

    _write_json(operation_path, operation_records)
    _write_json(approval_history_path, approval_history)
    _write_json(audit_logs_path, audit_logs)
    _write_json(final_detail_path, final_detail)

    summary = {
        "status": _status_from_checks(checks),
        "accepted": all(item.passed for item in checks),
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "task_id": task_id,
        "checks": [item.to_dict() for item in checks],
        "artifacts": {
            "operation_records": str(operation_path),
            "approval_history": str(approval_history_path),
            "audit_logs": str(audit_logs_path),
            "final_task_detail": str(final_detail_path),
            "summary": str(run_dir / "summary.json"),
        },
    }
    _write_json(run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
