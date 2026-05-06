from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SEC_SECRET_KEY", "local-selection-close-loop-32chars")
sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient

from scripts.run_local_selection_main_chain_acceptance import (
    AcceptanceSelectionTaskService,
    CheckResult,
    _DummySession,
    _InMemorySelectionRepo,
    _build_headers,
    _build_run_dir,
    _status_from_checks,
    _write_json,
)
from src.core.security import clear_audit_logs, list_audit_logs
from src.main import create_app
from src.services.erp_integration_service import ErpIntegrationService


ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "local_close_loop"
BASELINE_ERP_LOCAL = PROJECT_ROOT / "artifacts" / "erp_local"


class _FakeFeatureEngine:
    _features: dict[str, dict[str, Any]] = {}

    async def process_event(self, payload: dict[str, Any]) -> None:
        product_id = str(payload.get("product_id"))
        sales = int(payload.get("sales") or 0)
        price = float(payload.get("price") or 0.0)
        self._features[product_id] = {
            "sales_7d": sales,
            "price": price,
            "momentum_score": round(min(100.0, sales * 4.0), 1),
            "inventory_pressure": "healthy" if sales <= 20 else "watch",
        }

    async def get_features(self, product_id: str) -> dict[str, Any] | None:
        return self._features.get(str(product_id))


class _ConfigRepo:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.logs: dict[str, SimpleNamespace] = {}

    def _erp_root(self) -> Path:
        return self.workspace_root / "artifacts" / "erp_local"

    async def create_sync_log(self, *, config_id: str, sync_type: str, entity_type: str) -> SimpleNamespace:
        now = datetime.now(UTC)
        log = SimpleNamespace(
            id=f"log-{entity_type}-{len(self.logs) + 1:03d}",
            sync_type=sync_type,
            entity_type=entity_type,
            status="running",
            items_total=0,
            items_success=0,
            items_failed=0,
            error_detail=None,
            started_at=now,
            finished_at=None,
            duration_seconds=None,
        )
        self.logs[str(log.id)] = log
        return log

    async def update_sync_log(self, log_id: str, **fields: Any) -> SimpleNamespace:
        log = self.logs[str(log_id)]
        for key, value in fields.items():
            setattr(log, key, value)
        return log

    async def get_config(self, system_type: Any, name: str = "default") -> SimpleNamespace | None:
        system_key = getattr(system_type, "value", str(system_type))
        erp_root = self._erp_root()
        mapping = {
            "scm": {
                "path": erp_root / "scm",
                "inbound_path": "/quotes.json",
                "outbound_path": "/outbound-product-plan.json",
            },
            "wms": {
                "path": erp_root / "wms",
                "inbound_path": "/inventory.json",
                "outbound_path": "/outbound-replenishment.json",
            },
            "oms": {
                "path": erp_root / "oms",
                "inbound_path": "/orders.json",
                "outbound_path": "/outbound-products.json",
            },
            "som": {
                "path": erp_root / "som",
                "inbound_path": "/listing-draft.json",
                "outbound_path": "/listing-draft.json",
            },
            "pdm": {
                "path": erp_root / "pdm",
                "inbound_path": "/recommendations.json",
                "outbound_path": "/recommendation-submission.json",
            },
            "crm": {
                "path": erp_root / "crm",
                "inbound_path": "/feedback.json",
                "outbound_path": "/outbound-followups.json",
            },
            "fms": {
                "path": erp_root / "fms",
                "inbound_path": "/profit.json",
                "outbound_path": "/outbound-profit-plan.json",
            },
        }
        target = mapping.get(system_key)
        if target is None:
            return None
        return SimpleNamespace(
            id=f"cfg-{system_key}-{name}",
            name=name,
            system_type=SimpleNamespace(value=system_key),
            api_endpoint=f"file://{target['path'].resolve().as_posix()}",
            api_key=None,
            is_active=True,
            extra_config={
                "inbound_path": target["inbound_path"],
                "outbound_path": target["outbound_path"],
                "timeout_seconds": 5,
            },
            last_sync_at=None,
        )


