from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class DataSyncRepository:
    def __init__(self, session: AsyncSession, tenant_id: str | None = None):
        self.session = session
        self.tenant_id = tenant_id

    async def create_event(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        event_type: str,
        aggregate_id: str,
        topic: str,
        event_key: str,
        payload: dict[str, Any],
        source: str = "outbox",
    ) -> Any:
        from src.models.models import DataSyncEvent

        event = DataSyncEvent(
            tenant_id=UUID(str(tenant_id)),
            entity_type=entity_type,
            event_type=event_type,
            aggregate_id=aggregate_id,
            topic=topic,
            event_key=event_key,
            payload=payload,
            source=source,
            status="pending",
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_event(self, event_id: str) -> Any | None:
        from src.models.models import DataSyncEvent

        result = await self.session.execute(select(DataSyncEvent).where(DataSyncEvent.id == UUID(str(event_id))))
        return result.scalar_one_or_none()

    async def get_event_by_key(self, event_key: str) -> Any | None:
        from src.models.models import DataSyncEvent

        result = await self.session.execute(select(DataSyncEvent).where(DataSyncEvent.event_key == event_key))
        return result.scalar_one_or_none()

    async def list_pending(self, limit: int = 20) -> list[Any]:
        from src.models.models import DataSyncEvent

        stmt = select(DataSyncEvent).where(DataSyncEvent.status.in_(["pending", "failed"])).order_by(DataSyncEvent.created_at.asc()).limit(limit)
        if self.tenant_id:
            stmt = stmt.where(DataSyncEvent.tenant_id == UUID(str(self.tenant_id)))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_dead_letter(self, limit: int = 20) -> list[Any]:
        from src.models.models import DataSyncEvent

        stmt = select(DataSyncEvent).where(DataSyncEvent.status == "dead_letter").order_by(DataSyncEvent.created_at.desc()).limit(limit)
        if self.tenant_id:
            stmt = stmt.where(DataSyncEvent.tenant_id == UUID(str(self.tenant_id)))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_sent(self, event: Any) -> Any:
        event.status = "sent"
        event.published_at = datetime.now(UTC)
        event.last_attempt_at = datetime.now(UTC)
        await self.session.flush()
        return event

    async def mark_failed(self, event: Any, error: str, dead_letter: bool = False) -> Any:
        event.retry_count = int(event.retry_count or 0) + 1
        event.last_error = error
        event.last_attempt_at = datetime.now(UTC)
        event.status = "dead_letter" if dead_letter else "failed"
        await self.session.flush()
        return event

    async def reset_for_replay(self, event: Any) -> Any:
        event.status = "pending"
        event.last_error = None
        await self.session.flush()
        return event
