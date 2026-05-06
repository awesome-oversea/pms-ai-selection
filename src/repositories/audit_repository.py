"""
审计日志 Repository
===================

提供 audit_logs 的最小持久化与查询能力。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.base import TenantScopedRepository


class AuditLogRepository(TenantScopedRepository):
    """审计日志数据访问层。"""

    async def build_operations_status(self, limit: int = 20) -> dict[str, Any]:
        logs = await self.list_logs(limit=limit)
        return {
            'tenant_id': str(self.tenant_uuid()),
            'total': len(logs),
            'recent_actions': [
                {
                    'action': item.action,
                    'username': item.username,
                    'result': item.result,
                    'occurred_at': item.occurred_at.isoformat() if item.occurred_at else None,
                }
                for item in logs[:10]
            ],
            'export_policy': 'manual export via audit-operations',
            'archive_policy': 'retain latest records in db and archive externally by schedule',
            'trace_export_ready': True,
            'cross_system_trace_supported': True,
            'trace_query_ready': True,
            'supported_filters': ['username', 'target_id', 'action', 'request_id', 'trace_id'],
        }

    def __init__(self, session: AsyncSession, tenant_id: str | None = None):
        super().__init__(session, tenant_id=tenant_id, require_tenant=True)

    async def create_log(
        self,
        *,
        action: str,
        actor: dict[str, Any] | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        result: str = "success",
        detail: dict[str, Any] | None = None,
    ) -> Any:
        from src.models.models import AuditLog

        actor = actor or {}
        log = AuditLog(
            tenant_id=self.tenant_uuid(actor.get("tenant_id")),
            user_id=str(actor.get("user_id")) if actor.get("user_id") is not None else None,
            username=actor.get("username") or "system",
            is_superuser=bool(actor.get("is_superuser", False)),
            action=action,
            target_type=target_type,
            target_id=target_id,
            result=result,
            detail=detail or {},
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def list_logs(
        self,
        *,
        username: str | None = None,
        target_id: str | None = None,
        action: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        from src.models.models import AuditLog

        query = select(AuditLog).where(AuditLog.tenant_id == self.tenant_uuid())
        if username:
            query = query.where(AuditLog.username == username)
        if target_id:
            query = query.where(AuditLog.target_id == target_id)
        if action:
            query = query.where(AuditLog.action == action)
        if request_id:
            query = query.where(AuditLog.detail.op("->>")("request_id") == request_id)
        if trace_id:
            query = query.where(AuditLog.detail.op("->>")("trace_id") == trace_id)
        query = query.order_by(desc(AuditLog.occurred_at)).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
