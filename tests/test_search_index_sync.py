from __future__ import annotations

import os

import pytest
from src.infrastructure.database import get_async_session_factory
from src.services.knowledge_service import KnowledgeService

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")


@pytest.mark.asyncio
async def test_search_backend_reindex_returns_index_name():
    session = get_async_session_factory()()
    try:
        service = KnowledgeService(session, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
        result = await service.reindex_search_backend()
        assert result["tenant_id"] == "86d1f796-7c55-57a1-ac77-2e952a2111ca"
        assert result["index_name"]
        assert "document_count" in result
    finally:
        await session.close()
