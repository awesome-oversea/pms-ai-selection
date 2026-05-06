"""
基础安全与审计工具
================

提供当前阶段最小可用的：
- 角色权限依赖
- 操作人提取
- 审计日志记录与查询

说明：
- 当前阶段采用进程内审计存储，满足 Phase 4 最小验收
- 后续可替换为数据库或日志平台实现，而不改 API 契约
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends

from src.core.auth import get_current_user, get_current_user_optional
from src.core.exceptions import AuthorizationError
from src.core.rbac import derive_roles
from src.core.tenant import get_default_tenant_context
from src.infrastructure.database import get_async_session_factory
from src.infrastructure.tracing import get_request_id, get_trace_id

_AUDIT_LOGS: list[dict[str, Any]] = []
_MAX_AUDIT_LOGS = 1000


async def get_actor(current_user: dict[str, Any] | None = Depends(get_current_user_optional)) -> dict[str, Any]:
    """返回当前操作人；匿名请求也会有统一 actor 结构。"""
    from src.config.settings import get_settings

    default_tenant = get_default_tenant_context()
    require_explicit_tenant = get_settings().security.require_explicit_tenant

    if current_user is None:
        actor: dict[str, Any] = {
            "user_id": None,
            "username": "anonymous",
            "is_superuser": False,
            "tenant_id": default_tenant.tenant_id,
            "tenant_key": default_tenant.tenant_key,
            "tenant_name": default_tenant.tenant_name,
            "roles": [],
        }
        actor["roles"] = derive_roles(actor)
        return actor

    tenant_id = current_user.get("tenant_id")
    if require_explicit_tenant and not tenant_id:
        raise ValueError("tenant_id is required when require_explicit_tenant is True")

    actor = {
        "user_id": current_user.get("user_id"),
        "username": current_user.get("username") or "unknown",
        "is_superuser": bool(current_user.get("is_superuser", False)),
        "tenant_id": tenant_id or default_tenant.tenant_id,
        "tenant_key": current_user.get("tenant_key", default_tenant.tenant_key),
        "tenant_name": current_user.get("tenant_name", default_tenant.tenant_name),
        "roles": current_user.get("roles", []),
        "authorization": current_user.get("authorization"),
    }
    actor["roles"] = derive_roles(actor)
    return actor


async def require_superuser(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """要求当前用户具备管理员权限。"""
    if not current_user.get("is_superuser", False):
        raise AuthorizationError(action="admin_access", resource="protected_resource")
    return current_user


async def _persist_audit_log(entry: dict[str, Any]) -> None:
    try:
        factory = get_async_session_factory()
        async with factory() as session:
            from src.repositories.audit_repository import AuditLogRepository

            repo = AuditLogRepository(session, tenant_id=entry["actor"].get("tenant_id"))
            await repo.create_log(
                action=entry["action"],
                actor=entry["actor"],
                target_type=entry.get("target_type"),
                target_id=entry.get("target_id"),
                result=entry.get("result", "success"),
                detail=entry.get("detail") or {},
            )
            await session.commit()
    except Exception:
        return


def add_audit_log(
    action: str,
    actor: dict[str, Any] | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    result: str = "success",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """追加一条审计日志。"""
    default_tenant = get_default_tenant_context()
    normalized_actor = {
        "user_id": (actor or {}).get("user_id"),
        "username": (actor or {}).get("username", "system"),
        "is_superuser": bool((actor or {}).get("is_superuser", False)),
        "tenant_id": (actor or {}).get("tenant_id", default_tenant.tenant_id),
        "tenant_key": (actor or {}).get("tenant_key", default_tenant.tenant_key),
        "tenant_name": (actor or {}).get("tenant_name", default_tenant.tenant_name),
    }
    detail_payload = dict(detail or {})
    detail_payload.setdefault("request_id", get_request_id())
    detail_payload.setdefault("trace_id", get_trace_id())
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "actor": normalized_actor,
        "target_type": target_type,
        "target_id": target_id,
        "result": result,
        "detail": detail_payload,
    }
    _AUDIT_LOGS.append(entry)
    if len(_AUDIT_LOGS) > _MAX_AUDIT_LOGS:
        del _AUDIT_LOGS[:-_MAX_AUDIT_LOGS]
    with contextlib.suppress(RuntimeError):
        asyncio.get_running_loop().create_task(_persist_audit_log(entry))
    return entry


def list_audit_logs(
    username: str | None = None,
    target_id: str | None = None,
    action: str | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """按条件查询内存审计日志。"""
    logs = list(reversed(_AUDIT_LOGS))
    if username:
        logs = [log for log in logs if log["actor"].get("username") == username]
    if target_id:
        logs = [log for log in logs if log.get("target_id") == target_id]
    if action:
        logs = [log for log in logs if log.get("action") == action]
    if request_id:
        logs = [log for log in logs if (log.get("detail") or {}).get("request_id") == request_id]
    if trace_id:
        logs = [log for log in logs if (log.get("detail") or {}).get("trace_id") == trace_id]
    return logs[:limit]


async def list_audit_logs_persistent(
    tenant_id: str,
    username: str | None = None,
    target_id: str | None = None,
    action: str | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """优先从数据库查询审计日志；失败时由调用方决定是否回退内存。"""
    factory = get_async_session_factory()
    async with factory() as session:
        from src.repositories.audit_repository import AuditLogRepository

        repo = AuditLogRepository(session, tenant_id=tenant_id)
        logs = await repo.list_logs(
            username=username,
            target_id=target_id,
            action=action,
            request_id=request_id,
            trace_id=trace_id,
            limit=limit,
        )
        return [
            {
                "timestamp": log.occurred_at.isoformat() if log.occurred_at else None,
                "action": log.action,
                "actor": {
                    "user_id": log.user_id,
                    "username": log.username,
                    "is_superuser": log.is_superuser,
                    "tenant_id": str(log.tenant_id),
                },
                "target_type": log.target_type,
                "target_id": log.target_id,
                "result": log.result,
                "detail": log.detail or {},
                "request_id": (log.detail or {}).get("request_id"),
                "trace_id": (log.detail or {}).get("trace_id"),
            }
            for log in logs
        ]


def latest_audit_log() -> dict[str, Any] | None:
    """返回最近一条审计日志；无数据时返回 None。"""
    return _AUDIT_LOGS[-1] if _AUDIT_LOGS else None


def clear_audit_logs() -> None:
    """测试/调试辅助：清空审计日志。"""
    _AUDIT_LOGS.clear()
