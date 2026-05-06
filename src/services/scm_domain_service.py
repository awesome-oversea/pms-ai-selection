from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.infrastructure.scm_client import SCMClient
from src.models.enums import ERPSystemType, RecommendationExecutionState, can_transition
from src.repositories.erp_repository import ErpIntegrationRepository
from src.repositories.selection_repository import SelectionTaskRepository

logger = get_logger(__name__)


class SCMDomainService:
    """
    SCM 供应链管理领域服务。

    职责:
    - 供应商产品查询
    - 采购计划推送
    - 供应商报价获取
    - 采购建议创建
    - 供应链状态推进（13态状态机中 SCM_REVIEWING → SCM_APPROVED → SCM_ORDERED）
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.repo = ErpIntegrationRepository(session, tenant_id=self.tenant_id) if session is not None else None
        self.selection_repo = SelectionTaskRepository(session, tenant_id=self.tenant_id) if session is not None else None

    async def review_supply_chain(
        self,
        *,
        task_id: str,
        scm_name: str = "default",
        supplier_code: str | None = None,
        quantity: int = 200,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        current_state = self._get_current_state(config)

        if current_state is not None and not can_transition(current_state, RecommendationExecutionState.SCM_REVIEWING) and current_state != RecommendationExecutionState.SCM_REVIEWING:
            raise ValueError(f"当前状态 {current_state.value} 不允许进入 SCM 审核阶段")

        scm_data = config.get("scm") if isinstance(config.get("scm"), dict) else {}
        scm_data.setdefault("review_history", [])

        review_result: dict[str, Any] = {
            "task_id": task_id,
            "review_status": "pending_review",
            "supplier_code": supplier_code,
            "quantity": quantity,
            "reviewed_at": datetime.now(UTC).isoformat(),
        }

        if self.repo is not None:
            try:
                scm_config = await self.repo.get_config(ERPSystemType.SCM, name=scm_name)
                if scm_config is not None:
                    scm_client = self._build_scm_client(scm_config)
                    supplier_products = await scm_client.fetch_supplier_products(
                        supplier_code=supplier_code or "",
                        audit_context=self._build_audit_context(task_id=task_id, purpose="scm_review"),
                    )
                    review_result["supplier_products_count"] = len(supplier_products) if isinstance(supplier_products, list) else 0
                    review_result["supplier_products"] = supplier_products[:5] if isinstance(supplier_products, list) else []
            except Exception as e:
                logger.warning("SCM供应商产品查询失败: %s", e)
                review_result["supplier_query_error"] = str(e)

        scm_data["review_history"].append(review_result)
        config["scm"] = scm_data
        if current_state is not None and can_transition(current_state, RecommendationExecutionState.SCM_REVIEWING):
            config["erp_workflow_state"] = RecommendationExecutionState.SCM_REVIEWING.value
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return review_result

    async def approve_supply_chain(
        self,
        *,
        task_id: str,
        approved_quantity: int | None = None,
        approved_supplier: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        current_state = self._get_current_state(config)

        if current_state != RecommendationExecutionState.SCM_REVIEWING:
            raise ValueError(f"当前状态 {current_state.value if current_state else 'None'} 不允许审批，期望 SCM_REVIEWING")

        if not can_transition(current_state, RecommendationExecutionState.SCM_APPROVED):
            raise ValueError(f"不允许的状态转换: {current_state.value} → scm_approved")

        scm_data = config.get("scm") if isinstance(config.get("scm"), dict) else {}
        scm_data["approval"] = {
            "approved_quantity": approved_quantity,
            "approved_supplier": approved_supplier,
            "approved_at": datetime.now(UTC).isoformat(),
            "approved_by": self.actor.get("sub") or self.actor.get("user_id") or "system",
            "notes": notes,
        }
        config["scm"] = scm_data
        config["erp_workflow_state"] = RecommendationExecutionState.SCM_APPROVED.value
        self._append_state_history(config, current_state, RecommendationExecutionState.SCM_APPROVED, "SCM审批通过")
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "status": "scm_approved",
            "approved_quantity": approved_quantity,
            "approved_supplier": approved_supplier,
            "approved_at": scm_data["approval"]["approved_at"],
        }

    async def create_purchase_order(
        self,
        *,
        task_id: str,
        scm_name: str = "default",
        quantity: int = 200,
        supplier_code: str | None = None,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        current_state = self._get_current_state(config)

        if current_state != RecommendationExecutionState.SCM_APPROVED:
            raise ValueError(f"当前状态 {current_state.value if current_state else 'None'} 不允许创建采购单，期望 SCM_APPROVED")

        if not can_transition(current_state, RecommendationExecutionState.SCM_ORDERED):
            raise ValueError(f"不允许的状态转换: {current_state.value} → scm_ordered")

        scm_data = config.get("scm") if isinstance(config.get("scm"), dict) else {}
        purchase_order: dict[str, Any] = {
            "po_id": f"PO-{task_id[:8]}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            "task_id": task_id,
            "quantity": quantity,
            "supplier_code": supplier_code,
            "status": "created",
            "created_at": datetime.now(UTC).isoformat(),
        }

        if self.repo is not None:
            try:
                scm_config = await self.repo.get_config(ERPSystemType.SCM, name=scm_name)
                if scm_config is not None:
                    scm_client = self._build_scm_client(scm_config)
                    suggestion = await scm_client.create_purchase_suggestion(
                        payload={
                            "task_id": task_id,
                            "quantity": quantity,
                            "supplier_code": supplier_code,
                            "po_id": purchase_order["po_id"],
                        },
                        audit_context=self._build_audit_context(task_id=task_id, purpose="create_purchase_order"),
                    )
                    purchase_order["scm_suggestion"] = suggestion
                    purchase_order["status"] = "submitted"
            except Exception as e:
                logger.warning("SCM采购建议创建失败: %s", e)
                purchase_order["scm_error"] = str(e)

        scm_data["purchase_order"] = purchase_order
        config["scm"] = scm_data
        config["erp_workflow_state"] = RecommendationExecutionState.SCM_ORDERED.value
        self._append_state_history(config, current_state, RecommendationExecutionState.SCM_ORDERED, "SCM采购单已创建")
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "po_id": purchase_order["po_id"],
            "status": purchase_order["status"],
            "quantity": quantity,
            "supplier_code": supplier_code,
        }

    async def get_supply_chain_status(self, task_id: str) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        scm_data = config.get("scm") if isinstance(config.get("scm"), dict) else {}
        current_state = self._get_current_state(config)

        return {
            "task_id": task_id,
            "current_state": current_state.value if current_state else None,
            "approval": scm_data.get("approval"),
            "purchase_order": scm_data.get("purchase_order"),
            "review_count": len(scm_data.get("review_history", [])),
        }

    async def reject_supply_chain(
        self,
        *,
        task_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        current_state = self._get_current_state(config)

        if current_state != RecommendationExecutionState.SCM_REVIEWING:
            raise ValueError(f"当前状态 {current_state.value if current_state else 'None'} 不允许驳回，期望 SCM_REVIEWING")

        if not can_transition(current_state, RecommendationExecutionState.SCM_REJECTED):
            raise ValueError(f"不允许的状态转换: {current_state.value} → scm_rejected")

        scm_data = config.get("scm") if isinstance(config.get("scm"), dict) else {}
        scm_data["rejection"] = {
            "reason": reason,
            "rejected_at": datetime.now(UTC).isoformat(),
            "rejected_by": self.actor.get("sub") or self.actor.get("user_id") or "system",
        }
        config["scm"] = scm_data
        config["erp_workflow_state"] = RecommendationExecutionState.SCM_REJECTED.value
        self._append_state_history(config, current_state, RecommendationExecutionState.SCM_REJECTED, f"SCM驳回: {reason or '无原因'}")
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "status": "scm_rejected",
            "reason": reason,
            "rejected_at": scm_data["rejection"]["rejected_at"],
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
    def _build_scm_client(config: Any) -> SCMClient:
        extra = config.extra_config or {}
        return SCMClient(
            api_endpoint=config.api_endpoint,
            api_key=config.api_key,
            secret_key=config.secret_key,
            inbound_path=extra.get("inbound_path", "/supplier-products"),
            outbound_path=extra.get("outbound_path", "/product-plans"),
            timeout_seconds=float(extra.get("timeout_seconds", 10.0)),
        )

    @staticmethod
    def _build_audit_context(*, task_id: str, purpose: str) -> dict[str, Any]:
        return {
            "tenant_id": "system",
            "actor_type": "service",
            "actor_id": "pms-scm-service",
            "domain": "scm",
            "purpose": purpose,
            "trace_id": f"scm-{task_id}",
            "idempotency_key": f"scm-{purpose}-{task_id}",
        }
