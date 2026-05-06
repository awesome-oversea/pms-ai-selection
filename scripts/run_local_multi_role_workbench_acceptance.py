from __future__ import annotations

import argparse
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

os.environ.setdefault("SEC_SECRET_KEY", "local-multi-role-workbench-32chars")
sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient

from scripts.run_local_selection_close_loop_acceptance import (
    BASELINE_ERP_LOCAL,
    LocalCloseLoopErpIntegrationService,
    _ConfigRepo,
    _FakeFeatureEngine,
)
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
from src.core.auth import create_access_token
from src.core.security import clear_audit_logs, list_audit_logs
from src.main import create_app
from src.models.enums import TaskStatus


ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "local_multi_role_workbench"
DEFAULT_TENANT_ID = "86d1f796-7c55-57a1-ac77-2e952a2111ca"


class AcceptanceMultiRoleSelectionTaskService(AcceptanceSelectionTaskService):
    async def submit_task_for_execution(self, context: Any) -> None:
        task = await self.repo.get_task(UUID(str(context.task_id)))
        if task is None:
            return

        now = datetime.now(UTC)
        config = task.config or {}
        recommended_price = 39.99
        expected_roi = 31.8
        config["execution_result"] = {
            "decision_output": {
                "market_summary": {
                    "trend_direction": "up",
                    "market_size_index": 0.84,
                    "competition_intensity": "medium",
                    "keyword_velocity": 1.21,
                },
                "decision": {
                    "decision": "GO",
                    "confidence": 0.93,
                    "recommendation": "蓝牙耳机 Pro 2",
                },
                "product": {
                    "name": "蓝牙耳机 Pro 2",
                    "asin": "B0LOCALROLE001",
                    "product_id": "selection-task-local-role-001",
                },
                "pricing": {
                    "recommended_price": recommended_price,
                    "currency": "USD",
                    "cost_price": 26.5,
                },
                "profitability": {
                    "expected_roi": expected_roi,
                    "roi_year1_percent": expected_roi,
                    "expected_margin": 0.274,
                    "expected_gross_profit": 139.0,
                },
                "supply_chain": {
                    "primary_supplier": "SUP-LOCAL-001",
                    "supplier_name": "Shenzhen SoundMax Factory",
                    "lead_time_days": 7,
                    "moq": 120,
                },
                "top_recommendations": [
                    {
                        "rank": 1,
                        "product_name": "蓝牙耳机 Pro 2",
                        "score": 92.4,
                        "reason": "高复购、评价稳定、供应履约可控",
                    },
                    {
                        "rank": 2,
                        "product_name": "开放式运动耳机 Lite",
                        "score": 87.9,
                        "reason": "趋势增长快，但利润弹性略弱",
                    },
                ],
                "risks": [
                    {"type": "competition", "level": "medium", "mitigation": "先做差异化包装"},
                    {"type": "inventory", "level": "low", "mitigation": "先走小批量首单"},
                ],
                "execution_summary": {
                    "steps": [
                        "collect_market_signals",
                        "score_candidate",
                        "prepare_recommendation",
                        "handoff_to_multirole_workbench",
                    ],
                    "next_action": "operator_review",
                },
            },
            "state_summary": {
                "current_phase": "completed",
                "completed": True,
            },
        }
        config["pilot_scenario"] = {
            "scenario_id": "phase4-local-multi-role-bluetooth-headset",
            "scenario_name": "蓝牙耳机美国站多角色试点",
        }
        config["status_reason"] = "选品建议已生成，进入多角色联动作业"
        task.status = TaskStatus.COMPLETED
        task.result_summary = "多角色联动作业建议已生成"
        task.updated_at = now
        task.completed_at = now
        task.config = config


