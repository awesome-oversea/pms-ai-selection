from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.infrastructure.wms_client import WMSClient
from src.models.enums import ERPSystemType, RecommendationExecutionState, can_transition
from src.repositories.erp_repository import ErpIntegrationRepository
from src.repositories.selection_repository import SelectionTaskRepository

logger = get_logger(__name__)


class WMSDomainService:
    """
    WMS 仓储管理领域服务。

    职责:
    - 库存快照查询
    - 补货计划推送
    - 库龄/容量查询
    - 库存预留与确认
    - 仓储状态推进（13态状态机中 SCM_ORDERED → WMS_RESERVED → WMS_CONFIRMED）
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.repo = ErpIntegrationRepository(session, tenant_id=self.tenant_id) if session is not None else None
        self.selection_repo = SelectionTaskRepository(session, tenant_id=self.tenant_id) if session is not None else None

    async def reserve_inventory(
        self,
        *,
        task_id: str,
        wms_name: str = "default",
        sku_code: str | None = None,
        quantity: int = 200,
        warehouse_code: str | None = None,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        current_state = self._get_current_state(config)

        if current_state is not None and current_state != RecommendationExecutionState.SCM_ORDERED and not can_transition(current_state, RecommendationExecutionState.WMS_RESERVED):
            raise ValueError(f"当前状态 {current_state.value} 不允许库存预留，期望 SCM_ORDERED")

        wms_data = config.get("wms") if isinstance(config.get("wms"), dict) else {}
        reservation: dict[str, Any] = {
            "reservation_id": f"RES-{task_id[:8]}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            "task_id": task_id,
            "sku_code": sku_code,
            "quantity": quantity,
            "warehouse_code": warehouse_code,
            "status": "reserved",
            "reserved_at": datetime.now(UTC).isoformat(),
        }

        if self.repo is not None:
            try:
                wms_config = await self.repo.get_config(ERPSystemType.WMS, name=wms_name)
                if wms_config is not None:
                    wms_client = self._build_wms_client(wms_config)
                    create_result = await wms_client.create_reservation(
                        payload={
                            "task_id": task_id,
                            "sku_code": sku_code,
                            "quantity": quantity,
                            "warehouse_code": warehouse_code,
                            "reservation_id": reservation["reservation_id"],
                        },
                        audit_context=self._build_audit_context(task_id=task_id, purpose="reserve_inventory"),
                    )
                    reservation["wms_result"] = create_result
            except Exception as e:
                logger.warning("WMS库存预留失败: %s", e)
                reservation["wms_error"] = str(e)

        wms_data["reservation"] = reservation
        config["wms"] = wms_data
        if current_state is not None and can_transition(current_state, RecommendationExecutionState.WMS_RESERVED):
            config["erp_workflow_state"] = RecommendationExecutionState.WMS_RESERVED.value
            self._append_state_history(config, current_state, RecommendationExecutionState.WMS_RESERVED, "WMS库存已预留")
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "reservation_id": reservation["reservation_id"],
            "status": reservation["status"],
            "quantity": quantity,
            "sku_code": sku_code,
        }

    async def confirm_inventory(
        self,
        *,
        task_id: str,
        confirmed_quantity: int | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        current_state = self._get_current_state(config)

        if current_state != RecommendationExecutionState.WMS_RESERVED:
            raise ValueError(f"当前状态 {current_state.value if current_state else 'None'} 不允许确认，期望 WMS_RESERVED")

        if not can_transition(current_state, RecommendationExecutionState.WMS_CONFIRMED):
            raise ValueError(f"不允许的状态转换: {current_state.value} → wms_confirmed")

        wms_data = config.get("wms") if isinstance(config.get("wms"), dict) else {}
        reservation = wms_data.get("reservation") if isinstance(wms_data.get("reservation"), dict) else {}

        wms_data["confirmation"] = {
            "confirmed_quantity": confirmed_quantity or reservation.get("quantity"),
            "confirmed_at": datetime.now(UTC).isoformat(),
            "confirmed_by": self.actor.get("sub") or self.actor.get("user_id") or "system",
            "notes": notes,
        }
        if isinstance(reservation, dict):
            reservation["status"] = "confirmed"
        config["wms"] = wms_data
        config["erp_workflow_state"] = RecommendationExecutionState.WMS_CONFIRMED.value
        self._append_state_history(config, current_state, RecommendationExecutionState.WMS_CONFIRMED, "WMS库存已确认")
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "reservation_id": reservation.get("reservation_id") if isinstance(reservation, dict) else None,
            "status": "confirmed",
            "confirmed_quantity": confirmed_quantity or reservation.get("quantity") if isinstance(reservation, dict) else confirmed_quantity,
            "confirmed_at": wms_data["confirmation"]["confirmed_at"],
        }

    async def get_inventory_status(self, task_id: str) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        wms_data = config.get("wms") if isinstance(config.get("wms"), dict) else {}
        current_state = self._get_current_state(config)

        return {
            "task_id": task_id,
            "current_state": current_state.value if current_state else None,
            "reservation": wms_data.get("reservation"),
            "confirmation": wms_data.get("confirmation"),
        }

    async def fetch_inventory_snapshots(
        self,
        *,
        task_id: str,
        wms_name: str = "default",
    ) -> dict[str, Any]:
        if self.repo is None:
            return {"task_id": task_id, "snapshots": [], "error": "仓储未初始化"}

        try:
            wms_config = await self.repo.get_config(ERPSystemType.WMS, name=wms_name)
            if wms_config is None:
                return {"task_id": task_id, "snapshots": [], "error": "WMS配置不存在"}

            wms_client = self._build_wms_client(wms_config)
            snapshots = await wms_client.fetch_inventory_snapshots(
                audit_context=self._build_audit_context(task_id=task_id, purpose="fetch_inventory_snapshots"),
            )
            return {"task_id": task_id, "snapshots": snapshots}
        except Exception as e:
            logger.warning("WMS库存快照查询失败: %s", e)
            return {"task_id": task_id, "snapshots": [], "error": str(e)}

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
    def _build_wms_client(config: Any) -> WMSClient:
        extra = config.extra_config or {}
        return WMSClient(
            api_endpoint=config.api_endpoint,
            api_key=config.api_key,
            secret_key=config.secret_key,
            inbound_path=extra.get("inbound_path", "/inventory-snapshots"),
            outbound_path=extra.get("outbound_path", "/replenishment-plans"),
            timeout_seconds=float(extra.get("timeout_seconds", 10.0)),
        )

    @staticmethod
    def _build_audit_context(*, task_id: str, purpose: str) -> dict[str, Any]:
        return {
            "tenant_id": "system",
            "actor_type": "service",
            "actor_id": "pms-wms-service",
            "domain": "wms",
            "purpose": purpose,
            "trace_id": f"wms-{task_id}",
            "idempotency_key": f"wms-{purpose}-{task_id}",
        }
