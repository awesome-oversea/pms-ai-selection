from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.data_masking import mask_sensitive_data
from src.core.security import list_audit_logs
from src.repositories.audit_repository import AuditLogRepository


async def list_audit_logs_persistent(**kwargs: Any) -> list[dict[str, Any]]:
    from src.api.v1.endpoints.audit import query_persistent_audit_logs

    return await query_persistent_audit_logs(**kwargs)


class AuditOperationsService:
    def __init__(self, session: AsyncSession, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id
        self.repo = AuditLogRepository(session, tenant_id=tenant_id)

    async def build_status(self, limit: int = 20) -> dict[str, Any]:
        return await self.repo.build_operations_status(limit=limit)

    @staticmethod
    def _merge_logs(memory_logs: list[dict[str, Any]], persistent_logs: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for log in [*persistent_logs, *memory_logs]:
            detail = log.get("detail") or {}
            actor = log.get("actor") or {}
            key = (
                log.get("timestamp"),
                log.get("action"),
                log.get("target_type"),
                log.get("target_id"),
                log.get("result"),
                actor.get("username"),
                detail.get("request_id"),
                detail.get("trace_id"),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(log)
            if len(merged) >= limit:
                break
        return merged

    async def query_logs(
        self,
        *,
        username: str | None = None,
        target_id: str | None = None,
        action: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        memory_logs = [
            log
            for log in list_audit_logs(
                username=username,
                target_id=target_id,
                action=action,
                request_id=request_id,
                trace_id=trace_id,
                limit=limit,
            )
            if str((log.get("actor") or {}).get("tenant_id") or "") == str(self.tenant_id)
        ]
        try:
            persistent_logs = await list_audit_logs_persistent(
                tenant_id=self.tenant_id,
                username=username,
                target_id=target_id,
                action=action,
                request_id=request_id,
                trace_id=trace_id,
                limit=limit,
            )
            logs = self._merge_logs(memory_logs, persistent_logs, limit)
            source = "persistent+memory" if memory_logs else "persistent"
        except Exception:
            logs = memory_logs
            source = "memory"

        return {
            "tenant_id": self.tenant_id,
            "total": len(logs),
            "source": source,
            "logs": mask_sensitive_data(logs),
            "filters": {
                "username": username,
                "target_id": target_id,
                "action": action,
                "request_id": request_id,
                "trace_id": trace_id,
                "limit": limit,
            },
        }
