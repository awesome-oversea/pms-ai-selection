from __future__ import annotations

from typing import Any

from src.services.data_sync_service import DataSyncService


class DataSyncDispatcher:
    def __init__(self, service: DataSyncService):
        self.service = service

    async def run_once(self, limit: int = 20, max_retries: int = 2) -> dict[str, Any]:
        return await self.service.dispatch_pending_events(limit=limit, max_retries=max_retries)
