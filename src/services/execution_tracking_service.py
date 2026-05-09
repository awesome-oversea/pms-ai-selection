from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.core.pms_governance import AuditContext
from src.models.enums import ERPSystemType, RecommendationExecutionState
from src.services.suggestion_service import SuggestionService

logger = get_logger(__name__)

_DOMAIN_STATUS_METHOD: dict[str, str] = {
    "scm": "query_suggestion_status",
    "wms": "query_suggestion_status",
    "ads": "query_suggestion_status",
    "som": "query_suggestion_status",
    "oms": "query_order_status",
}

_ERP_STATUS_TO_EXECUTION_STATE: dict[str, dict[str, RecommendationExecutionState]] = {
    "scm": {
        "pending_review": RecommendationExecutionState.SCM_REVIEWING,
        "approved": RecommendationExecutionState.SCM_APPROVED,
        "ordered": RecommendationExecutionState.SCM_ORDERED,
        "rejected": RecommendationExecutionState.SCM_REJECTED,
        "completed": RecommendationExecutionState.SCM_ORDERED,
        "partial": RecommendationExecutionState.SCM_ORDERED,
    },
    "wms": {
        "reserved": RecommendationExecutionState.WMS_RESERVED,
        "allocated": RecommendationExecutionState.WMS_RESERVED,
        "confirmed": RecommendationExecutionState.WMS_CONFIRMED,
        "rejected": RecommendationExecutionState.SCM_REJECTED,
    },
    "ads": {
        "pending_review": RecommendationExecutionState.OMS_DRAFT_CREATED,
        "approved": RecommendationExecutionState.OMS_PUBLISHED,
        "active": RecommendationExecutionState.OMS_ACTIVE,
        "rejected": RecommendationExecutionState.OMS_DRAFT_CREATED,
    },
    "som": {
        "pending_approval": RecommendationExecutionState.OMS_DRAFT_CREATED,
        "approved": RecommendationExecutionState.OMS_PUBLISHED,
        "published": RecommendationExecutionState.OMS_PUBLISHED,
        "active": RecommendationExecutionState.OMS_ACTIVE,
        "rejected": RecommendationExecutionState.OMS_DRAFT_CREATED,
    },
    "oms": {
        "draft": RecommendationExecutionState.OMS_DRAFT_CREATED,
        "published": RecommendationExecutionState.OMS_PUBLISHED,
        "active": RecommendationExecutionState.OMS_ACTIVE,
        "closed": RecommendationExecutionState.CLOSED,
    },
}