class LocalMultiRoleWorkbenchErpIntegrationService(LocalCloseLoopErpIntegrationService):
    def _iter_tasks(self) -> list[Any]:
        return sorted(
            self.shared_selection_repo.tasks.values(),
            key=lambda item: item.updated_at or item.created_at,
            reverse=True,
        )

    def _latest_task(self) -> Any | None:
        tasks = self._iter_tasks()
        return tasks[0] if tasks else None

    def _latest_adopted_task(self) -> Any | None:
        for task in self._iter_tasks():
            adoption = (task.config or {}).get("adoption")
            if isinstance(adoption, dict) and adoption:
                return task
        return None

    def _build_log_rows(self, *, system_type: str, name: str, limit: int) -> dict[str, Any]:
        task = self._latest_adopted_task()
        if task is None:
            return {"total": 0, "logs": []}
        adoption = (task.config or {}).get("adoption") or {}
        execution_status = adoption.get("execution_status") or {}
        status_payload = execution_status.get(system_type) or {}
        rows = [
            {
                "log_id": f"log-{system_type}-{str(task.id)[:8]}",
                "config_name": name,
                "system_type": system_type,
                "task_id": str(task.id),
                "status": status_payload.get("status") or "completed",
                "purchase_order_id": adoption.get("purchase_order_id"),
                "reservation_id": ((adoption.get("warehouse_reservation") or {}).get("reservation_id")),
                "listing_draft_id": ((adoption.get("listing_draft") or {}).get("listing_draft_id")),
                "occurred_at": adoption.get("executed_at") or task.updated_at.isoformat(),
            }
        ]
        return {"total": len(rows), "logs": rows[:limit]}

    async def list_scm_logs(self, limit: int = 20, name: str = "default") -> dict[str, Any]:
        return self._build_log_rows(system_type="scm", name=name, limit=limit)

    async def list_wms_logs(self, limit: int = 20, name: str = "default") -> dict[str, Any]:
        return self._build_log_rows(system_type="wms", name=name, limit=limit)

    async def list_oms_logs(self, limit: int = 20, name: str = "default") -> dict[str, Any]:
        return self._build_log_rows(system_type="oms", name=name, limit=limit)

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
        result = await super().execute_selection_adoption(
            task_id=task_id,
            scm_name=scm_name,
            wms_name=wms_name,
            oms_name=oms_name,
            quantity=quantity,
            supplier_code=supplier_code,
            notes=notes,
        )
        task = await self.shared_selection_repo.get_task(UUID(task_id))
        if task is None:
            return result
        decision_output = ((task.config or {}).get("execution_result") or {}).get("decision_output") or {}
        recommended_price = float((decision_output.get("pricing") or {}).get("recommended_price") or 39.99)
        adoption = dict((task.config or {}).get("adoption") or {})
        adoption["supplier_name"] = "Shenzhen SoundMax Factory"
        adoption["total_amount"] = round(float(quantity) * recommended_price, 2)
        adoption["expected_roi"] = (decision_output.get("profitability") or {}).get("expected_roi")
        adoption["expected_margin_rate"] = (decision_output.get("profitability") or {}).get("expected_margin")
        task.config["adoption"] = adoption
        result["adoption"] = adoption
        result["purchase_suggestion"]["estimated_total_amount"] = adoption["total_amount"]
        return result

    async def get_scm_operational_status(self, name: str = "default") -> dict[str, Any]:
        task = self._latest_adopted_task()
        if task is None:
            return {
                "system_type": "scm",
                "config_name": name,
                "status": "idle",
                "purchase_order_ready": False,
            }
        adoption = (task.config or {}).get("adoption") or {}
        execution_status = adoption.get("execution_status") or {}
        scm_status = execution_status.get("scm") or {}
        return {
            "system_type": "scm",
            "config_name": name,
            "status": scm_status.get("status") or "pending_review",
            "purchase_order_ready": bool(adoption.get("purchase_order_id")),
            "purchase_order_id": adoption.get("purchase_order_id"),
            "supplier_code": adoption.get("supplier_code"),
            "supplier_name": adoption.get("supplier_name"),
            "lead_time_days": 7,
        }

    async def get_oms_operational_status(self, name: str = "default") -> dict[str, Any]:
        task = self._latest_adopted_task()
        if task is None:
            return {
                "system_type": "oms",
                "config_name": name,
                "listing_status": "idle",
            }
        adoption = (task.config or {}).get("adoption") or {}
        execution_status = adoption.get("execution_status") or {}
        oms_status = execution_status.get("oms") or {}
        listing_draft = adoption.get("listing_draft") or {}
        return {
            "system_type": "oms",
            "config_name": name,
            "listing_status": oms_status.get("status") or "draft_created",
            "listing_draft_id": listing_draft.get("listing_draft_id"),
            "listing_ready": bool(listing_draft.get("listing_draft_id")),
        }

    async def get_wms_operational_status(self, name: str = "default") -> dict[str, Any]:
        result = await super().get_wms_operational_status(name=name)
        task = self._latest_adopted_task()
        if task is None:
            return result
        adoption = (task.config or {}).get("adoption") or {}
        result["reservation"] = adoption.get("warehouse_reservation")
        return result

    async def get_latest_daily_selection_kpis(self, *, name: str = "default") -> dict[str, Any] | None:
        task = self._latest_adopted_task()
        if task is None:
            return None
        config = task.config or {}
        execution_result = config.get("execution_result") if isinstance(config, dict) else {}
        decision_output = execution_result.get("decision_output") if isinstance(execution_result, dict) else {}
        feedback_snapshot = (
            execution_result.get("execution_feedback_snapshot")
            if isinstance(execution_result, dict) and isinstance(execution_result.get("execution_feedback_snapshot"), dict)
            else {}
        )
        adoption = config.get("adoption") if isinstance(config.get("adoption"), dict) else {}
        sales = feedback_snapshot.get("sales") if isinstance(feedback_snapshot.get("sales"), dict) else {}
        orders = sales.get("orders") if isinstance(sales.get("orders"), dict) else {}
        reviews = feedback_snapshot.get("reviews") if isinstance(feedback_snapshot.get("reviews"), dict) else {}
        profit = feedback_snapshot.get("profit") if isinstance(feedback_snapshot.get("profit"), dict) else {}
        inventory = feedback_snapshot.get("inventory") if isinstance(feedback_snapshot.get("inventory"), dict) else {}
        profitability = decision_output.get("profitability") if isinstance(decision_output.get("profitability"), dict) else {}
        kpi_date = str(task.updated_at.date().isoformat())
        row = {
            "task_id": str(task.id),
            "query": task.title,
            "decision": ((decision_output.get("decision") or {}).get("decision")),
            "orders_units": int(orders.get("units") or 0),
            "avg_rating": float(reviews.get("avg_rating") or 0.0),
            "gross_profit_total": float(profit.get("gross_profit_total") or 0.0),
            "inventory_available": int(((inventory.get("summary") or {}).get("available_quantity_total") or 0)),
            "roi_year1_percent": float(profitability.get("roi_year1_percent") or profitability.get("expected_roi") or 0.0),
            "purchase_order_id": adoption.get("purchase_order_id"),
        }
        return {
            "dataset_name": "selection_daily_kpis",
            "kpi_date": kpi_date,
            "summary": {
                "task_count": 1,
                "go_count": 1 if row["decision"] == "GO" else 0,
                "gross_profit_total": row["gross_profit_total"],
                "orders_units": row["orders_units"],
                "avg_rating": row["avg_rating"],
            },
            "rows": [row],
            "source": "local_multi_role_workbench",
            "config_name": name,
        }


class FakeConfigOperationsService:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def build_status(self) -> dict[str, Any]:
        return {
            "config_total": 6,
            "feature_flag_total": 3,
            "recent_versions": [
                {"config_key": "selection.pipeline", "version": 3, "description": "本地试点配置"},
                {"config_key": "workbench.manager", "version": 2, "description": "管理看板口径"},
            ],
        }


class FakeTenantOperationsService:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def build_status(self) -> dict[str, Any]:
        return {
            "total": 1,
            "tenants": [
                {
                    "tenant_id": DEFAULT_TENANT_ID,
                    "tenant_key": "default",
                    "name": "Default Tenant",
                    "status": "active",
                    "is_active": True,
                    "quota_status": [
                        {
                            "quota_type": "llm_cost_usd",
                            "remaining": 72.5,
                            "limit_value": 100.0,
                            "used_value": 27.5,
                        }
                    ],
                    "isolation_summary": {
                        "tenant_scoped": True,
                        "quota_governed": True,
                    },
                }
            ],
        }


