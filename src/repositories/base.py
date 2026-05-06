"""
Repository 基础能力
===================

提供最小租户仓储基线，避免各仓储重复处理 tenant_id。
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tenant import get_default_tenant_id


class TenantScopedRepository:
    """最小租户仓储基类。"""

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, *, require_tenant: bool = True):
        self.session = session
        if tenant_id is None and require_tenant:
            tenant_id = get_default_tenant_id()
        self.tenant_id = tenant_id

    def require_tenant_id(self, tenant_id: str | None = None) -> str:
        resolved = tenant_id or self.tenant_id
        if not resolved:
            raise ValueError("tenant_id 不能为空")
        return str(resolved)

    def tenant_uuid(self, tenant_id: str | None = None) -> uuid.UUID:
        return uuid.UUID(self.require_tenant_id(tenant_id))
