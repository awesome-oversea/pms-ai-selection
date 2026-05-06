from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest
from src.services.local_knowledge_service import LocalKnowledgeRepository, LocalKnowledgeService


def test_build_qdrant_point_id_returns_stable_uuid_for_document_chunk() -> None:
    document_id = "09c283cf-df06-4fb8-9c16-1dec59b903a5"

    point_id_first = LocalKnowledgeService._build_qdrant_point_id(document_id, 0)
    point_id_second = LocalKnowledgeService._build_qdrant_point_id(document_id, 0)
    other_chunk_point_id = LocalKnowledgeService._build_qdrant_point_id(document_id, 1)

    assert point_id_first == point_id_second
    assert point_id_first != other_chunk_point_id
    assert str(UUID(point_id_first)) == point_id_first
    assert str(UUID(other_chunk_point_id)) == other_chunk_point_id


def test_build_qdrant_point_id_falls_back_for_non_uuid_document_id() -> None:
    point_id = LocalKnowledgeService._build_qdrant_point_id("selection-task-erp-real-001", 3)

    assert str(UUID(point_id)) == point_id


def test_upload_document_reuses_existing_indexed_doc_without_rebuild(tmp_path) -> None:
    repo = LocalKnowledgeRepository(tmp_path / "local_knowledge.db")
    content = b"wireless earbuds with anc and long battery life"
    content_hash = LocalKnowledgeService._hash_content(content)
    document = repo.create_document(
        title="earbuds.txt",
        doc_type="txt",
        file_size=len(content),
        content_hash=content_hash,
        status="indexed",
        extra_data={"provider_mode": "unit-test", "vector_status": "indexed"},
    )
    repo.update_document_status(
        document["id"],
        status="indexed",
        chunk_count=2,
        provider_mode="unit-test",
        vector_status="indexed",
    )

    service = LocalKnowledgeService(repo=repo)
    service.embedding_provider = SimpleNamespace(provider_mode="unit-test")

    result = asyncio.run(service.upload_document("earbuds.txt", content))

    assert result["doc_id"] == document["id"]
    assert result["qdrant_indexed"] is True
    assert result["collection_name"] == LocalKnowledgeService.QDRANT_COLLECTION_NAME


@pytest.mark.asyncio
async def test_upload_document_rebuilds_failed_existing_doc_when_qdrant_available(monkeypatch, tmp_path) -> None:
    repo = LocalKnowledgeRepository(tmp_path / "local_knowledge.db")
    content = b"portable blender with usb-c charging and safety lock"
    content_hash = LocalKnowledgeService._hash_content(content)
    existing = repo.create_document(
        title="blender.txt",
        doc_type="txt",
        file_size=len(content),
        content_hash=content_hash,
        status="indexed",
        extra_data={"provider_mode": "unit-test", "vector_status": "failed:stale-index"},
    )
    repo.update_document_status(
        existing["id"],
        status="indexed",
        chunk_count=1,
        provider_mode="unit-test",
        vector_status="failed:stale-index",
    )

    service = LocalKnowledgeService(repo=repo)

    async def _embed_texts(texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    service.embedding_provider = SimpleNamespace(
        provider_mode="unit-test",
        embed_texts=_embed_texts,
    )

    calls: dict[str, object] = {}

    async def _fake_delete_document(doc_id: str):
        calls["deleted_doc_id"] = doc_id
        repo.soft_delete_document(doc_id)
        return {"doc_id": doc_id, "status": "deleted"}

    class _FakeClient:
        upsert = object()

    class _FakeQdrantService:
        def __init__(self, _client) -> None:
            pass

        async def ensure_collection(self, collection_name: str, vector_size: int) -> None:
            calls["ensured"] = (collection_name, vector_size)

        async def upsert_points(self, collection_name: str, points) -> None:
            calls["upserted"] = (collection_name, len(points))

    monkeypatch.setattr("src.services.local_knowledge_service._QDRANT_AVAILABLE", True)
    monkeypatch.setattr(service, "delete_document", _fake_delete_document)
    monkeypatch.setattr("src.services.local_knowledge_service.get_qdrant_client", lambda: _FakeClient())
    monkeypatch.setattr("src.services.local_knowledge_service.QdrantService", _FakeQdrantService)

    result = await service.upload_document("blender.txt", content)
    docs = await service.list_documents(status=None, limit=10, offset=0)

    assert calls["deleted_doc_id"] == existing["id"]
    assert calls["ensured"] == (LocalKnowledgeService.QDRANT_COLLECTION_NAME, 3)
    assert calls["upserted"][0] == LocalKnowledgeService.QDRANT_COLLECTION_NAME
    assert result["doc_id"] != existing["id"]
    assert result["qdrant_indexed"] is True
    assert repo.get_document(existing["id"]) is None
    assert docs["total"] == 1
