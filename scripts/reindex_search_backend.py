from __future__ import annotations

import asyncio
import json

from src.infrastructure.database import close_db, get_async_session_factory, init_db
from src.services.knowledge_service import KnowledgeService


async def _main() -> dict:
    await init_db()
    session = get_async_session_factory()()
    try:
        service = KnowledgeService(session)
        return await service.reindex_search_backend()
    finally:
        await session.close()
        await close_db()


if __name__ == "__main__":
    result = asyncio.run(_main())
    print(json.dumps(result, ensure_ascii=False, indent=2))