class ExecutionTrackingService:
    """
    ERP执行状态追踪服务 (P2-ERP-011)。

    职责:
    - 从ERP各域客户端实时查询建议/草稿的审批和执行状态
    - 将ERP域状态映射为PMS执行状态(RecommendationExecutionState)
    - 通过SuggestionService同步更新建议状态
    - 支持批量追踪和单条追踪
    - 记录追踪历史和审计日志
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        tenant_id: str | None = None,
        actor: dict[str, Any] | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self._tracking_history: list[dict[str, Any]] = []

    async def track_suggestion_status(
        self,
        suggestion_id: str,
        *,
        target_domain: str,
        domain_reference_id: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        domain_status = await self._query_domain_status(
            target_domain,
            reference_id=domain_reference_id or suggestion_id,
            audit_context=audit_context,
        )

        execution_state = self._map_to_execution_state(target_domain, domain_status.get("status", "unknown"))

        sync_result: dict[str, Any] | None = None
        if execution_state is not None:
            suggestion_service = SuggestionService(
                self.session,
                tenant_id=self.tenant_id,
                actor=self.actor,
            )
            try:
                sync_result = await suggestion_service.sync_from_execution_state(
                    suggestion_id,
                    execution_state,
                    detail=f"追踪同步: {target_domain}状态={domain_status.get('status')}",
                    audit_context=audit_context,
                )
            except (ValueError, KeyError) as e:
                logger.warning("建议状态同步跳过: suggestion_id=%s error=%s", suggestion_id, e)
                sync_result = {"suggestion_id": suggestion_id, "error": str(e)}

        tracking_record = {
            "suggestion_id": suggestion_id,
            "target_domain": target_domain,
            "domain_status": domain_status,
            "mapped_execution_state": execution_state.value if execution_state else None,
            "sync_result": sync_result,
            "tracked_at": datetime.now(UTC).isoformat(),
        }
        self._tracking_history.append(tracking_record)

        return tracking_record

    async def batch_track_suggestions(
        self,
        suggestions: list[dict[str, Any]],
        *,
        audit_context: AuditContext | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in suggestions:
            suggestion_id = item.get("suggestion_id") or item.get("id")
            target_domain = item.get("target_domain", "scm")
            domain_reference_id = item.get("domain_reference_id") or item.get("erp_reference_id")
            if not suggestion_id:
                continue
            result = await self.track_suggestion_status(
                suggestion_id,
                target_domain=target_domain,
                domain_reference_id=domain_reference_id,
                audit_context=audit_context,
            )
            results.append(result)
        logger.info("批量追踪完成: %d/%d 条建议已追踪", len(results), len(suggestions))
        return results

    async def track_task_execution(
        self,
        task_id: str,
        *,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        from src.repositories.selection_repository import SelectionTaskRepository

        repo = SelectionTaskRepository(self.session, tenant_id=self.tenant_id)
        from uuid import UUID
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return {"task_id": task_id, "error": "invalid_task_id_format"}
        task = await repo.get_task(task_uuid)
        if task is None:
            return {"task_id": task_id, "error": "task_not_found"}

        config = task.config or {}
        adoption = config.get("adoption") if isinstance(config, dict) else {}
        erp_submission = adoption.get("erp_submission") if isinstance(adoption, dict) else {}

        if not erp_submission:
            return {
                "task_id": task_id,
                "status": "no_erp_submission",
                "message": "该任务尚未提交ERP建议池",
            }

        suggestion_id = erp_submission.get("suggestion_id")
        target_domain = erp_submission.get("target_domain", "scm")

        if not suggestion_id:
            return {"task_id": task_id, "error": "no_suggestion_id_in_erp_submission"}

        tracking_result = await self.track_suggestion_status(
            suggestion_id,
            target_domain=target_domain,
            audit_context=audit_context,
        )

        domain_status = tracking_result.get("domain_status", {})
        if isinstance(adoption, dict):
            adoption["execution_tracking"] = {
                "last_tracked_at": tracking_result.get("tracked_at"),
                "domain_status": domain_status.get("status"),
                "mapped_state": tracking_result.get("mapped_execution_state"),
                "sync_result": tracking_result.get("sync_result"),
            }
            config["adoption"] = adoption
            task.config = config
            await self.session.flush()

        return {
            "task_id": task_id,
            "suggestion_id": suggestion_id,
            "target_domain": target_domain,
            "tracking": tracking_result,
        }

    def get_tracking_history(self, suggestion_id: str | None = None) -> list[dict[str, Any]]:
        if suggestion_id:
            return [r for r in self._tracking_history if r.get("suggestion_id") == suggestion_id]
        return list(self._tracking_history)

    async def _query_domain_status(
        self,
        domain: str,
        *,
        reference_id: str,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        try:
            client = await self._get_domain_client(domain)
            if client is None:
                return {"domain": domain, "status": "client_unavailable"}

            method_name = _DOMAIN_STATUS_METHOD.get(domain)
            if method_name is None:
                return {"domain": domain, "status": "unsupported_domain"}

            method = getattr(client, method_name, None)
            if not callable(method):
                return {"domain": domain, "status": "method_not_available"}

            if domain == "oms":
                result = await method(reference_id)
            else:
                result = await method(reference_id, audit_context=audit_context)
            return result if isinstance(result, dict) else {"domain": domain, "status": "unknown"}

        except Exception as e:
            logger.warning("查询域状态失败: domain=%s ref=%s error=%s", domain, reference_id, e)
            return {"domain": domain, "status": "query_failed", "error": str(e)}

    async def _get_domain_client(self, domain: str) -> Any:
        from src.infrastructure.erp_client_factory import get_erp_client_factory
        from src.repositories.erp_repository import ErpIntegrationRepository

        try:
            repo = ErpIntegrationRepository(self.session, tenant_id=self.tenant_id)
            system_type = ERPSystemType(domain)
            config = await repo.get_config(system_type, name="default")
            if config is None:
                logger.warning("域 %s 无ERP配置", domain)
                return None

            factory = get_erp_client_factory()
            return factory.get_client_from_config(system_type, config)
        except Exception as e:
            logger.warning("获取域客户端失败: domain=%s error=%s", domain, e)
            return None

    @staticmethod
    def _map_to_execution_state(domain: str, domain_status: str) -> RecommendationExecutionState | None:
        domain_mapping = _ERP_STATUS_TO_EXECUTION_STATE.get(domain, {})
        return domain_mapping.get(domain_status)
