"""
租户上下文与默认租户工具
======================

提供 Phase 5 的最小多租户基础能力：
- 默认租户常量
- TenantContext 数据结构
- 从 token / actor / 任意上下文中解析租户信息
- 向 metadata 注入 tenant 字段
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from src.core.exceptions import AuthenticationError

DEFAULT_TENANT_KEY = "default"
DEFAULT_TENANT_NAME = "默认租户"
DEFAULT_TENANT_UUID = uuid.uuid5(uuid.NAMESPACE_DNS, "fms.default.tenant")


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    tenant_key: str | None = DEFAULT_TENANT_KEY
    tenant_name: str | None = DEFAULT_TENANT_NAME
    is_default: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_key": self.tenant_key,
            "tenant_name": self.tenant_name,
            "is_default_tenant": self.is_default,
        }


def get_default_tenant_id() -> str:
    return str(DEFAULT_TENANT_UUID)


def get_default_tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id=get_default_tenant_id(),
        tenant_key=DEFAULT_TENANT_KEY,
        tenant_name=DEFAULT_TENANT_NAME,
        is_default=True,
    )


def resolve_tenant_context(source: dict[str, Any] | None = None) -> TenantContext:
    from src.config.settings import get_settings

    payload = source or {}
    tenant_id = payload.get("tenant_id")

    # 当要求显式租户时，不允许默认回退
    if get_settings().security.require_explicit_tenant and not tenant_id:
        raise AuthenticationError("tenant_id is required when require_explicit_tenant is True")

    tenant_id = str(tenant_id or get_default_tenant_id())
    require_explicit_tenant = get_settings().security.require_explicit_tenant
    tenant_key = payload.get("tenant_key")
    tenant_name = payload.get("tenant_name")
    if not require_explicit_tenant:
        tenant_key = tenant_key or DEFAULT_TENANT_KEY
        tenant_name = tenant_name or DEFAULT_TENANT_NAME

    return TenantContext(
        tenant_id=tenant_id,
        tenant_key=tenant_key,
        tenant_name=tenant_name,
        is_default=tenant_id == get_default_tenant_id(),
    )


def inject_tenant_metadata(
    metadata: dict[str, Any] | None,
    tenant_context: TenantContext | None,
) -> dict[str, Any]:
    result = dict(metadata or {})
    context = tenant_context or get_default_tenant_context()
    result.update(context.to_dict())
    return result
