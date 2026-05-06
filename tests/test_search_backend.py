from __future__ import annotations

import pytest
from src.infrastructure.search_backend import SearchBackend


def test_search_backend_build_index_name_and_status():
    backend = SearchBackend()
    index_name = backend.build_index_name("86d1f796-7c55-57a1-ac77-2e952a2111ca")
    assert index_name.startswith(backend.settings.index_prefix)
    status = backend.build_status()
    assert "backend" in status
    assert "effective_mode" in status
    assert status["reindex_ready"] is True
    assert "content" in status["index_mapping_fields"]
    assert status["memory_doc_count"] == 0
    assert status["last_reindex"] is None
    assert "client_available" in status
    assert "fallback_reason" in status


@pytest.mark.asyncio
async def test_search_backend_reindex_updates_last_status():
    backend = SearchBackend()
    result = await backend.reindex_documents(
        index_name="pms_knowledge_demo",
        documents=[{"id": "1", "content": "蓝牙耳机", "metadata": {"tenant_id": "t1", "document_id": "d1", "chunk_index": 0, "source": "demo"}}],
    )
    assert result["document_count"] == 1
    status = backend.build_status()
    assert status["last_reindex"]["index_name"] == "pms_knowledge_demo"
    assert status["memory_doc_count"] == 1
