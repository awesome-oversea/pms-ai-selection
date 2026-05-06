from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enums import ERPSystemType, TaskStatus
from src.repositories.erp_repository import ErpIntegrationRepository
from src.repositories.selection_repository import SelectionTaskRepository
from src.services.data_lake_service import DataLakeService


class ProfitFlywheelService:
    def __init__(self, session: AsyncSession, tenant_id: str | None = None):
        self.session = session
        self.tenant_id = tenant_id
        self.selection_repo = SelectionTaskRepository(session, tenant_id=tenant_id)
        self.erp_repo = ErpIntegrationRepository(session, tenant_id=tenant_id)
        self.data_lake_service = DataLakeService(session)

    async def build_status(self) -> dict[str, Any]:
        latest_task = await self._get_latest_task()
        latest_task_payload = self._serialize_task(latest_task)

        scm = await self._build_system_status(ERPSystemType.SCM)
        wms = await self._build_system_status(ERPSystemType.WMS)
        crm = await self._build_system_status(ERPSystemType.CRM)
        fms = await self._build_system_status(ERPSystemType.FMS)
        bi = await self._build_bi_status()

        selection = {
            "ready": latest_task_payload is not None,
            "task": latest_task_payload,
            "can_drive_downstream": bool(latest_task_payload and latest_task_payload.get("status") in {"completed", "running"}),
            "go_no_go_decision": latest_task_payload.get("go_no_go_decision") if latest_task_payload else None,
        }

        latest_decision_output = ((latest_task.config or {}).get("execution_result") or {}).get("decision_output", {}) if latest_task is not None else {}
        latest_rescore_summary = latest_decision_output.get("rescore_summary") if isinstance(latest_decision_output, dict) else None

        feedback_loop = {
            "crm_feedback_ready": crm["ready"],
            "fms_profit_ready": fms["ready"],
            "bi_ready": bi["ready"],
            "selection_feedback_ready": bool(latest_task_payload),
            "auto_rescore_completed": isinstance(latest_rescore_summary, dict),
            "feature_asset_ready": isinstance(latest_rescore_summary, dict),
            "loop_closed": bool(latest_task_payload) and crm["ready"] and fms["ready"] and bi["ready"],
        }

        recommended_actions: list[dict[str, Any]] = []
        if not selection["ready"]:
            recommended_actions.append({"step": "selection", "action": "create_or_complete_selection_task", "reason": "缺少可驱动下游的选品任务结果"})
        if not scm["configured"]:
            recommended_actions.append({"step": "scm", "action": "configure_scm", "reason": "缺少SCM配置"})
        elif not scm["synced"]:
            recommended_actions.append({"step": "scm", "action": "run_scm_sync", "reason": "SCM尚未形成最近同步证据"})
        if not wms["configured"]:
            recommended_actions.append({"step": "wms", "action": "configure_wms", "reason": "缺少WMS配置"})
        elif not wms["synced"]:
            recommended_actions.append({"step": "wms", "action": "run_wms_sync", "reason": "WMS尚未形成最近同步证据"})
        if not crm["configured"]:
            recommended_actions.append({"step": "crm", "action": "configure_crm", "reason": "缺少CRM配置"})
        elif not crm["synced"]:
            recommended_actions.append({"step": "crm", "action": "run_crm_sync", "reason": "CRM尚未形成最近同步证据"})
        if not fms["configured"]:
            recommended_actions.append({"step": "fms", "action": "configure_fms", "reason": "缺少FMS配置"})
        elif not fms["synced"]:
            recommended_actions.append({"step": "fms", "action": "run_fms_sync", "reason": "FMS尚未形成最近同步证据"})
        if not bi["configured"]:
            recommended_actions.append({"step": "bi", "action": "configure_bi", "reason": "缺少BI配置"})
        elif not bi["synced"]:
            recommended_actions.append({"step": "bi", "action": "run_bi_export", "reason": "BI尚未形成最近消费导出证据"})

        route_status = {
            "selection_to_scm": selection["can_drive_downstream"] and scm["ready"],
            "scm_to_wms": scm["ready"] and wms["ready"],
            "wms_to_crm": wms["ready"] and crm["ready"],
            "crm_to_fms": crm["ready"] and fms["ready"],
            "fms_to_bi": fms["ready"] and bi["ready"],
        }
        all_ready = all(route_status.values())
        loop_gaps = [key for key, value in route_status.items() if not value]
        score_feedback_inputs = {
            "crm_feedback_ready": crm["ready"],
            "fms_profit_ready": fms["ready"],
            "wms_inventory_ready": wms["ready"],
            "bi_metrics_ready": bi["ready"],
            "can_rescore_selection": feedback_loop["loop_closed"] and all_ready,
            "signals": [
                signal
                for signal, ready in {
                    "crm_feedback": crm["ready"],
                    "fms_profit": fms["ready"],
                    "wms_inventory": wms["ready"],
                    "bi_metrics": bi["ready"],
                }.items()
                if ready
            ],
        }
        recycle_actions = [
            {
                "trigger": "feedback_loop",
                "target": "selection",
                "action": "re-score selection with downstream and feedback metrics",
                "inputs": score_feedback_inputs["signals"],
            }
        ] if feedback_loop["loop_closed"] else []
        overall_status = "closed_loop_ready" if feedback_loop["loop_closed"] and all_ready else ("downstream_ready" if all_ready else "partial")

        return {
            "selection": selection,
            "scm": scm,
            "wms": wms,
            "crm": crm,
            "fms": fms,
            "bi": bi,
            "feedback_loop": feedback_loop,
            "route_status": route_status,
            "loop_gaps": loop_gaps,
            "score_feedback_inputs": score_feedback_inputs,
            "recycle_actions": recycle_actions,
            "recommended_actions": recommended_actions,
            "overall_status": overall_status,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    async def _get_latest_task(self) -> Any | None:
        tasks, _ = await self.selection_repo.list_tasks(limit=1, offset=0)
        return tasks[0] if tasks else None

    async def _build_system_status(self, system_type: ERPSystemType) -> dict[str, Any]:
        config = await self.erp_repo.get_config(system_type, name="default")
        logs = await self.erp_repo.list_sync_logs(system_type, limit=1)
        latest_log = logs[0][0] if logs else None
        configured = config is not None
        synced = latest_log is not None and latest_log.status in {"completed", "partial_success"}
        extra = {}
        if system_type == ERPSystemType.WMS and latest_log is not None:
            extra = {
                "inventory_summary": {
                    "last_sync_type": latest_log.sync_type,
                    "sync_status": latest_log.status,
                },
                "fulfillment_status": {
                    "status": "healthy" if synced else "attention_required",
                    "backorder_risk": latest_log.status != "completed",
                },
            }
        return {
            "configured": configured,
            "synced": synced,
            "ready": configured and synced,
            "config_name": config.name if config else None,
            "last_sync_status": latest_log.status if latest_log else None,
            "last_sync_type": latest_log.sync_type if latest_log else None,
            "last_finished_at": latest_log.finished_at.isoformat() if latest_log and latest_log.finished_at else None,
            **extra,
        }

    async def _build_bi_status(self) -> dict[str, Any]:
        config = await self.erp_repo.get_config(ERPSystemType.BI, name="default")
        logs = await self.erp_repo.list_sync_logs(ERPSystemType.BI, limit=1)
        latest_log = logs[0][0] if logs else None
        data_lake_status = await self.data_lake_service.build_status()
        bi_ready_assets = data_lake_status.get("bi_ready_assets", [])
        downstream = data_lake_status.get("downstream_consumers", {}).get("bi", [])
        configured = config is not None
        synced = latest_log is not None and latest_log.status in {"completed", "partial_success"}
        return {
            "configured": configured,
            "synced": synced,
            "ready": configured and synced and len(bi_ready_assets) >= 2,
            "bi_ready_assets": bi_ready_assets,
            "downstream_consumers": downstream,
            "last_sync_status": latest_log.status if latest_log else None,
            "last_finished_at": latest_log.finished_at.isoformat() if latest_log and latest_log.finished_at else None,
        }

    @staticmethod
    def _serialize_task(task: Any | None) -> dict[str, Any] | None:
        if task is None:
            return None
        config = task.config or {}
        execution_result = config.get("execution_result") if isinstance(config, dict) else None
        go_no_go = None
        go_no_go_decision = None
        if isinstance(execution_result, dict):
            commercial = execution_result.get("results", {}).get("commercial_evaluation", {})
            if isinstance(commercial, dict):
                go_no_go = commercial.get("go_no_go")
                if isinstance(go_no_go, dict):
                    go_no_go_decision = go_no_go.get("decision")
                elif isinstance(go_no_go, str):
                    go_no_go_decision = go_no_go
        return {
            "task_id": str(task.id),
            "query": task.title,
            "status": task.status.value if isinstance(task.status, TaskStatus) else str(task.status),
            "target_market": task.target_market,
            "category": task.target_category,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "go_no_go": go_no_go,
            "go_no_go_decision": go_no_go_decision,
            "status_reason": config.get("status_reason") if isinstance(config, dict) else None,
        }
