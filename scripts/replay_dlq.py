from __future__ import annotations

import asyncio
import json

from src.infrastructure.database import close_db, get_async_session_factory, init_db
from src.services.data_sync_service import DataSyncService


async def _main(event_id: str) -> dict:
    await init_db()
    session = get_async_session_factory()()
    try:
        service = DataSyncService(session, tenant_id=None, actor={})
        return await service.replay_dead_letter(event_id)
    finally:
        await session.close()
        await close_db()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("usage: python scripts/replay_dlq.py <event_id>")
    print(json.dumps(asyncio.run(_main(sys.argv[1])), ensure_ascii=False, indent=2))
