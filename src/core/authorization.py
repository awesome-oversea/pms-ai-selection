"""
最小授权检查基线
================

将权限检查从 endpoint 下沉到 service 层的最小实现。
"""

from __future__ import annotations

from typing import Any

from src.core.exceptions import AuthorizationError
from src.core.rbac import ROLE_PERMISSIONS, derive_roles


def resolve_permissions(actor: dict[str, Any] | None) -> set[str]:
    roles = derive_roles(actor or {})
    permissions: set[str] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSIONS.get(role, set()))
    return permissions


def has_permission(actor: dict[str, Any] | None, permission: str) -> bool:
    return permission in resolve_permissions(actor)


def require_permission(actor: dict[str, Any] | None, permission: str, resource: str) -> None:
    if not has_permission(actor, permission):
        raise AuthorizationError(action=permission, resource=resource)
