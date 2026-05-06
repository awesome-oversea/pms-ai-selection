"""
租户配置 Repository
===================

提供 T6.5 最小 Prompt / Route Policy 配置化能力：
- 获取配置
- 新增/更新配置
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TenantConfigRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_config(self, *, tenant_id: str, config_key: str) -> Any | None:
        from src.models.models import TenantConfig

        tenant_uuid = UUID(str(tenant_id))
        result = await self.session.execute(
            select(TenantConfig).where(
                TenantConfig.tenant_id == tenant_uuid,
                TenantConfig.config_key == config_key,
                TenantConfig.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def list_configs(self, *, tenant_id: str, limit: int = 100) -> list[Any]:
        from src.models.models import TenantConfig

        tenant_uuid = UUID(str(tenant_id))
        result = await self.session.execute(
            select(TenantConfig)
            .where(
                TenantConfig.tenant_id == tenant_uuid,
                TenantConfig.is_active == True,  # noqa: E712
            )
            .order_by(TenantConfig.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def upsert_config(self, *, tenant_id: str, config_key: str, config_value: dict[str, Any]) -> Any:
        from src.models.models import TenantConfig

        tenant_uuid = UUID(str(tenant_id))
        config = await self.get_config(tenant_id=tenant_id, config_key=config_key)
        if config is None:
            config = TenantConfig(
                tenant_id=tenant_uuid,
                config_key=config_key,
                config_value=config_value,
                is_active=True,
            )
            self.session.add(config)
        else:
            config.config_value = config_value
            config.is_active = True
        await self.session.flush()
        return config
