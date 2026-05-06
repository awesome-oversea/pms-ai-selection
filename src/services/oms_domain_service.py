from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.infrastructure.oms_client import OMSClient
from src.models.enums import ERPSystemType, RecommendationExecutionState, can_transition
from src.repositories.erp_repository import ErpIntegrationRepository
from src.repositories.selection_repository import SelectionTaskRepository

logger = get_logger(__name__)


class OMSDomainService:
    """
    OMS 订单管理领域服务。

    职责:
    - 商品/订单数据同步
    - Listing草稿推送
    - 销售指标获取
    - 订单状态推进（13态状态机中 WMS_CONFIRMED → OMS_DRAFT_CREATED → OMS_PUBLISHED → OMS_ACTIVE）
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.repo = ErpIntegrationRepository(session, tenant_id=self.tenant_id) if session is not None else None
        self.selection_repo = SelectionTaskRepository(session, tenant_id=self.tenant_id) if session is not None else None

    async def create_listing_draft(
        self,
        *,
        task_id: str,
        oms_name: str = "default",
        title: str | None = None,
        price: float | None = None,
        sku_code: str | None = None,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        current_state = self._get_current_state(config)

        if current_state is not None and current_state not in {
            RecommendationExecutionState.WMS_CONFIRMED,
            RecommendationExecutionState.OMS_DRAFT_CREATED,
        } and not can_transition(current_state, RecommendationExecutionState.OMS_DRAFT_CREATED):
            raise ValueError(f"当前状态 {current_state.value} 不允许创建Listing草稿，期望 WMS_CONFIRMED")

        oms_data = config.get("oms") if isinstance(config.get("oms"), dict) else {}
        listing_draft: dict[str, Any] = {
            "listing_id": f"LST-{task_id[:8]}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            "task_id": task_id,
            "title": title,
            "price": price,
            "sku_code": sku_code,
            "marketplace": marketplace,
            "status": "draft",
            "created_at": datetime.now(UTC).isoformat(),
        }

        if self.repo is not None:
            try:
                oms_config = await self.repo.get_config(ERPSystemType.OMS, name=oms_name)
                if oms_config is not None:
                    oms_client = self._build_oms_client(oms_config)
                    push_result = await oms_client.push_listing_draft(
                        payload=listing_draft,
                    )
                    listing_draft["oms_push_result"] = push_result
                    listing_draft["status"] = "draft_pushed"
            except Exception as e:
                logger.warning("OMS Listing草稿推送失败: %s", e)
                listing_draft["oms_error"] = str(e)

        oms_data["listing_draft"] = listing_draft
        config["oms"] = oms_data
        if current_state is not None and can_transition(current_state, RecommendationExecutionState.OMS_DRAFT_CREATED):
            config["erp_workflow_state"] = RecommendationExecutionState.OMS_DRAFT_CREATED.value
            self._append_state_history(config, current_state, RecommendationExecutionState.OMS_DRAFT_CREATED, "OMS Listing草稿已创建")
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "listing_id": listing_draft["listing_id"],
            "status": listing_draft["status"],
            "title": title,
            "price": price,
            "marketplace": marketplace,
        }

    async def publish_listing(
        self,
        *,
        task_id: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        current_state = self._get_current_state(config)

        if current_state != RecommendationExecutionState.OMS_DRAFT_CREATED:
            raise ValueError(f"当前状态 {current_state.value if current_state else 'None'} 不允许发布，期望 OMS_DRAFT_CREATED")

        if not can_transition(current_state, RecommendationExecutionState.OMS_PUBLISHED):
            raise ValueError(f"不允许的状态转换: {current_state.value} → oms_published")

        oms_data = config.get("oms") if isinstance(config.get("oms"), dict) else {}
        listing_draft = oms_data.get("listing_draft") if isinstance(oms_data.get("listing_draft"), dict) else {}

        oms_data["publication"] = {
            "published_at": datetime.now(UTC).isoformat(),
            "published_by": self.actor.get("sub") or self.actor.get("user_id") or "system",
            "notes": notes,
        }
        if isinstance(listing_draft, dict):
            listing_draft["status"] = "published"
        config["oms"] = oms_data
        config["erp_workflow_state"] = RecommendationExecutionState.OMS_PUBLISHED.value
        self._append_state_history(config, current_state, RecommendationExecutionState.OMS_PUBLISHED, "OMS Listing已发布")
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "listing_id": listing_draft.get("listing_id") if isinstance(listing_draft, dict) else None,
            "status": "published",
            "published_at": oms_data["publication"]["published_at"],
        }

    async def activate_listing(
        self,
        *,
        task_id: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        current_state = self._get_current_state(config)

        if current_state != RecommendationExecutionState.OMS_PUBLISHED:
            raise ValueError(f"当前状态 {current_state.value if current_state else 'None'} 不允许激活，期望 OMS_PUBLISHED")

        if not can_transition(current_state, RecommendationExecutionState.OMS_ACTIVE):
            raise ValueError(f"不允许的状态转换: {current_state.value} → oms_active")

        oms_data = config.get("oms") if isinstance(config.get("oms"), dict) else {}
        listing_draft = oms_data.get("listing_draft") if isinstance(oms_data.get("listing_draft"), dict) else {}

        oms_data["activation"] = {
            "activated_at": datetime.now(UTC).isoformat(),
            "activated_by": self.actor.get("sub") or self.actor.get("user_id") or "system",
            "notes": notes,
        }
        if isinstance(listing_draft, dict):
            listing_draft["status"] = "active"
        config["oms"] = oms_data
        config["erp_workflow_state"] = RecommendationExecutionState.OMS_ACTIVE.value
        self._append_state_history(config, current_state, RecommendationExecutionState.OMS_ACTIVE, "OMS Listing已激活上线")
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "listing_id": listing_draft.get("listing_id") if isinstance(listing_draft, dict) else None,
            "status": "active",
            "activated_at": oms_data["activation"]["activated_at"],
        }

    async def get_order_status(self, task_id: str) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        oms_data = config.get("oms") if isinstance(config.get("oms"), dict) else {}
        current_state = self._get_current_state(config)

        return {
            "task_id": task_id,
            "current_state": current_state.value if current_state else None,
            "listing_draft": oms_data.get("listing_draft"),
            "publication": oms_data.get("publication"),
            "activation": oms_data.get("activation"),
        }

    async def fetch_sales_metrics(
        self,
        *,
        task_id: str,
        oms_name: str = "default",
    ) -> dict[str, Any]:
        if self.repo is None:
            return {"task_id": task_id, "metrics": [], "error": "仓储未初始化"}

        try:
            oms_config = await self.repo.get_config(ERPSystemType.OMS, name=oms_name)
            if oms_config is None:
                return {"task_id": task_id, "metrics": [], "error": "OMS配置不存在"}

            oms_client = self._build_oms_client(oms_config)
            metrics = await oms_client.fetch_sales_metrics()
            return {"task_id": task_id, "metrics": metrics}
        except Exception as e:
            logger.warning("OMS销售指标查询失败: %s", e)
            return {"task_id": task_id, "metrics": [], "error": str(e)}

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
    def _get_current_state(config: dict) -> RecommendationExecutionState | None:
        state_value = config.get("erp_workflow_state")
        if state_value is None:
            return None
        try:
            return RecommendationExecutionState(state_value)
        except ValueError:
            return None

    @staticmethod
    def _append_state_history(config: dict, from_state: RecommendationExecutionState | None, to_state: RecommendationExecutionState, detail: str) -> None:
        history = config.get("erp_workflow_state_history") or []
        history.append({
            "from": from_state.value if from_state else None,
            "to": to_state.value,
            "detail": detail,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        config["erp_workflow_state_history"] = history

    @staticmethod
    def _build_oms_client(config: Any) -> OMSClient:
        extra = config.extra_config or {}
        return OMSClient(
            api_endpoint=config.api_endpoint,
            api_key=config.api_key,
            secret_key=config.secret_key,
            inbound_path=extra.get("inbound_path", "/products"),
            outbound_path=extra.get("outbound_path", "/listings"),
            timeout_seconds=float(extra.get("timeout_seconds", 10.0)),
        )

    @staticmethod
    def _build_audit_context(*, task_id: str, purpose: str) -> dict[str, Any]:
        return {
            "tenant_id": "system",
            "actor_type": "service",
            "actor_id": "pms-oms-service",
            "domain": "oms",
            "purpose": purpose,
            "trace_id": f"oms-{task_id}",
            "idempotency_key": f"oms-{purpose}-{task_id}",
        }
