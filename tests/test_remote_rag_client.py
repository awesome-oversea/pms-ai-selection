from __future__ import annotations

import pytest
from src.infrastructure.remote_rag_client import RemoteRAGClient


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _Client:
    last_request = None

    def __init__(self, timeout=10):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        _Client.last_request = {"url": url, "headers": headers or {}, "json": json or {}}
        return _Resp({"data": {"query": json["query"], "results": [], "total_found": 0, "processing_time_ms": 1.0}})


@pytest.mark.asyncio
async def test_remote_rag_client_query(monkeypatch):
    monkeypatch.setattr("src.infrastructure.remote_rag_client.httpx.AsyncClient", _Client)
    client = RemoteRAGClient()
    result = await client.query(query="蓝牙耳机", top_k=3, threshold=0.1, token="Bearer token")
    assert result["query"] == "蓝牙耳机"
    assert _Client.last_request["headers"]["Authorization"] == "Bearer token"
    status = client.build_status()
    assert status["deployment"] == "k8s/rag-service.yml"
    assert status["status_endpoint"].endswith("/status")