class FakeAuditOperationsService:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def build_status(self) -> dict[str, Any]:
        recent_logs = list_audit_logs(limit=10)
        return {
            "total": len(recent_logs),
            "recent_actions": [
                {
                    "action": log.get("action"),
                    "username": ((log.get("actor") or {}).get("username")),
                    "result": log.get("result"),
                    "occurred_at": log.get("timestamp"),
                }
                for log in recent_logs[:5]
            ],
            "supported_filters": ["username", "action", "request_id", "trace_id", "target_id"],
            "trace_query_ready": True,
        }

    async def query_logs(
        self,
        *,
        username: str | None = None,
        target_id: str | None = None,
        action: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        logs = list_audit_logs(
            username=username,
            target_id=target_id,
            action=action,
            request_id=request_id,
            trace_id=trace_id,
            limit=limit,
        )
        return {
            "total": len(logs),
            "source": "in_memory_audit",
            "logs": logs,
            "filters": {
                "username": username,
                "target_id": target_id,
                "action": action,
                "request_id": request_id,
                "trace_id": trace_id,
                "limit": limit,
            },
        }


class FakeReleaseManagementService:
    def build_status(self) -> dict[str, Any]:
        return {
            "delivery_readiness": {
                "ready_for_deploy": True,
                "ready_for_cutover": True,
                "latest_gate_status": "passed",
                "blocking_reasons": [],
            }
        }


class FakeSecurityBaselineService:
    def build_status(self) -> dict[str, Any]:
        return {
            "explicit_tenant_required": True,
            "llm_protection": {
                "ip_allowlist_enabled": True,
                "prompt_guard_enabled": True,
            },
        }


class FakeLLMGovernanceService:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def build_status(self) -> dict[str, Any]:
        return {
            "quota": {
                "configured": True,
                "quota_type": "llm_cost_usd",
                "limit_value": 100.0,
                "used_value": 27.5,
                "remaining": 72.5,
                "reset_period": "monthly",
                "is_active": True,
            },
            "prompt_governance": {
                "prompt_total": 4,
                "recent_versions": [
                    {"prompt_key": "selection-summary", "version": 3, "description": "选品摘要模板"},
                    {"prompt_key": "manager-risk-review", "version": 2, "description": "管理审批模板"},
                ],
            },
            "route_policy": {
                "configured": True,
                "version": 2,
                "gray_rollout_percent": 20,
                "default_force_tier": "light",
            },
            "audit": {
                "prompt_audit_ready": True,
                "cost_trace_ready": True,
                "quota_enforcement_ready": True,
            },
        }


class FakeGatewayGovernanceService:
    def _payload(self) -> dict[str, Any]:
        return {
            "canary_release": {
                "strategy": "weighted",
                "routes": [
                    {
                        "route_name": "selection-workbench",
                        "traffic_split": {"stable": 90, "canary": 10},
                    }
                ],
            }
        }

    def build_status(self) -> dict[str, Any]:
        return self._payload()

    def get_status(self) -> dict[str, Any]:
        return self._payload()


class FakeMetricsDashboardService:
    async def build_dashboard(self) -> dict[str, Any]:
        return {
            "technical": {
                "observability_runtime": {
                    "grafana_import": {
                        "dashboard_tool": "grafana",
                        "dashboards": [
                            {
                                "title": "PMS Local Pilot Dashboard",
                                "source_artifact": "artifacts/ops/metrics_dashboard.json",
                                "import_mode": "file",
                            }
                        ],
                    }
                }
            }
        }


class FakeDataPlatformRuntimeService:
    def build_status(self) -> dict[str, Any]:
        return {
            "scheduler": {
                "scheduler": "local-cron",
                "jobs": [{"job_key": "selection-daily-kpi"}, {"job_key": "audit-governance-export"}],
            },
            "kettle": {
                "etl_engine": "kettle-compatible",
                "pipelines": [{"pipeline_key": "selection_profit_pipeline"}],
            },
            "ray_embedding": {
                "engine": "ray-compatible",
                "status": "ready",
                "target_qps": 120,
                "runner": "local-runner",
                "workload": "vector-refresh",
            },
            "processing_engines": {
                "batch_engine": {
                    "scheduler_manifest": {
                        "scheduler": "local-cron",
                        "jobs": [{"job_key": "selection-daily-kpi"}],
                    },
                    "kettle_etl_manifest": {
                        "etl_engine": "kettle-compatible",
                        "pipelines": [{"pipeline_key": "selection_profit_pipeline"}],
                    },
                }
            },
        }


class FakeOperationsGovernanceOverviewService:
    def build_status(self) -> dict[str, Any]:
        return {
            "status": "ready",
            "business_config_governance": {
                "latest_execution": {
                    "last_executed_at": datetime.now(UTC).isoformat(),
                    "last_result_ok": True,
                    "summary": {
                        "exported_config_count": 6,
                        "acceptance_ok": True,
                        "rollback_ok": True,
                        "verified_config_count": 6,
                    },
                }
            },
            "rag_governance": {
                "latest_execution": {
                    "last_executed_at": datetime.now(UTC).isoformat(),
                    "last_result_ok": True,
                    "summary": {
                        "feedback_learning_ok": True,
                        "evaluation_ok": True,
                        "dashboard_ok": True,
                        "evaluated_case_count": 4,
                        "feedback_case_count": 3,
                    },
                }
            },
        }


class FakeCaptchaOCRService:
    def recognize(self, image_base64: str | None = None, image_text_hint: str | None = None) -> dict[str, Any]:
        if image_base64:
            recognized = "captcha-from-base64"
        else:
            recognized = "".join(char for char in str(image_text_hint or "").lower() if char.isalnum())
        return {
            "recognized_text": recognized,
            "mode": "text_hint" if image_text_hint else "base64",
            "confidence": 0.98,
        }


def _build_superuser_headers(*roles: str, user_id: str, username: str) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": username,
            "user_id": user_id,
            "is_superuser": True,
            "tenant_id": DEFAULT_TENANT_ID,
            "tenant_key": "default",
            "tenant_name": "Default Tenant",
            "roles": list(roles),
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _json_data(response: Any) -> dict[str, Any]:
    payload = response.json()
    return payload["data"] if isinstance(payload, dict) and "data" in payload else payload


def _record_response(
    operation_records: list[dict[str, Any]],
    *,
    step: str,
    actor: str,
    response: Any,
    path: str,
    method: str,
    request_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _json_data(response)
    operation_records.append(
        {
            "step": step,
            "actor": actor,
            "request": {
                "method": method,
                "path": path,
                "payload": request_payload,
            },
            "response_status_code": response.status_code,
            "response_data": payload,
        }
    )
    return payload


def _serialize_tasks_for_reporting() -> list[dict[str, Any]]:
    service = AcceptanceMultiRoleSelectionTaskService(_DummySession(), tenant_id=DEFAULT_TENANT_ID, actor={"tenant_id": DEFAULT_TENANT_ID})
    tasks = sorted(
        AcceptanceMultiRoleSelectionTaskService.shared_repo.tasks.values(),
        key=lambda item: item.updated_at or item.created_at,
        reverse=True,
    )
    return [service._serialize_task(task) for task in tasks]


def _build_selection_dashboard_payload() -> dict[str, Any]:
    tasks = _serialize_tasks_for_reporting()
    latest = tasks[0] if tasks else {}
    decision_output = latest.get("decision_output") if isinstance(latest.get("decision_output"), dict) else {}
    profitability = decision_output.get("profitability") if isinstance(decision_output.get("profitability"), dict) else {}
    execution_feedback = latest.get("execution_feedback_snapshot") if isinstance(latest.get("execution_feedback_snapshot"), dict) else {}
    sales = execution_feedback.get("sales") if isinstance(execution_feedback.get("sales"), dict) else {}
    orders = sales.get("orders") if isinstance(sales.get("orders"), dict) else {}
    adoption = latest.get("adoption") if isinstance(latest.get("adoption"), dict) else {}
    gmv = round(float(orders.get("units") or 0) * float((decision_output.get("pricing") or {}).get("recommended_price") or 39.99), 2)
    completion_rate = round((sum(1 for task in tasks if task.get("status") == "completed") / len(tasks)) * 100, 2) if tasks else 0.0
    roi = float(profitability.get("roi_year1_percent") or profitability.get("expected_roi") or 0.0)
    return {
        "summary": {
            "overall_status": "loop_closed_ready" if latest.get("execution_feedback_snapshot") else "approval_in_progress",
            "gmv": gmv,
            "completion_rate": completion_rate,
            "loop_closed": bool(latest.get("execution_feedback_snapshot")),
            "data_source": "local_multi_role_workbench",
            "updated_at": latest.get("updated_at"),
            "report_title": latest.get("query"),
            "report_count": len(tasks),
        },
        "filters": ["time_window", "role_view", "data_source"],
        "charts": {
            "trend_chart": {
                "type": "line",
                "title": "经营趋势",
                "xAxis": ["审批", "采纳", "回流"],
                "series": [72, 86, 94],
            },
            "profit_chart": {
                "type": "bar",
                "title": "利润 / ROI",
                "xAxis": ["GMV", "ROI", "利润"],
                "series": [
                    gmv,
                    roi,
                    float(((execution_feedback.get("profit") or {}).get("gross_profit_total") or 0.0)),
                ],
            },
            "risk_chart": {
                "type": "pie",
                "title": "经营风险分布",
                "items": [
                    {"name": "供应可控", "value": 1},
                    {"name": "竞争风险", "value": len(decision_output.get("risks") or [])},
                    {"name": "履约异常", "value": 0},
                ],
            },
            "competitor_chart": {
                "type": "ranking",
                "title": "推荐商品优先级",
                "items": [
                    {"name": item.get("product_name") or item.get("name") or "unknown", "value": float(item.get("score") or 0)}
                    for item in (decision_output.get("top_recommendations") or [])
                ],
            },
            "execution_chart": {
                "type": "progress",
                "title": "业务闭环进度",
                "items": [
                    {"name": "审批完成", "value": 100 if (latest.get("approval") or {}).get("status") == "approved" else 60},
                    {"name": "采纳执行", "value": 100 if adoption.get("status") == "executed" else 0},
                    {"name": "经营回流", "value": 100 if latest.get("execution_feedback_snapshot") else 0},
                ],
            },
        },
        "highlights": {
            "task_id": latest.get("task_id"),
            "query": latest.get("query"),
            "supplier_code": adoption.get("supplier_code"),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local multi-role workbench acceptance.")
    parser.add_argument("--output-root", default=str(ARTIFACT_ROOT), help="Artifact root directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = _build_run_dir(Path(args.output_root))
    workspace_root = run_dir / "workspace"
    workspace_erp_root = workspace_root / "artifacts" / "erp_local"
    workspace_erp_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASELINE_ERP_LOCAL, workspace_erp_root, dirs_exist_ok=True)

    clear_audit_logs()
    AcceptanceMultiRoleSelectionTaskService.shared_repo = _InMemorySelectionRepo()
    LocalMultiRoleWorkbenchErpIntegrationService.shared_selection_repo = AcceptanceMultiRoleSelectionTaskService.shared_repo
    LocalMultiRoleWorkbenchErpIntegrationService.shared_config_repo = _ConfigRepo(workspace_root)
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

    def _fake_session_factory() -> Any:
        return lambda: _DummySession()

    async def _noop_persist_audit_log(_entry: dict[str, Any]) -> None:
        return None

    operator_headers = _build_headers("operator", user_id="00000000-0000-0000-0000-000000000011", username="operator-1")
    procurement_headers = _build_headers("procurement", user_id="00000000-0000-0000-0000-000000000021", username="procurement-1")
    manager_headers = _build_headers("manager", user_id="00000000-0000-0000-0000-000000000031", username="manager-1")
    finance_headers = _build_superuser_headers("finance", user_id="00000000-0000-0000-0000-000000000041", username="finance-1")
    operations_headers = _build_superuser_headers("tenant_admin", "operations", user_id="00000000-0000-0000-0000-000000000051", username="ops-admin-1")

    with ExitStack() as stack:
        stack.enter_context(patch("src.infrastructure.database.init_db", _noop_init_db))
        stack.enter_context(patch("src.infrastructure.database.check_db_health", _healthy_db))
        stack.enter_context(patch("src.infrastructure.redis.check_redis_health", _healthy_redis))
        stack.enter_context(patch("src.infrastructure.qdrant.check_qdrant_health", _healthy_qdrant))
        stack.enter_context(patch("src.core.security._persist_audit_log", _noop_persist_audit_log))
        stack.enter_context(patch("src.api.v1.endpoints.bff._get_db_session", _fake_session))
        stack.enter_context(patch("src.api.v1.endpoints.bff.SelectionTaskService", AcceptanceMultiRoleSelectionTaskService))
        stack.enter_context(patch("src.api.v1.endpoints.bff.ErpIntegrationService", LocalMultiRoleWorkbenchErpIntegrationService))
        stack.enter_context(
            patch(
                "src.api.v1.endpoints.bff.get_settings",
                lambda: SimpleNamespace(selection_execution=SimpleNamespace(enable_api_background_dispatch=True)),
            )
        )
        stack.enter_context(patch("src.api.v1.endpoints.integration.get_async_session_factory", _fake_session_factory))
        stack.enter_context(patch("src.api.v1.endpoints.integration.ErpIntegrationService", LocalMultiRoleWorkbenchErpIntegrationService))
        stack.enter_context(patch("src.api.v1.endpoints.system.get_async_session_factory", _fake_session_factory))
        stack.enter_context(patch("src.api.v1.endpoints.system.ConfigOperationsService", FakeConfigOperationsService))
        stack.enter_context(patch("src.api.v1.endpoints.system.TenantOperationsService", FakeTenantOperationsService))
        stack.enter_context(patch("src.api.v1.endpoints.system.AuditOperationsService", FakeAuditOperationsService))
        stack.enter_context(patch("src.api.v1.endpoints.system.ReleaseManagementService", FakeReleaseManagementService))
        stack.enter_context(patch("src.api.v1.endpoints.system.SecurityBaselineService", FakeSecurityBaselineService))
        stack.enter_context(patch("src.api.v1.endpoints.system.LLMGovernanceService", FakeLLMGovernanceService))
        stack.enter_context(patch("src.api.v1.endpoints.system.GatewayGovernanceService", FakeGatewayGovernanceService))
        stack.enter_context(patch("src.api.v1.endpoints.system.MetricsDashboardService", FakeMetricsDashboardService))
        stack.enter_context(patch("src.api.v1.endpoints.system.DataPlatformRuntimeService", FakeDataPlatformRuntimeService))
        stack.enter_context(patch("src.api.v1.endpoints.system.OperationsGovernanceOverviewService", FakeOperationsGovernanceOverviewService))
        stack.enter_context(patch("src.api.v1.endpoints.system.CaptchaOCRService", FakeCaptchaOCRService))
        stack.enter_context(patch("src.api.v1.endpoints.system.get_realtime_gateway_status", lambda: {
            "websocket": {
                "total_connections": 3,
                "active_connections": 2,
                "subscribed_tasks": 1,
            },
            "erp_gateway": {
                "queue_size": 0,
                "dead_letter_size": 0,
                "sync_log_size": 6,
                "supported_systems": ["scm", "wms", "oms", "crm", "fms", "bi"],
            },
            "transport": {
                "sse_ready": True,
                "websocket_manager_ready": True,
                "client_reconnect_strategy": "client_retry_3000ms",
            },
        }))
        stack.enter_context(patch("src.api.v1.endpoints.system._build_selection_dashboard_from_artifacts", _build_selection_dashboard_payload))
        stack.enter_context(patch("src.services.selection_service.FeatureEngine", _FakeFeatureEngine))

        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            create_data = _record_response(
                operation_records,
                step="selection_create_task",
                actor="operator-1",
                response=client.post(
                    "/api/v1/bff/workbench/selection/tasks",
                    headers=operator_headers,
                    json={
                        "query": "蓝牙耳机美国站试点",
                        "category": "electronics",
                        "target_market": "US",
                        "investment_budget": 50000,
                        "priority": "high",
                        "auto_approve": False,
                    },
                ),
                path="/api/v1/bff/workbench/selection/tasks",
                method="POST",
                request_payload={
                    "query": "蓝牙耳机美国站试点",
                    "category": "electronics",
                    "target_market": "US",
                },
            )
            task_id = str(create_data["task_id"])

            selection_detail = _record_response(
                operation_records,
                step="selection_task_detail",
                actor="operator-1",
                response=client.get(
                    f"/api/v1/bff/workbench/selection/tasks/{task_id}",
                    headers=operator_headers,
                ),
                path=f"/api/v1/bff/workbench/selection/tasks/{task_id}",
                method="GET",
            )

            _record_response(
                operation_records,
                step="selection_operator_review",
                actor="operator-1",
                response=client.post(
                    f"/api/v1/bff/workbench/selection/tasks/{task_id}/approve",
                    headers=operator_headers,
                    json={
                        "action": "approve",
                        "stage": "operator_review",
                        "comment": "运营确认趋势与利润空间符合试点预期",
                        "reviewer": "operator-1",
                    },
                ),
                path=f"/api/v1/bff/workbench/selection/tasks/{task_id}/approve",
                method="POST",
            )

            _record_response(
                operation_records,
                step="procurement_second_review",
                actor="procurement-1",
                response=client.post(
                    f"/api/v1/bff/workbench/selection/tasks/{task_id}/approve",
                    headers=procurement_headers,
                    json={
                        "action": "approve",
                        "stage": "procurement_review",
                        "comment": "供应商、MOQ、首单成本均可接受",
                        "reviewer": "procurement-1",
                    },
                ),
                path=f"/api/v1/bff/workbench/selection/tasks/{task_id}/approve",
                method="POST",
            )

            manager_pending = _record_response(
                operation_records,
                step="manager_pending_overview",
                actor="manager-1",
                response=client.get(
                    "/api/v1/bff/workbench/manager/overview",
                    headers=manager_headers,
                ),
                path="/api/v1/bff/workbench/manager/overview",
                method="GET",
            )

            _record_response(
                operation_records,
                step="manager_final_review",
                actor="manager-1",
                response=client.post(
                    f"/api/v1/bff/workbench/selection/tasks/{task_id}/approve",
                    headers=manager_headers,
                    json={
                        "action": "approve",
                        "stage": "manager_review",
                        "stage_order": 3,
                        "comment": "批准进入首单执行与本地闭环跟踪",
                        "reviewer": "manager-1",
                    },
                ),
                path=f"/api/v1/bff/workbench/selection/tasks/{task_id}/approve",
                method="POST",
            )

            _record_response(
                operation_records,
                step="procurement_execute_adoption",
                actor="procurement-1",
                response=client.post(
                    f"/api/v1/bff/workbench/selection/tasks/{task_id}/adopt",
                    headers=procurement_headers,
                    json={
                        "scm_name": "local-scm",
                        "wms_name": "local-wms",
                        "oms_name": "local-oms",
                        "quantity": 240,
                        "supplier_code": "SUP-ERP-001",
                        "notes": "N1-05 多角色联动作业试点",
                    },
                ),
                path=f"/api/v1/bff/workbench/selection/tasks/{task_id}/adopt",
                method="POST",
            )

            scm_status = _record_response(
                operation_records,
                step="procurement_scm_status",
                actor="procurement-1",
                response=client.get("/api/v1/integration/scm/status?name=default", headers=procurement_headers),
                path="/api/v1/integration/scm/status?name=default",
                method="GET",
            )
            wms_status = _record_response(
                operation_records,
                step="procurement_wms_status",
                actor="procurement-1",
                response=client.get("/api/v1/integration/wms/status?name=default", headers=procurement_headers),
                path="/api/v1/integration/wms/status?name=default",
                method="GET",
            )
            oms_status = _record_response(
                operation_records,
                step="procurement_oms_status",
                actor="procurement-1",
                response=client.get("/api/v1/integration/oms/status?name=default", headers=procurement_headers),
                path="/api/v1/integration/oms/status?name=default",
                method="GET",
            )
            adoption_status = _record_response(
                operation_records,
                step="procurement_adoption_status",
                actor="procurement-1",
                response=client.get(
                    f"/api/v1/integration/selection/{task_id}/adoption-status",
                    headers=procurement_headers,
                ),
                path=f"/api/v1/integration/selection/{task_id}/adoption-status",
                method="GET",
            )
            scm_logs = _record_response(
                operation_records,
                step="procurement_scm_logs",
                actor="procurement-1",
                response=client.get("/api/v1/integration/scm/logs?limit=10", headers=procurement_headers),
                path="/api/v1/integration/scm/logs?limit=10",
                method="GET",
            )
            wms_logs = _record_response(
                operation_records,
                step="procurement_wms_logs",
                actor="procurement-1",
                response=client.get("/api/v1/integration/wms/logs?limit=10", headers=procurement_headers),
                path="/api/v1/integration/wms/logs?limit=10",
                method="GET",
            )

            _record_response(
                operation_records,
                step="finance_sync_execution_feedback",
                actor="finance-1",
                response=client.post(
                    f"/api/v1/bff/workbench/selection/tasks/{task_id}/execution-feedback-sync",
                    headers=finance_headers,
                    json={
                        "oms_name": "local-oms",
                        "crm_name": "local-crm",
                        "fms_name": "local-fms",
                        "wms_name": "local-wms",
                        "auto_rescore": True,
                    },
                ),
                path=f"/api/v1/bff/workbench/selection/tasks/{task_id}/execution-feedback-sync",
                method="POST",
            )

            selection_summary = _record_response(
                operation_records,
                step="selection_workbench_summary",
                actor="operator-1",
                response=client.get("/api/v1/bff/workbench/selection/summary", headers=operator_headers),
                path="/api/v1/bff/workbench/selection/summary",
                method="GET",
            )
            selection_result = _record_response(
                operation_records,
                step="selection_task_result",
                actor="operator-1",
                response=client.get(
                    f"/api/v1/bff/workbench/selection/tasks/{task_id}/result",
                    headers=operator_headers,
                ),
                path=f"/api/v1/bff/workbench/selection/tasks/{task_id}/result",
                method="GET",
            )
            manager_final = _record_response(
                operation_records,
                step="manager_final_overview",
                actor="manager-1",
                response=client.get("/api/v1/bff/workbench/manager/overview", headers=manager_headers),
                path="/api/v1/bff/workbench/manager/overview",
                method="GET",
            )

            fms_status = _record_response(
                operation_records,
                step="finance_fms_status",
                actor="finance-1",
                response=client.get("/api/v1/integration/fms/status?name=default", headers=finance_headers),
                path="/api/v1/integration/fms/status?name=default",
                method="GET",
            )
            daily_kpi = _record_response(
                operation_records,
                step="finance_daily_kpi",
                actor="finance-1",
                response=client.get("/api/v1/integration/bi/kpis/daily/latest?name=default", headers=finance_headers),
                path="/api/v1/integration/bi/kpis/daily/latest?name=default",
                method="GET",
            )
            dashboard = _record_response(
                operation_records,
                step="finance_dashboard",
                actor="finance-1",
                response=client.get("/api/v1/dashboard/selection-overview", headers=finance_headers),
                path="/api/v1/dashboard/selection-overview",
                method="GET",
            )

            config_operations = _record_response(
                operation_records,
                step="operations_config",
                actor="ops-admin-1",
                response=client.get("/api/v1/config-operations", headers=operations_headers),
                path="/api/v1/config-operations",
                method="GET",
            )
            tenant_operations = _record_response(
                operation_records,
                step="operations_tenant",
                actor="ops-admin-1",
                response=client.get("/api/v1/tenant-operations", headers=operations_headers),
                path="/api/v1/tenant-operations",
                method="GET",
            )
            audit_operations = _record_response(
                operation_records,
                step="operations_audit",
                actor="ops-admin-1",
                response=client.get("/api/v1/audit-operations", headers=operations_headers),
                path="/api/v1/audit-operations",
                method="GET",
            )
            release_status = _record_response(
                operation_records,
                step="operations_release",
                actor="ops-admin-1",
                response=client.get("/api/v1/release/status", headers=operations_headers),
                path="/api/v1/release/status",
                method="GET",
            )
            security_status = _record_response(
                operation_records,
                step="operations_security",
                actor="ops-admin-1",
                response=client.get("/api/v1/security/status", headers=operations_headers),
                path="/api/v1/security/status",
                method="GET",
            )
            llm_governance = _record_response(
                operation_records,
                step="operations_llm_governance",
                actor="ops-admin-1",
                response=client.get("/api/v1/llm-governance/status", headers=operations_headers),
                path="/api/v1/llm-governance/status",
                method="GET",
            )
            gateway_governance = _record_response(
                operation_records,
                step="operations_gateway_governance",
                actor="ops-admin-1",
                response=client.get("/api/v1/gateway-governance", headers=operations_headers),
                path="/api/v1/gateway-governance",
                method="GET",
            )
            metrics_dashboard = _record_response(
                operation_records,
                step="operations_metrics_dashboard",
                actor="ops-admin-1",
                response=client.get("/api/v1/metrics-dashboard", headers=operations_headers),
                path="/api/v1/metrics-dashboard",
                method="GET",
            )
            data_platform_runtime = _record_response(
                operation_records,
                step="operations_data_platform_runtime",
                actor="ops-admin-1",
                response=client.get("/api/v1/data-platform/runtime", headers=operations_headers),
                path="/api/v1/data-platform/runtime",
                method="GET",
            )
            realtime_status = _record_response(
                operation_records,
                step="operations_realtime_status",
                actor="ops-admin-1",
                response=client.get("/api/v1/realtime/status", headers=operations_headers),
                path="/api/v1/realtime/status",
                method="GET",
            )
            governance_overview = _record_response(
                operation_records,
                step="operations_governance_overview",
                actor="ops-admin-1",
                response=client.get("/api/v1/operations-governance-overview", headers=operations_headers),
                path="/api/v1/operations-governance-overview",
                method="GET",
            )
            captcha_ocr = _record_response(
                operation_records,
                step="operations_captcha_ocr",
                actor="ops-admin-1",
                response=client.post(
                    "/api/v1/security/captcha-ocr",
                    headers=operations_headers,
                    json={"image_text_hint": "a b-1 2 c"},
                ),
                path="/api/v1/security/captcha-ocr",
                method="POST",
                request_payload={"image_text_hint": "a b-1 2 c"},
            )
            audit_query = _record_response(
                operation_records,
                step="operations_audit_query",
                actor="ops-admin-1",
                response=client.get(
                    f"/api/v1/audit/logs?target_id={task_id}&limit=20",
                    headers=operations_headers,
                ),
                path=f"/api/v1/audit/logs?target_id={task_id}&limit=20",
                method="GET",
            )

    selection_workbench = {
        "summary": selection_summary,
        "task_detail": selection_detail,
        "task_result": selection_result,
    }
    manager_overview = {
        "pending_snapshot": manager_pending,
        "final_snapshot": manager_final,
    }
    procurement_workbench = {
        "scm_status": scm_status,
        "wms_status": wms_status,
        "oms_status": oms_status,
        "adoption_status": adoption_status,
        "scm_logs": scm_logs,
        "wms_logs": wms_logs,
    }
    finance_workbench = {
        "fms_status": fms_status,
        "daily_kpi": daily_kpi,
        "dashboard": dashboard,
    }
    operations_workbench = {
        "config_operations": config_operations,
        "tenant_operations": tenant_operations,
        "audit_operations": audit_operations,
        "release_status": release_status,
        "security_status": security_status,
        "llm_governance": llm_governance,
        "gateway_governance": gateway_governance,
        "metrics_dashboard": metrics_dashboard,
        "data_platform_runtime": data_platform_runtime,
        "realtime_status": realtime_status,
        "governance_overview": governance_overview,
        "captcha_ocr": captcha_ocr,
        "audit_query": audit_query,
    }
    audit_logs = list_audit_logs(target_id=task_id, limit=50)

    selection_workbench_path = run_dir / "selection_workbench.json"
    manager_overview_path = run_dir / "manager_overview.json"
    procurement_workbench_path = run_dir / "procurement_workbench.json"
    finance_workbench_path = run_dir / "finance_workbench.json"
    operations_workbench_path = run_dir / "operations_workbench.json"
    scenario_manifest_path = run_dir / "scenario_manifest.json"
    operation_records_path = run_dir / "operation_records.json"
    audit_logs_path = run_dir / "audit_logs.json"

    _write_json(selection_workbench_path, selection_workbench)
    _write_json(manager_overview_path, manager_overview)
    _write_json(procurement_workbench_path, procurement_workbench)
    _write_json(finance_workbench_path, finance_workbench)
    _write_json(operations_workbench_path, operations_workbench)
    _write_json(operation_records_path, operation_records)
    _write_json(audit_logs_path, audit_logs)

    scenario_manifest = {
        "scenario_id": "phase4-local-multi-role-bluetooth-headset",
        "scenario_name": "蓝牙耳机美国站多角色工作台联动作业",
        "task_id": task_id,
        "run_id": run_dir.name,
        "workspace_root": str(workspace_root),
        "roles": [
            {"role": "selection", "actor": "operator-1", "goal": "创建试点任务并确认推荐结论"},
            {"role": "manager", "actor": "manager-1", "goal": "完成终审并处理审批队列"},
            {"role": "procurement", "actor": "procurement-1", "goal": "执行采纳、跟踪 SCM/WMS/OMS"},
            {"role": "finance", "actor": "finance-1", "goal": "核验利润与每日 KPI"},
            {"role": "operations", "actor": "ops-admin-1", "goal": "核验治理、审计与实时通道状态"},
        ],
        "phases": [
            {"phase": "selection_analysis", "status": "completed"},
            {"phase": "approval_queue", "status": "completed"},
            {"phase": "adoption_execution", "status": "completed"},
            {"phase": "profit_feedback_loop", "status": "completed"},
            {"phase": "operations_governance_check", "status": "completed"},
        ],
        "artifacts": {
            "selection_workbench": str(selection_workbench_path),
            "manager_overview": str(manager_overview_path),
            "procurement_workbench": str(procurement_workbench_path),
            "finance_workbench": str(finance_workbench_path),
            "operations_workbench": str(operations_workbench_path),
            "operation_records": str(operation_records_path),
            "audit_logs": str(audit_logs_path),
        },
        "regression_scope": [
            "tests/test_local_multi_role_workbench.py",
            "tests/test_api_integration.py -k \"manager or governance or graph\"",
            "tests/test_bff_contracts.py",
        ],
    }
    _write_json(scenario_manifest_path, scenario_manifest)

    checks = [
        CheckResult(
            "selection_workbench_exposes_business_signal",
            selection_summary.get("total") == 1
            and selection_summary.get("go_decision_count") == 1
            and float(selection_summary.get("avg_roi_year1_percent") or 0.0) > 0
            and bool((selection_result.get("decision_output") or {}).get("top_recommendations")),
            f"selection_total={selection_summary.get('total')}",
            {
                "selection_summary": selection_summary,
                "task_result": selection_result,
            },
        ),
        CheckResult(
            "manager_overview_covers_pending_and_closed_loop",
            (manager_pending.get("summary") or {}).get("pending_approval_count", 0) >= 1
            and len(manager_pending.get("approval_queue") or []) >= 1
            and (manager_final.get("summary") or {}).get("loop_closed") is True
            and (manager_final.get("summary") or {}).get("pending_approval_count") == 0,
            f"pending={((manager_pending.get('summary') or {}).get('pending_approval_count'))}, final_pending={((manager_final.get('summary') or {}).get('pending_approval_count'))}",
            {
                "pending_snapshot": manager_pending,
                "final_snapshot": manager_final,
            },
        ),
        CheckResult(
            "procurement_workbench_tracks_execution_chain",
            adoption_status.get("status") == "completed"
            and bool(adoption_status.get("purchase_order_id"))
            and (scm_status.get("status") in {"pending_review", "approved", "ordered", "completed"})
            and ((wms_status.get("fulfillment_status") or {}).get("status") in {"healthy", "watch", "reserved", "confirmed"})
            and bool((procurement_workbench.get("scm_logs") or {}).get("logs")),
            f"adoption_status={adoption_status.get('status')}",
            procurement_workbench,
        ),
        CheckResult(
            "finance_workbench_has_profit_and_daily_kpi",
            float((fms_status.get("profit_summary") or {}).get("gross_profit_total") or 0.0) == 139.0
            and daily_kpi.get("kpi_date") is not None
            and int((daily_kpi.get("summary") or {}).get("task_count") or 0) >= 1
            and float((dashboard.get("summary") or {}).get("gmv") or 0.0) > 0
            and len(dashboard.get("charts") or {}) >= 5,
            f"gross_profit={((fms_status.get('profit_summary') or {}).get('gross_profit_total'))}",
            finance_workbench,
        ),
        CheckResult(
            "operations_workbench_has_governance_and_audit",
            int(config_operations.get("config_total") or 0) >= 1
            and int(tenant_operations.get("total") or 0) >= 1
            and (release_status.get("delivery_readiness") or {}).get("ready_for_deploy") is True
            and (security_status.get("llm_protection") or {}).get("prompt_guard_enabled") is True
            and (llm_governance.get("quota") or {}).get("configured") is True
            and (realtime_status.get("transport") or {}).get("sse_ready") is True
            and captcha_ocr.get("recognized_text") == "ab12c"
            and int(audit_query.get("total") or 0) >= 6,
            f"audit_total={audit_query.get('total')}",
            operations_workbench,
        ),
        CheckResult(
            "scenario_manifest_and_artifacts_complete",
            len(scenario_manifest.get("roles") or []) == 5
            and all(Path(path).exists() for path in scenario_manifest["artifacts"].values())
            and len(operation_records) >= 20,
            f"role_count={len(scenario_manifest.get('roles') or [])}, operations={len(operation_records)}",
            scenario_manifest,
        ),
        CheckResult(
            "audit_logs_capture_multirole_chain",
            "bff.selection.task.create" in [log.get("action") for log in audit_logs]
            and [log.get("action") for log in audit_logs].count("bff.selection.task.approve") == 3
            and "bff.selection.task.adopt" in [log.get("action") for log in audit_logs]
            and "bff.selection.task.execution_feedback_sync" in [log.get("action") for log in audit_logs],
            f"audit_count={len(audit_logs)}",
            {"actions": [log.get("action") for log in audit_logs]},
        ),
    ]

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
            "selection_workbench": str(selection_workbench_path),
            "manager_overview": str(manager_overview_path),
            "procurement_workbench": str(procurement_workbench_path),
            "finance_workbench": str(finance_workbench_path),
            "operations_workbench": str(operations_workbench_path),
            "scenario_manifest": str(scenario_manifest_path),
            "operation_records": str(operation_records_path),
            "audit_logs": str(audit_logs_path),
            "summary": str(run_dir / "summary.json"),
        },
    }
    _write_json(run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
