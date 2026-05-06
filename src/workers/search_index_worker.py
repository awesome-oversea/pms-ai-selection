from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.infrastructure.database import get_async_session_factory
from src.services.knowledge_service import KnowledgeService


@dataclass
class SearchIndexWorkerResult:
    tenant_id: str
    index_name: str
    document_count: int
    backend: str
    client_configured: bool


async def run_search_reindex(tenant_id: str) -> SearchIndexWorkerResult:
    session = get_async_session_factory()()
    try:
        service = KnowledgeService(session, tenant_id=tenant_id, actor={"tenant_id": tenant_id})
        result: dict[str, Any] = await service.reindex_search_backend()
        return SearchIndexWorkerResult(
            tenant_id=result["tenant_id"],
            index_name=result["index_name"],
            document_count=result["document_count"],
            backend=result["backend"],
            client_configured=result["client_configured"],
        )
    finally:
        await session.close()
