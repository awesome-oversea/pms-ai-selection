"""
租户 Repository
===============

为 Phase 5 多租户改造提供最小数据访问能力：
- 获取租户
- 通过 tenant_key 查找租户
- 获取或创建默认租户
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.core.tenant import DEFAULT_TENANT_KEY, DEFAULT_TENANT_NAME, DEFAULT_TENANT_UUID

logger = get_logger(__name__)


class TenantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_tenants(self, limit: int = 100) -> list[Any]:
        from src.models.models import Tenant

        result = await self.session.execute(
            select(Tenant).where(Tenant.is_deleted == False).order_by(Tenant.created_at.desc()).limit(limit)  # noqa: E712
        )
        return list(result.scalars().all())

    async def get_tenant(self, tenant_id: UUID) -> Any | None:
        from src.models.models import Tenant

        result = await self.session.execute(
            select(Tenant).where(
                Tenant.id == tenant_id,
                Tenant.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_tenant_by_key(self, tenant_key: str) -> Any | None:
        from src.models.models import Tenant

        result = await self.session.execute(
            select(Tenant).where(
                Tenant.tenant_key == tenant_key,
                Tenant.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_default_tenant(self) -> Any:
        from src.models.models import Tenant

        tenant = await self.get_tenant_by_key(DEFAULT_TENANT_KEY)
        if tenant is not None:
            return tenant

        tenant = Tenant(
            id=DEFAULT_TENANT_UUID,
            name=DEFAULT_TENANT_NAME,
            tenant_key=DEFAULT_TENANT_KEY,
            status="active",
            is_active=True,
            config={"bootstrap": True},
        )
        self.session.add(tenant)
        await self.session.flush()
        logger.info(f"✅ 创建默认租户: {tenant.id}")
        return tenant