class LocalCloseLoopErpIntegrationService(ErpIntegrationService):
    shared_selection_repo: _InMemorySelectionRepo
    shared_config_repo: _ConfigRepo

    def __init__(self, session: Any, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session or _DummySession()
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.repo = self.shared_config_repo
        self.selection_repo = self.shared_selection_repo

    async def list_crm_logs(self, limit: int = 5, name: str = "default") -> dict[str, Any]:
        return {
            "total": 1,
            "logs": [
                {
                    "log_id": f"log-crm-{name}",
                    "config_name": name,
                    "system_type": "crm",
                    "status": "completed",
                }
            ],
        }

    async def list_bi_logs(self, limit: int = 5, name: str = "default") -> dict[str, Any]:
        return {
            "total": 1,
            "logs": [
                {
                    "log_id": f"log-bi-{name}",
                    "config_name": name,
                    "system_type": "bi",
                    "status": "completed",
                }
            ],
        }

    async def list_paas_logs(self, limit: int = 5, name: str = "default") -> dict[str, Any]:
        return {
            "total": 1,
            "logs": [
                {
                    "log_id": f"log-paas-{name}",
                    "run_id": f"run-paas-{name}",
                    "config_name": name,
                    "system_type": "paas",
                    "status": "running",
                }
            ],
        }

    async def get_paas_run_status(self, name: str = "default", run_id: str = "") -> dict[str, Any]:
        return {
            "system_type": "paas",
            "status": "running",
            "callback_expected": True,
            "retry_recommended": False,
            "run_id": run_id or f"run-paas-{name}",
        }

    async def get_wms_operational_status(self, name: str = "default") -> dict[str, Any]:
        inventory_path = self.shared_config_repo.workspace_root / "artifacts" / "erp_local" / "wms" / "inventory.json"
        payload = json.loads(inventory_path.read_text(encoding="utf-8"))
        items = payload.get("items") if isinstance(payload, dict) else payload
        rows = items if isinstance(items, list) else []
        return {
            "system_type": "wms",
            "config_name": name,
            "inventory_summary": self._summarize_wms_inventory(rows),
            "fulfillment_status": self._build_fulfillment_status(self._summarize_wms_inventory(rows)),
        }

    async def get_fms_operational_status(self, name: str = "default") -> dict[str, Any]:
        profit_path = self.shared_config_repo.workspace_root / "artifacts" / "erp_local" / "fms" / "profit.json"
        payload = json.loads(profit_path.read_text(encoding="utf-8"))
        items = payload.get("items") if isinstance(payload, dict) else payload
        rows = items if isinstance(items, list) else []
        return {
            "system_type": "fms",
            "config_name": name,
            "profit_summary": self._summarize_fms_profit_facts(rows),
            "profit_trace_ready": True,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local selection close-loop acceptance.")
    parser.add_argument("--output-root", default=str(ARTIFACT_ROOT), help="Artifact root directory")
    return parser.parse_args()


def _json_data(response: Any) -> dict[str, Any]:
    payload = response.json()
    return payload["data"] if isinstance(payload, dict) and "data" in payload else payload


def main() -> int:
    args = parse_args()
    run_dir = _build_run_dir(Path(args.output_root))
    workspace_root = run_dir / "workspace"
    workspace_erp_root = workspace_root / "artifacts" / "erp_local"
    workspace_erp_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASELINE_ERP_LOCAL, workspace_erp_root, dirs_exist_ok=True)
    pdm_dir = workspace_erp_root / "pdm"
    pdm_dir.mkdir(parents=True, exist_ok=True)
    (pdm_dir / "recommendations.json").write_text('{"items": []}', encoding="utf-8")

    clear_audit_logs()
    AcceptanceSelectionTaskService.shared_repo = _InMemorySelectionRepo()
    LocalCloseLoopErpIntegrationService.shared_selection_repo = AcceptanceSelectionTaskService.shared_repo
    LocalCloseLoopErpIntegrationService.shared_config_repo = _ConfigRepo(workspace_root)
    _FakeFeatureEngine._features = {}

    operation_records: list[dict[str, Any]] = []

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
        stack.enter_context(patch("src.api.v1.endpoints.bff.ErpIntegrationService", LocalCloseLoopErpIntegrationService))
        stack.enter_context(
            patch(
                "src.api.v1.endpoints.bff.get_settings",
                lambda: SimpleNamespace(selection_execution=SimpleNamespace(enable_api_background_dispatch=True)),
            )
        )
        stack.enter_context(patch("src.services.selection_service.FeatureEngine", _FakeFeatureEngine))

        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            create_response = client.post(
                "/api/v1/bff/workbench/selection/tasks",
                headers=operator_headers,
                json={
                    "query": "蓝牙耳机企业联调样本",
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
                    "response_status_code": create_response.status_code,
                    "response_data": create_data,
                }
            )

            execution_context = SimpleNamespace(
                task_id=task_id,
                tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
                query="蓝牙耳机企业联调样本",
                category="electronics",
                investment_budget=50000,
                target_market="US",
                auto_approve=False,
                priority="high",
            )
            execution_service = AcceptanceSelectionTaskService(_DummySession(), tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca")
            client.app.dependency_overrides.clear()
            asyncio.run(execution_service.submit_task_for_execution(execution_context))
            executed_task = AcceptanceSelectionTaskService.shared_repo.tasks[UUID(task_id)]
            executed_task.config["execution_result"]["decision_output"]["product"]["asin"] = task_id
            executed_task.config["execution_result"]["decision_output"]["supply_chain"]["primary_supplier"] = "SUP-ERP-001"

            for stage, actor_name, headers, comment in [
                ("operator_review", "operator-1", operator_headers, "运营初审通过"),
                ("procurement_review", "procurement-1", procurement_headers, "采购复审通过"),
                ("manager_review", "manager-1", manager_headers, "管理终审通过"),
            ]:
                response = client.post(
                    f"/api/v1/bff/workbench/selection/tasks/{task_id}/approve",
                    headers=headers,
                    json={"action": "approve", "stage": stage, "comment": comment, "reviewer": actor_name},
                )
                operation_records.append(
                    {
                        "step": f"approve_{stage}",
                        "actor": actor_name,
                        "response_status_code": response.status_code,
                        "response_data": _json_data(response),
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
                    "supplier_code": "SUP-ERP-001",
                    "notes": "N1-04 local close loop drill",
                },
            )
            adopt_data = _json_data(adopt_response)
            operation_records.append(
                {
                    "step": "adopt_recommendation",
                    "actor": "tenant-admin-1",
                    "response_status_code": adopt_response.status_code,
                    "response_data": adopt_data,
                }
            )

            feedback_sync_response = client.post(
                f"/api/v1/bff/workbench/selection/tasks/{task_id}/execution-feedback-sync",
                headers=admin_headers,
                json={
                    "oms_name": "local-oms",
                    "crm_name": "local-crm",
                    "fms_name": "local-fms",
                    "wms_name": "local-wms",
                    "auto_rescore": True,
                },
            )
            feedback_sync_data = _json_data(feedback_sync_response)
            operation_records.append(
                {
                    "step": "execution_feedback_sync",
                    "actor": "tenant-admin-1",
                    "response_status_code": feedback_sync_response.status_code,
                    "response_data": feedback_sync_data,
                }
            )

            feedback_loop_status_response = client.get(
                f"/api/v1/bff/workbench/selection/tasks/{task_id}/feedback-loop-status",
                headers=admin_headers,
                params={"crm_name": "local-crm", "paas_name": "local-paas"},
            )
            feedback_loop_status = _json_data(feedback_loop_status_response)
            operation_records.append(
                {
                    "step": "feedback_loop_status",
                    "actor": "tenant-admin-1",
                    "response_status_code": feedback_loop_status_response.status_code,
                    "response_data": feedback_loop_status,
                }
            )

            profit_trace_response = client.get(
                f"/api/v1/bff/workbench/selection/tasks/{task_id}/profit-trace",
                headers=admin_headers,
                params={
                    "crm_name": "local-crm",
                    "fms_name": "local-fms",
                    "wms_name": "local-wms",
                    "paas_name": "local-paas",
                },
            )
            profit_trace = _json_data(profit_trace_response)
            operation_records.append(
                {
                    "step": "profit_trace",
                    "actor": "tenant-admin-1",
                    "response_status_code": profit_trace_response.status_code,
                    "response_data": profit_trace,
                }
            )

            feature_asset_response = client.get(
                f"/api/v1/bff/workbench/selection/tasks/{task_id}/feedback-feature-asset",
                headers=admin_headers,
            )
            feature_asset = _json_data(feature_asset_response)
            operation_records.append(
                {
                    "step": "feedback_feature_asset",
                    "actor": "tenant-admin-1",
                    "response_status_code": feature_asset_response.status_code,
                    "response_data": feature_asset,
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
                    "response_status_code": final_detail_response.status_code,
                    "response_data": final_detail,
                }
            )

    audit_logs = list_audit_logs(target_id=task_id, limit=20)
    pdm_outbound_path = workspace_root / "artifacts" / "erp_local" / "pdm" / "recommendation-submission.json"
    scm_outbound_path = workspace_root / "artifacts" / "erp_local" / "scm" / "outbound-product-plan.json"
    wms_outbound_path = workspace_root / "artifacts" / "erp_local" / "wms" / "outbound-replenishment.json"
    som_listing_draft_path = workspace_root / "artifacts" / "erp_local" / "som" / "listing-draft.json"

    adopt_payload = adopt_data if isinstance(adopt_data, dict) else {}
    checks = [
        CheckResult(
            "adoption_execution_completed",
            adopt_response.status_code == 200
            and adopt_payload.get("status") == "completed"
            and adopt_payload.get("adoption", {}).get("status") == "executed"
            and pdm_outbound_path.exists()
            and scm_outbound_path.exists()
            and wms_outbound_path.exists()
            and som_listing_draft_path.exists(),
            f"adopt_status={adopt_response.status_code}",
            {
                "adopt_response": adopt_payload,
                "recommendation_id": (adopt_payload.get("pdm_receipt") or {}).get("recommendation_id"),
                "purchase_order_id": (adopt_payload.get("scm_receipt") or {}).get("purchase_order_id"),
                "reservation_id": (adopt_payload.get("wms_reservation") or {}).get("reservation_id"),
                "listing_draft_id": (adopt_payload.get("som_listing_draft") or {}).get("listing_draft_id"),
            },
        ),
        CheckResult(
            "execution_feedback_synced",
            feedback_sync_response.status_code == 200
            and ((feedback_sync_data.get("execution_feedback_snapshot") or {}).get("sales") or {}).get("orders", {}).get("units") == 12
            and ((feedback_sync_data.get("execution_feedback_snapshot") or {}).get("reviews") or {}).get("avg_rating") == 4.6
            and ((feedback_sync_data.get("execution_feedback_snapshot") or {}).get("profit") or {}).get("gross_profit_total") == 139.0
            and ((feedback_sync_data.get("execution_feedback_snapshot") or {}).get("inventory") or {}).get("summary", {}).get("available_quantity_total") == 18,
            f"sync_status={feedback_sync_response.status_code}",
            {"execution_feedback_snapshot": feedback_sync_data.get("execution_feedback_snapshot")},
        ),
        CheckResult(
            "rescore_persisted_to_task",
            ((feedback_sync_data.get("rescore_result") or {}).get("rescore_summary") or {}).get("decision") == "GO"
            and (((final_detail.get("decision_output") or {}).get("rescore_summary") or {}).get("decision") == "GO")
            and ((((final_detail.get("decision_output") or {}).get("execution_feedback") or {}).get("sales") or {}).get("sales_7d") == 12),
            f"final_status={final_detail.get('status')}",
            {
                "rescore_summary": (final_detail.get("decision_output") or {}).get("rescore_summary"),
                "execution_feedback": (final_detail.get("decision_output") or {}).get("execution_feedback"),
            },
        ),
        CheckResult(
            "feature_asset_ready",
            feature_asset_response.status_code == 200
            and (feature_asset.get("feature_asset") or {}).get("asset_type") == "feedback_feature_asset"
            and final_detail.get("execution_feedback_snapshot") is not None,
            f"feature_asset_status={feature_asset_response.status_code}",
            {"feature_asset": feature_asset.get("feature_asset")},
        ),
        CheckResult(
            "feedback_loop_status_ready",
            feedback_loop_status_response.status_code == 200
            and (feedback_loop_status.get("selection_feedback_loop") or {}).get("auto_rescore_completed") is True
            and (feedback_loop_status.get("selection_feedback_loop") or {}).get("feature_asset_ready") is True
            and ((feedback_loop_status.get("bi") or {}).get("task_metrics") or {}).get("decision") == "GO",
            f"feedback_loop_status={feedback_loop_status_response.status_code}",
            {"feedback_loop_status": feedback_loop_status},
        ),
        CheckResult(
            "profit_trace_ready",
            profit_trace_response.status_code == 200
            and profit_trace.get("ready") is True
            and (profit_trace.get("profit_contract") or {}).get("gross_profit_total") == 139.0
            and (profit_trace.get("profit_contract") or {}).get("inventory_available") == 18,
            f"profit_trace_status={profit_trace_response.status_code}",
            {"profit_trace": profit_trace},
        ),
        CheckResult(
            "audit_logs_captured",
            "bff.selection.task.adopt" in [log.get("action") for log in audit_logs]
            and "bff.selection.task.execution_feedback_sync" in [log.get("action") for log in audit_logs],
            f"audit_count={len(audit_logs)}",
            {"actions": [log.get("action") for log in audit_logs]},
        ),
    ]

    operation_path = run_dir / "operation_records.json"
    feedback_loop_path = run_dir / "feedback_loop_status.json"
    profit_trace_path = run_dir / "profit_trace.json"
    feature_asset_path = run_dir / "feature_asset.json"
    final_detail_path = run_dir / "final_task_detail.json"
    audit_logs_path = run_dir / "audit_logs.json"

    _write_json(operation_path, operation_records)
    _write_json(feedback_loop_path, feedback_loop_status)
    _write_json(profit_trace_path, profit_trace)
    _write_json(feature_asset_path, feature_asset)
    _write_json(final_detail_path, final_detail)
    _write_json(audit_logs_path, audit_logs)

    summary = {
        "status": _status_from_checks(checks),
        "accepted": all(item.passed for item in checks),
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "workspace_root": str(workspace_root),
        "task_id": task_id,
        "checks": [item.to_dict() for item in checks],
        "artifacts": {
            "operation_records": str(operation_path),
            "feedback_loop_status": str(feedback_loop_path),
            "profit_trace": str(profit_trace_path),
            "feature_asset": str(feature_asset_path),
            "final_task_detail": str(final_detail_path),
            "audit_logs": str(audit_logs_path),
            "summary": str(run_dir / "summary.json"),
        },
    }
    _write_json(run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
