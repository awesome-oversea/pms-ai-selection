from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.infrastructure.crm_client import CRMClient
from src.models.enums import ERPSystemType
from src.repositories.erp_repository import ErpIntegrationRepository
from src.repositories.selection_repository import SelectionTaskRepository

logger = get_logger(__name__)


class CRMDomainService:
    """
    CRM 客户关系管理领域服务。

    职责:
    - 客户反馈查询
    - 投诉数据获取
    - 跟进记录推送
    - 客户满意度分析
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.repo = ErpIntegrationRepository(session, tenant_id=self.tenant_id) if session is not None else None
        self.selection_repo = SelectionTaskRepository(session, tenant_id=self.tenant_id) if session is not None else None

    async def fetch_customer_feedbacks(
        self,
        *,
        task_id: str,
        crm_name: str = "default",
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}

        feedbacks: list[dict[str, Any]] = []
        if self.repo is not None:
            try:
                crm_config = await self.repo.get_config(ERPSystemType.CRM, name=crm_name)
                if crm_config is not None:
                    crm_client = self._build_crm_client(crm_config)
                    feedbacks = await crm_client.fetch_customer_feedbacks()
            except Exception as e:
                logger.warning("CRM客户反馈查询失败: %s", e)

        crm_data = config.get("crm") if isinstance(config.get("crm"), dict) else {}
        crm_data["feedbacks"] = feedbacks
        crm_data["feedbacks_fetched_at"] = datetime.now(UTC).isoformat()
        config["crm"] = crm_data
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "feedbacks_count": len(feedbacks),
            "feedbacks": feedbacks[:20],
            "fetched_at": crm_data["feedbacks_fetched_at"],
        }

    async def fetch_complaints(
        self,
        *,
        task_id: str,
        crm_name: str = "default",
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}

        complaints: list[dict[str, Any]] = []
        if self.repo is not None:
            try:
                crm_config = await self.repo.get_config(ERPSystemType.CRM, name=crm_name)
                if crm_config is not None:
                    crm_client = self._build_crm_client(crm_config)
                    complaints = await crm_client.fetch_complaints()
            except Exception as e:
                logger.warning("CRM投诉数据查询失败: %s", e)

        crm_data = config.get("crm") if isinstance(config.get("crm"), dict) else {}
        crm_data["complaints"] = complaints
        crm_data["complaints_fetched_at"] = datetime.now(UTC).isoformat()
        config["crm"] = crm_data
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "complaints_count": len(complaints),
            "complaints": complaints[:20],
            "fetched_at": crm_data["complaints_fetched_at"],
        }

    async def push_followup(
        self,
        *,
        task_id: str,
        crm_name: str = "default",
        followup_type: str = "general",
        content: str | None = None,
        customer_id: str | None = None,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}

        followup_payload: dict[str, Any] = {
            "task_id": task_id,
            "followup_type": followup_type,
            "content": content,
            "customer_id": customer_id,
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": self.actor.get("sub") or self.actor.get("user_id") or "system",
        }

        push_result: dict[str, Any] = {"status": "pending"}
        if self.repo is not None:
            try:
                crm_config = await self.repo.get_config(ERPSystemType.CRM, name=crm_name)
                if crm_config is not None:
                    crm_client = self._build_crm_client(crm_config)
                    await crm_client.push_followups(followup_payload)
                    push_result = {"status": "pushed"}
            except Exception as e:
                logger.warning("CRM跟进记录推送失败: %s", e)
                push_result = {"status": "error", "error": str(e)}

        crm_data = config.get("crm") if isinstance(config.get("crm"), dict) else {}
        crm_data.setdefault("followups", [])
        crm_data["followups"].append({
            "payload": followup_payload,
            "result": push_result,
        })
        config["crm"] = crm_data
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "followup_type": followup_type,
            "push_status": push_result["status"],
        }

    async def get_crm_summary(self, task_id: str) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        crm_data = config.get("crm") if isinstance(config.get("crm"), dict) else {}

        return {
            "task_id": task_id,
            "feedbacks_count": len(crm_data.get("feedbacks", [])),
            "complaints_count": len(crm_data.get("complaints", [])),
            "followups_count": len(crm_data.get("followups", [])),
            "last_feedbacks_fetched_at": crm_data.get("feedbacks_fetched_at"),
            "last_complaints_fetched_at": crm_data.get("complaints_fetched_at"),
        }

    async def _get_selection_task(self, task_id: str) -> Any:
        if self.selection_repo is None:
            raise ValueError("选品任务仓储未初始化")
        from uuid import UUID
        try:
            normalized_task_id: Any = UUID(str(task_id))
        except ValueError:
            normalized_task_id = task_id
        task = await self.selection_repo.get_task(normalized_task_id)
        if task is None:
            raise ValueError(f"选品任务不存在: {task_id}")
        return task

    @staticmethod
    def _build_crm_client(config: Any) -> CRMClient:
        extra = config.extra_config or {}
        return CRMClient(
            api_endpoint=config.api_endpoint,
            api_key=config.api_key,
            secret_key=config.secret_key,
            inbound_path=extra.get("inbound_path", "/feedbacks"),
            outbound_path=extra.get("outbound_path", "/followups"),
            timeout_seconds=float(extra.get("timeout_seconds", 10.0)),
        )
