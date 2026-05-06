from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.enums import RecommendationExecutionState, can_transition
from src.repositories.erp_repository import ErpIntegrationRepository
from src.repositories.selection_repository import SelectionTaskRepository
from src.services.erp_integration_service import ErpIntegrationService
from src.services.ms_service import MasterDataService

logger = get_logger(__name__)


class ERPWorkflowService:
    """
    ERP 闭环编排服务。

    作为跨域编排主入口，串联 PMS 建议池 → ERP 六域执行 → 回流闭环。
    基于 13 态状态机驱动流程推进。
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.repo = ErpIntegrationRepository(session, tenant_id=self.tenant_id) if session is not None else None
        self.selection_repo = SelectionTaskRepository(session, tenant_id=self.tenant_id) if session is not None else None
        self.erp_service = ErpIntegrationService(session, tenant_id=self.tenant_id, actor=self.actor)
        self.ms_service = MasterDataService(session, tenant_id=self.tenant_id, actor=self.actor)

    async def orchestrate_adoption(
        self,
        *,
        task_id: str,
        scm_name: str = "default",
        wms_name: str = "default",
        oms_name: str = "default",
        som_name: str = "default",
        pdm_name: str = "default",
        quantity: int = 200,
        supplier_code: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """
        编排"选品采纳"全流程: PMS_APPROVED → ERP_SUBMITTED → SCM → WMS → OMS。

        基于状态机推进，每步校验合法转换。
        """
        current_state = await self._get_execution_state(task_id)
        if current_state is None:
            current_state = RecommendationExecutionState.SUGGESTED

        if not can_transition(current_state, RecommendationExecutionState.PMS_APPROVED):
            if current_state == RecommendationExecutionState.PMS_APPROVED:
                pass
            else:
                raise ValueError(f"当前状态 {current_state.value} 不允许执行采纳编排，期望 SUGGESTED 或 PMS_APPROVED")

        ms_result = await self.ms_service.create_product_from_selection(
            task_id=task_id,
            pdm_name=pdm_name,
            notes=notes,
        )

        await self._advance_state(
            task_id=task_id,
            from_state=current_state,
            to_state=RecommendationExecutionState.ERP_SUBMITTED,
            detail="MS商品草稿已创建，提交至ERP执行",
        )

        adoption_result = await self.erp_service.execute_selection_adoption(
            task_id=task_id,
            scm_name=scm_name,
            wms_name=wms_name,
            oms_name=oms_name,
            som_name=som_name,
            quantity=quantity,
            supplier_code=supplier_code,
            notes=notes,
        )

        execution_status = (adoption_result.get("execution_status") or {})
        scm_status = (execution_status.get("scm") or {}).get("status")
        wms_status = (execution_status.get("wms") or {}).get("status")
        som_status = (execution_status.get("som") or {}).get("status")

        if scm_status in {"pending_review", "approved"}:
            await self._advance_state(
                task_id=task_id,
                from_state=RecommendationExecutionState.ERP_SUBMITTED,
                to_state=RecommendationExecutionState.SCM_REVIEWING,
                detail=f"SCM状态: {scm_status}",
            )

        if scm_status == "approved" or scm_status == "pending_review":
            target_scm = RecommendationExecutionState.SCM_APPROVED if scm_status == "approved" else RecommendationExecutionState.SCM_REVIEWING
            if can_transition(RecommendationExecutionState.SCM_REVIEWING, target_scm):
                await self._advance_state(
                    task_id=task_id,
                    from_state=RecommendationExecutionState.SCM_REVIEWING,
                    to_state=target_scm,
                    detail=f"SCM状态推进: {scm_status}",
                )

        if scm_status in {"ordered", "completed"} and can_transition(RecommendationExecutionState.SCM_APPROVED, RecommendationExecutionState.SCM_ORDERED):
            await self._advance_state(
                task_id=task_id,
                from_state=RecommendationExecutionState.SCM_APPROVED,
                to_state=RecommendationExecutionState.SCM_ORDERED,
                detail=f"SCM已下单: {scm_status}",
            )

        if wms_status in {"reserved", "allocated"} and can_transition(RecommendationExecutionState.SCM_ORDERED, RecommendationExecutionState.WMS_RESERVED):
            await self._advance_state(
                task_id=task_id,
                from_state=RecommendationExecutionState.SCM_ORDERED,
                to_state=RecommendationExecutionState.WMS_RESERVED,
                detail=f"WMS已预留: {wms_status}",
            )

        if wms_status == "confirmed" and can_transition(RecommendationExecutionState.WMS_RESERVED, RecommendationExecutionState.WMS_CONFIRMED):
            await self._advance_state(
                task_id=task_id,
                from_state=RecommendationExecutionState.WMS_RESERVED,
                to_state=RecommendationExecutionState.WMS_CONFIRMED,
                detail="WMS已确认",
            )

        if som_status in {"pending_approval", "draft_created"} and can_transition(RecommendationExecutionState.WMS_CONFIRMED, RecommendationExecutionState.OMS_DRAFT_CREATED):
            await self._advance_state(
                task_id=task_id,
                from_state=RecommendationExecutionState.WMS_CONFIRMED,
                to_state=RecommendationExecutionState.OMS_DRAFT_CREATED,
                detail=f"OMS/SOM草稿已创建: {som_status}",
            )

        final_state = await self._get_execution_state(task_id)

        return {
            "task_id": task_id,
            "orchestration_type": "adoption",
            "ms_result": ms_result,
            "adoption_result": adoption_result,
            "state_machine": {
                "initial_state": current_state.value,
                "final_state": final_state.value if final_state else None,
            },
            "completed_at": datetime.now(UTC).isoformat(),
        }

    async def orchestrate_close_loop(
        self,
        *,
        task_id: str,
        oms_name: str = "default",
        scm_name: str = "default",
        wms_name: str = "default",
        crm_name: str = "default",
        fms_name: str = "default",
        paas_name: str = "default",
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        编排"闭环回流"全流程: OMS_ACTIVE → CLOSED。

        同步 OMS/CRM/FMS/WMS 执行反馈，更新闭环状态，触发自动再评分。
        """
        current_state = await self._get_execution_state(task_id)
        if current_state is None:
            current_state = RecommendationExecutionState.OMS_DRAFT_CREATED

        close_loop_result = await self.erp_service.close_selection_loop(
            task_id=task_id,
            oms_name=oms_name,
            scm_name=scm_name,
            wms_name=wms_name,
            crm_name=crm_name,
            fms_name=fms_name,
            paas_name=paas_name,
            limit=limit,
        )

        feedback_sync_result = None
        try:
            feedback_sync_result = await self.erp_service.sync_selection_execution_feedback(
                task_id=task_id,
                oms_name=oms_name,
                crm_name=crm_name,
                fms_name=fms_name,
                wms_name=wms_name,
                auto_rescore=True,
            )
        except Exception as e:
            logger.warning("闭环回流中执行反馈同步失败: %s", e)

        if close_loop_result.get("summary", {}).get("close_loop_completed") and current_state in {
            RecommendationExecutionState.OMS_DRAFT_CREATED,
            RecommendationExecutionState.OMS_PUBLISHED,
            RecommendationExecutionState.OMS_ACTIVE,
        } and can_transition(current_state, RecommendationExecutionState.CLOSED):
            await self._advance_state(
                task_id=task_id,
                from_state=current_state,
                to_state=RecommendationExecutionState.CLOSED,
                detail="闭环回流完成",
            )

        final_state = await self._get_execution_state(task_id)

        return {
            "task_id": task_id,
            "orchestration_type": "close_loop",
            "close_loop_result": close_loop_result,
            "feedback_sync_result": feedback_sync_result,
            "state_machine": {
                "initial_state": current_state.value,
                "final_state": final_state.value if final_state else None,
            },
            "completed_at": datetime.now(UTC).isoformat(),
        }

    async def get_workflow_status(self, task_id: str) -> dict[str, Any]:
        current_state = await self._get_execution_state(task_id)
        from src.models.enums import get_valid_transitions, is_terminal_state

        if current_state is None:
            return {
                "task_id": task_id,
                "current_state": None,
                "valid_transitions": ["suggested"],
                "is_terminal": False,
                "state_history": [],
            }

        valid_next = get_valid_transitions(current_state)
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        state_history = config.get("erp_workflow_state_history") or []

        return {
            "task_id": task_id,
            "current_state": current_state.value,
            "valid_transitions": [s.value for s in valid_next],
            "is_terminal": is_terminal_state(current_state),
            "state_history": state_history,
        }

    async def advance_state(
        self,
        task_id: str,
        *,
        target_state: RecommendationExecutionState,
        detail: str | None = None,
    ) -> dict[str, Any]:
        current_state = await self._get_execution_state(task_id)
        if current_state is None:
            current_state = RecommendationExecutionState.SUGGESTED

        if not can_transition(current_state, target_state):
            raise ValueError(f"不允许的状态转换: {current_state.value} → {target_state.value}")

        await self._advance_state(
            task_id=task_id,
            from_state=current_state,
            to_state=target_state,
            detail=detail or f"手动推进: {current_state.value} → {target_state.value}",
        )

        return {
            "task_id": task_id,
            "previous_state": current_state.value,
            "current_state": target_state.value,
            "detail": detail,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    async def _get_execution_state(self, task_id: str) -> RecommendationExecutionState | None:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        state_value = config.get("erp_workflow_state")
        if state_value is None:
            return None
        try:
            return RecommendationExecutionState(state_value)
        except ValueError:
            return None

    async def _advance_state(
        self,
        *,
        task_id: str,
        from_state: RecommendationExecutionState,
        to_state: RecommendationExecutionState,
        detail: str,
    ) -> None:
        if not can_transition(from_state, to_state):
            raise ValueError(f"不允许的状态转换: {from_state.value} → {to_state.value}")

        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        config["erp_workflow_state"] = to_state.value
        config["erp_workflow_state_updated_at"] = datetime.now(UTC).isoformat()
        history = config.get("erp_workflow_state_history") or []
        history.append({
            "from": from_state.value,
            "to": to_state.value,
            "detail": detail,
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": self.actor.get("sub") or self.actor.get("user_id") or "system",
        })
        config["erp_workflow_state_history"] = history
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

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
