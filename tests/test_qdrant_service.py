from __future__ import annotations

from types import SimpleNamespace

import pytest
from src.infrastructure import qdrant as qdrant_module


@pytest.mark.asyncio
async def test_ensure_collection_tolerates_already_exists_conflict(monkeypatch) -> None:
    if not qdrant_module._QDRANT_AVAILABLE or qdrant_module.models is None:
        pytest.skip("qdrant-client not installed")

    class _FakeClient:
        async def get_collections(self):
            return SimpleNamespace(collections=[])

        async def create_collection(self, **_kwargs):
            raise RuntimeError("409 already exists")

    service = qdrant_module.QdrantService(_FakeClient())

    created = await service.ensure_collection("product_knowledge_local", vector_size=3)

    assert created is False
