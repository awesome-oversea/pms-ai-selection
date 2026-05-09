from __future__ import annotations

from typing import Any

from src.core.logging import get_logger
from src.core.pms_governance import AuditContext
from src.infrastructure.database import get_async_session_factory
from src.infrastructure.fba_client import FBAClient, FBAClientError
from src.services.fba_restock_service import FBARestockService

logger = get_logger(__name__)


class FbaDomainService:
    """
    FBA域服务。

    职责:
    - 封装FBA域ERP客户端调用
    - 协调FBA补货建议的创建、审批、提交全流程
    - 管理FBA域数据同步
    """

    def __init__(self, fba_client: FBAClient, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.fba_client = fba_client
        self.tenant_id = tenant_id
        self.actor = actor or {}

    async def generate_and_submit_restock(
        self,
        *,
        product_id: str,
        sku: str | None = None,
        fnsku: str | None = None,
        asin: str | None = None,
        current_stock: int | None = None,
        inbound_quantity: int | None = None,
        daily_velocity: float | None = None,
        lead_time_days: int | None = None,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            try:
                fba_service = FBARestockService(session, tenant_id=self.tenant_id, actor=self.actor)
                suggestion = await fba_service.generate_restock_suggestion(
                    product_id=product_id,
                    sku=sku,
                    fnsku=fnsku,
                    asin=asin,
                    current_stock=current_stock,
                    inbound_quantity=inbound_quantity,
                    daily_velocity=daily_velocity,
                    lead_time_days=lead_time_days,
                    marketplace=marketplace,
                )
                await session.commit()
                return suggestion
            except Exception:
                await session.rollback()
                raise

    async def batch_generate_restock(
        self,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            try:
                fba_service = FBARestockService(session, tenant_id=self.tenant_id, actor=self.actor)
                result = await fba_service.batch_generate_restock_suggestions(items)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    async def push_suggestion_to_erp(self, suggestion_id: str) -> dict[str, Any]:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            try:
                fba_service = FBARestockService(session, tenant_id=self.tenant_id, actor=self.actor)
                result = await fba_service.submit_to_fba_domain(suggestion_id, self.fba_client)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    async def get_inventory_levels(
        self,
        sku: str | None = None,
        asin: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.fba_client.get_inventory_levels(sku=sku, asin=asin, audit_context=audit_context)
        except FBAClientError as e:
            logger.error("获取FBA库存水平失败: sku=%s asin=%s error=%s", sku, asin, e)
            raise

    async def health_check(self) -> dict[str, Any]:
        try:
            return await self.fba_client.test_connection()
        except FBAClientError as e:
            return {"status": "unhealthy", "error": str(e), "error_code": e.error_code}
