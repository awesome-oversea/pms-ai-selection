from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infrastructure.database import close_db, get_async_session_factory, init_db
from src.services.data_lake_service import DataLakeService


async def _main() -> dict:
    await init_db()
    session = get_async_session_factory()()
    try:
        service = DataLakeService(session)
        return await service.export_data_sync_events_snapshot()
    finally:
        await session.close()
        await close_db()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(_main()), ensure_ascii=False, indent=2))
