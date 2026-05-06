from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SEC_SECRET_KEY", "local-report-delivery-32chars")
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
from src.core.security import clear_audit_logs, list_audit_logs
from src.main import create_app
from src.services.report_center_service import ReportCenterService


ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "local_report_delivery"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local report delivery acceptance.")
    parser.add_argument("--output-root", default=str(ARTIFACT_ROOT), help="Artifact root directory")
    return parser.parse_args()


def _safe_json(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return {"text": response.text}


def _json_data(response: Any) -> dict[str, Any]:
    payload = _safe_json(response)
    return payload["data"] if isinstance(payload, dict) and "data" in payload else payload


def _filename_from_response(response: Any, fallback: str) -> str:
    content_disposition = response.headers.get("content-disposition") or response.headers.get("Content-Disposition") or ""
    match = re.search(r'filename="?([^";]+)"?', content_disposition)
    if match:
        return match.group(1)
    return fallback


def _metric_value(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def main() -> int:
    args = parse_args()
    run_dir = _build_run_dir(Path(args.output_root))
    workspace_root = run_dir / "workspace"
    workspace_erp_root = workspace_root / "artifacts" / "erp_local"
    workspace_erp_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASELINE_ERP_LOCAL, workspace_erp_root, dirs_exist_ok=True)

    report_state_path = workspace_root / "artifacts" / "report_center" / "state.json"
    export_root = run_dir / "exports"

    clear_audit_logs()
    AcceptanceSelectionTaskService.shared_repo = _InMemorySelectionRepo()
    LocalCloseLoopErpIntegrationService.shared_selection_repo = AcceptanceSelectionTaskService.shared_repo
    LocalCloseLoopErpIntegrationService.shared_config_repo = _ConfigRepo(workspace_root)
    _FakeFeatureEngine._features = {}

    operation_records: list[dict[str, Any]] = []
    delivery_records: list[dict[str, Any]] = []

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

    async def _local_share_report_link(
        self,
        *,
        channel: str,
        webhook_url: str,
        report_title: str,
        report_summary: str,
        share_url: str,
    ) -> dict[str, Any]:
        record = {
            "channel": channel,
            "webhook_url": webhook_url,
            "report_title": report_title,
            "report_summary": report_summary,
            "share_url": share_url,
            "delivery_mode": "local-record-only",
            "delivered_at": datetime.now(UTC).isoformat(),
        }
        delivery_records.append(record)
        return {
            "channel": channel,
            "message_type": "report_delivery",
            "template_used": "summary_with_link",
            "delivered": True,
            "audit_meta": {
                "has_report_url": True,
                "delivery_mode": "local-record-only",
            },
            "result": record,
        }

    operator_headers = _build_headers("operator", user_id="00000000-0000-0000-0000-000000000011", username="operator-1")
    procurement_headers = _build_headers("procurement", user_id="00000000-0000-0000-0000-000000000021", username="procurement-1")
    manager_headers = _build_headers("manager", user_id="00000000-0000-0000-0000-000000000031", username="manager-1")
    admin_headers = _build_headers("tenant_admin", user_id="00000000-0000-0000-0000-000000000041", username="tenant-admin-1")

    finance_report: dict[str, Any]
    market_report: dict[str, Any]
    management_report: dict[str, Any]
    csv_report: dict[str, Any]
    report_list: dict[str, Any]
    shared_result: dict[str, Any]
    delivered_result: dict[str, Any]
    shared_access: dict[str, Any]
    archive_result: dict[str, Any]
    archive_list: dict[str, Any]
    archive_detail: dict[str, Any]
    compare_result: dict[str, Any]
    final_detail: dict[str, Any]
    profit_trace: dict[str, Any]
    feedback_loop_status: dict[str, Any]
    templates_payload: dict[str, Any]
    task_id = ""
    export_manifest: list[dict[str, Any]] = []

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
        stack.enter_context(patch("src.services.channel_delivery_service.ChannelDeliveryService.share_report_link", _local_share_report_link))

        import src.api.v1.endpoints.reports as report_endpoints

        report_endpoints._SHARE_REPORT_OVERRIDES.clear()
        stack.enter_context(patch.object(report_endpoints, "service", ReportCenterService(state_path=report_state_path)))

        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            create_response = client.post(
                "/api/v1/bff/workbench/selection/tasks",
                headers=operator_headers,
                json={
                    "query": "蓝牙耳机经营复盘报告样本",
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
                    "notes": "N1-03 local report delivery drill",
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

            templates_response = client.get("/api/v1/reports/templates", headers=admin_headers)
            templates_payload = _json_data(templates_response)
            operation_records.append(
                {
                    "step": "report_templates",
                    "actor": "tenant-admin-1",
                    "response_status_code": templates_response.status_code,
                    "response_data": templates_payload,
                }
            )

            decision_output = final_detail.get("decision_output") or {}
            execution_feedback = decision_output.get("execution_feedback") or {}
            rescore_summary = decision_output.get("rescore_summary") or {}
            pricing = decision_output.get("pricing") or {}
            sales_feedback = execution_feedback.get("sales") or {}
            review_feedback = execution_feedback.get("reviews") or {}
            profit_feedback = execution_feedback.get("profit") or {}
            inventory_feedback = execution_feedback.get("inventory") or {}
            bi_metrics = _metric_value(feedback_loop_status, "bi", "task_metrics", default={}) or {}
            recommended_price = float(pricing.get("recommended_price") or 40.39)
            sales_7d = int(sales_feedback.get("sales_7d") or 12)
            gross_profit = float(profit_feedback.get("gross_profit") or 139.0)
            cost_total = float(_metric_value(profit_trace, "trace_chain", "fms", "profit_summary", "cost_total", default=60.0) or 60.0)
            margin_rate = float(profit_feedback.get("margin_rate") or 0.285)
            inventory_available = int(inventory_feedback.get("available_inventory") or 18)
            gmv = round(recommended_price * sales_7d, 2)
            roi = round(gross_profit / cost_total, 2) if cost_total else 0.0
            completion_rate = 1.0
            opportunities = int(bi_metrics.get("recommendation_count") or 1)
            anomalies = int(bi_metrics.get("risk_count") or 0)
            conversion_rate = round(float(review_feedback.get("review_rating") or 4.6) / 20, 4)
            market_gmv = round(gmv * 1.08, 2)
            market_opportunities = opportunities + 1

            finance_generate_response = client.post(
                f"/api/v1/reports/generate?report_type=monthly&format=pdf&task_id={task_id}",
                headers=admin_headers,
                json={
                    "template_name": "finance_review",
                    "title": "蓝牙耳机经营复盘月报",
                    "summary": "基于本地经营闭环任务输出利润、库存与ROI复盘。",
                    "sections": ["利润表现", "成本结构", "ROI复盘"],
                    "metrics_filter": ["gmv", "roi", "completion_rate"],
                    "chart_keys": ["sales_trend"],
                    "params": {
                        "gmv": gmv,
                        "roi": roi,
                        "completion_rate": completion_rate,
                        "gross_profit": gross_profit,
                        "margin_rate": margin_rate,
                    },
                },
            )
            finance_report = _json_data(finance_generate_response)
            operation_records.append(
                {
                    "step": "generate_finance_report_pdf",
                    "actor": "tenant-admin-1",
                    "response_status_code": finance_generate_response.status_code,
                    "response_data": finance_report,
                }
            )

            market_generate_response = client.post(
                f"/api/v1/reports/generate?report_type=weekly&format=xlsx&task_id={task_id}",
                headers=admin_headers,
                json={
                    "template_name": "market_insight",
                    "title": "蓝牙耳机市场洞察周报",
                    "summary": "输出趋势、机会与竞争态势，供分析师与运营对齐。",
                    "sections": ["趋势变化", "竞品动态", "增长机会", "行动建议"],
                    "metrics_filter": ["gmv", "conversion_rate", "opportunities"],
                    "chart_keys": ["sales_trend"],
                    "params": {
                        "gmv": market_gmv,
                        "conversion_rate": conversion_rate,
                        "opportunities": market_opportunities,
                        "anomalies": anomalies,
                    },
                },
            )
            market_report = _json_data(market_generate_response)
            operation_records.append(
                {
                    "step": "generate_market_report_xlsx",
                    "actor": "tenant-admin-1",
                    "response_status_code": market_generate_response.status_code,
                    "response_data": market_report,
                }
            )

            management_generate_response = client.post(
                f"/api/v1/reports/generate?report_type=daily&format=pptx&task_id={task_id}",
                headers=admin_headers,
                json={
                    "template_name": "management_focus",
                    "title": "蓝牙耳机管理层日报",
                    "summary": "聚焦关键经营指标、库存风险与行动建议。",
                    "sections": ["经营摘要", "核心指标", "异常与风险", "行动建议"],
                    "metrics_filter": ["gmv", "completion_rate", "roi", "anomalies"],
                    "chart_keys": ["sales_trend", "category_dist"],
                    "params": {
                        "gmv": gmv,
                        "completion_rate": completion_rate,
                        "roi": roi,
                        "anomalies": anomalies,
                    },
                },
            )
            management_report = _json_data(management_generate_response)
            operation_records.append(
                {
                    "step": "generate_management_report_pptx",
                    "actor": "tenant-admin-1",
                    "response_status_code": management_generate_response.status_code,
                    "response_data": management_report,
                }
            )

            csv_generate_response = client.post(
                f"/api/v1/reports/generate?report_type=daily&format=csv&task_id={task_id}",
                headers=admin_headers,
                json={
                    "template_name": "management_focus",
                    "title": "蓝牙耳机执行快照",
                    "summary": "导出任务执行与回流关键指标的CSV快照。",
                    "sections": ["经营摘要", "核心指标"],
                    "metrics_filter": ["gmv", "completion_rate", "anomalies"],
                    "chart_keys": [],
                    "params": {
                        "gmv": gmv,
                        "completion_rate": completion_rate,
                        "anomalies": anomalies,
                        "inventory_available": inventory_available,
                    },
                },
            )
            csv_report = _json_data(csv_generate_response)
            operation_records.append(
                {
                    "step": "generate_snapshot_report_csv",
                    "actor": "tenant-admin-1",
                    "response_status_code": csv_generate_response.status_code,
                    "response_data": csv_report,
                }
            )

            for label, report_payload in [
                ("finance_pdf", finance_report),
                ("market_xlsx", market_report),
                ("management_pptx", management_report),
                ("snapshot_csv", csv_report),
            ]:
                report_id = str(report_payload["report_id"])
                download_response = client.get(
                    f"/api/v1/reports/{report_id}/download",
                    headers=admin_headers,
                )
                filename = _filename_from_response(download_response, f"{report_id}.{label.split('_')[-1]}")
                export_path = export_root / filename
                export_path.parent.mkdir(parents=True, exist_ok=True)
                export_path.write_bytes(download_response.content)
                export_manifest.append(
                    {
                        "label": label,
                        "report_id": report_id,
                        "path": str(export_path),
                        "content_type": download_response.headers.get("content-type"),
                        "size_bytes": export_path.stat().st_size,
                        "response_status_code": download_response.status_code,
                    }
                )
                operation_records.append(
                    {
                        "step": f"download_{label}",
                        "actor": "tenant-admin-1",
                        "response_status_code": download_response.status_code,
                        "response_headers": {
                            "content-type": download_response.headers.get("content-type"),
                            "content-disposition": download_response.headers.get("content-disposition"),
                        },
                        "artifact_path": str(export_path),
                    }
                )

            share_response = client.post(
                f"/api/v1/reports/{management_report['report_id']}/share",
                headers=admin_headers,
                json={"expires_in_hours": 12},
            )
            shared_result = _json_data(share_response)
            operation_records.append(
                {
                    "step": "create_share_link",
                    "actor": "tenant-admin-1",
                    "response_status_code": share_response.status_code,
                    "response_data": shared_result,
                }
            )

            deliver_response = client.post(
                f"/api/v1/reports/{management_report['report_id']}/share/deliver",
                headers=admin_headers,
                json={
                    "channel": "dingtalk",
                    "webhook_url": "https://local.invalid/dingtalk/webhook",
                    "expires_in_hours": 12,
                },
            )
            delivered_result = _json_data(deliver_response)
            operation_records.append(
                {
                    "step": "deliver_share_link",
                    "actor": "tenant-admin-1",
                    "response_status_code": deliver_response.status_code,
                    "response_data": delivered_result,
                }
            )

            shared_access_response = client.get(
                f"/api/v1/reports/share/{delivered_result['share']['share_token']}",
            )
            shared_access = _json_data(shared_access_response)
            operation_records.append(
                {
                    "step": "access_shared_link",
                    "actor": "anonymous",
                    "response_status_code": shared_access_response.status_code,
                    "response_data": shared_access,
                }
            )

            report_list_response = client.get("/api/v1/reports?limit=10", headers=admin_headers)
            report_list = _json_data(report_list_response)
            operation_records.append(
                {
                    "step": "list_reports",
                    "actor": "tenant-admin-1",
                    "response_status_code": report_list_response.status_code,
                    "response_data": report_list,
                }
            )

            archive_response = client.delete(
                f"/api/v1/reports/{finance_report['report_id']}",
                headers=admin_headers,
            )
            archive_result = _json_data(archive_response)
            operation_records.append(
                {
                    "step": "archive_finance_report",
                    "actor": "tenant-admin-1",
                    "response_status_code": archive_response.status_code,
                    "response_data": archive_result,
                }
            )

            archive_list_response = client.get("/api/v1/reports/archive", headers=admin_headers)
            archive_list = _json_data(archive_list_response)
            operation_records.append(
                {
                    "step": "list_archives",
                    "actor": "tenant-admin-1",
                    "response_status_code": archive_list_response.status_code,
                    "response_data": archive_list,
                }
            )

            archive_detail_response = client.get(
                f"/api/v1/reports/archive/{finance_report['report_id']}",
                headers=admin_headers,
            )
            archive_detail = _json_data(archive_detail_response)
            operation_records.append(
                {
                    "step": "archive_detail",
                    "actor": "tenant-admin-1",
                    "response_status_code": archive_detail_response.status_code,
                    "response_data": archive_detail,
                }
            )

            compare_response = client.post(
                "/api/v1/reports/compare",
                headers=admin_headers,
                json={
                    "baseline_report_id": finance_report["report_id"],
                    "target_report_id": market_report["report_id"],
                },
            )
            compare_result = _json_data(compare_response)
            operation_records.append(
                {
                    "step": "compare_reports",
                    "actor": "tenant-admin-1",
                    "response_status_code": compare_response.status_code,
                    "response_data": compare_result,
                }
            )

    audit_logs = list_audit_logs(limit=100)
    action_list = [log.get("action") for log in audit_logs]

    checks = [
        CheckResult(
            "selection_close_loop_ready",
            final_detail.get("task_id") == task_id
            and final_detail.get("status") == "completed"
            and (decision_output.get("rescore_summary") or {}).get("decision") == "GO",
            f"task_status={final_detail.get('status')}",
            {
                "task_id": task_id,
                "decision": (decision_output.get("rescore_summary") or {}).get("decision"),
                "profit_contract": profit_trace.get("profit_contract"),
            },
        ),
        CheckResult(
            "report_templates_ready",
            templates_response.status_code == 200
            and any(item.get("name") == "management_focus" for item in templates_payload.get("templates", []))
            and set(["pdf", "xlsx", "pptx", "csv"]).issubset(set(templates_payload.get("supported_formats", []))),
            f"template_status={templates_response.status_code}",
            {"supported_formats": templates_payload.get("supported_formats")},
        ),
        CheckResult(
            "multi_format_exports_ready",
            len(export_manifest) == 4
            and all(item["response_status_code"] == 200 and Path(item["path"]).exists() and item["size_bytes"] > 0 for item in export_manifest)
            and (Path(export_manifest[0]["path"]).read_bytes().startswith(b"%PDF"))
            and (Path(export_manifest[1]["path"]).read_bytes().startswith(b"PK"))
            and (Path(export_manifest[2]["path"]).read_bytes().startswith(b"PK"))
            and (b"title" in Path(export_manifest[3]["path"]).read_bytes()),
            f"export_count={len(export_manifest)}",
            {"exports": export_manifest},
        ),
        CheckResult(
            "report_listing_ready",
            report_list_response.status_code == 200
            and report_list.get("total", 0) >= 4
            and (report_list.get("summary") or {}).get("report_count", 0) >= 4
            and any(item.get("report_id") == management_report["report_id"] for item in report_list.get("items", [])),
            f"report_total={report_list.get('total')}",
            {"report_list": report_list},
        ),
        CheckResult(
            "share_link_created",
            share_response.status_code == 200
            and bool(shared_result.get("share_token"))
            and str(shared_result.get("share_url") or "").startswith("/api/v1/reports/share/"),
            f"share_status={share_response.status_code}",
            {"share": shared_result},
        ),
        CheckResult(
            "share_delivery_recorded",
            deliver_response.status_code == 200
            and delivered_result.get("delivery", {}).get("delivered") is True
            and len(delivery_records) == 1
            and delivery_records[0]["delivery_mode"] == "local-record-only",
            f"delivery_status={deliver_response.status_code}",
            {"delivery": delivered_result, "delivery_records": delivery_records},
        ),
        CheckResult(
            "shared_access_ready",
            shared_access_response.status_code == 200
            and shared_access.get("report_id") == management_report["report_id"]
            and shared_access.get("access_count") == 1,
            f"shared_access_status={shared_access_response.status_code}",
            {"shared_access": shared_access},
        ),
        CheckResult(
            "archive_ready",
            archive_response.status_code == 200
            and archive_result.get("archived") is True
            and archive_list.get("total", 0) >= 1
            and archive_detail.get("report_id") == finance_report["report_id"],
            f"archive_status={archive_response.status_code}",
            {
                "archive_result": archive_result,
                "archive_list": archive_list,
                "archive_detail": archive_detail,
            },
        ),
        CheckResult(
            "report_compare_ready",
            compare_response.status_code == 200
            and compare_result.get("baseline", {}).get("archived") is True
            and compare_result.get("archive_context", {}).get("baseline_archived") is True
            and any(item.get("metric") == "gmv" for item in compare_result.get("metric_differences", [])),
            f"compare_status={compare_response.status_code}",
            {"compare_result": compare_result},
        ),
        CheckResult(
            "audit_logs_captured",
            all(
                action in action_list
                for action in [
                    "report.generate",
                    "report.download",
                    "report.share.create",
                    "report.share.deliver",
                    "report.share.access",
                    "report.compare",
                    "report.delete",
                ]
            ),
            f"audit_count={len(audit_logs)}",
            {"actions": action_list},
        ),
    ]

    operation_path = run_dir / "operation_records.json"
    selection_task_path = run_dir / "selection_task_detail.json"
    feedback_loop_path = run_dir / "feedback_loop_status.json"
    profit_trace_path = run_dir / "profit_trace.json"
    report_list_path = run_dir / "report_list.json"
    export_manifest_path = run_dir / "export_manifest.json"
    share_path = run_dir / "share_result.json"
    shared_access_path = run_dir / "shared_access.json"
    archive_list_path = run_dir / "archive_list.json"
    archive_detail_path = run_dir / "archive_detail.json"
    compare_path = run_dir / "compare_result.json"
    delivery_records_path = run_dir / "local_delivery_records.json"
    audit_logs_path = run_dir / "audit_logs.json"

    _write_json(operation_path, operation_records)
    _write_json(selection_task_path, final_detail)
    _write_json(feedback_loop_path, feedback_loop_status)
    _write_json(profit_trace_path, profit_trace)
    _write_json(report_list_path, report_list)
    _write_json(export_manifest_path, export_manifest)
    _write_json(share_path, {"share": shared_result, "delivery": delivered_result})
    _write_json(shared_access_path, shared_access)
    _write_json(archive_list_path, archive_list)
    _write_json(archive_detail_path, archive_detail)
    _write_json(compare_path, compare_result)
    _write_json(delivery_records_path, delivery_records)
    _write_json(audit_logs_path, audit_logs)

    summary = {
        "status": _status_from_checks(checks),
        "accepted": all(item.passed for item in checks),
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "workspace_root": str(workspace_root),
        "task_id": task_id,
        "report_ids": {
            "finance_pdf": finance_report["report_id"],
            "market_xlsx": market_report["report_id"],
            "management_pptx": management_report["report_id"],
            "snapshot_csv": csv_report["report_id"],
        },
        "checks": [item.to_dict() for item in checks],
        "artifacts": {
            "operation_records": str(operation_path),
            "selection_task_detail": str(selection_task_path),
            "feedback_loop_status": str(feedback_loop_path),
            "profit_trace": str(profit_trace_path),
            "report_list": str(report_list_path),
            "export_manifest": str(export_manifest_path),
            "share_result": str(share_path),
            "shared_access": str(shared_access_path),
            "archive_list": str(archive_list_path),
            "archive_detail": str(archive_detail_path),
            "compare_result": str(compare_path),
            "local_delivery_records": str(delivery_records_path),
            "audit_logs": str(audit_logs_path),
            "report_state": str(report_state_path),
            "summary": str(run_dir / "summary.json"),
        },
    }
    _write_json(run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
