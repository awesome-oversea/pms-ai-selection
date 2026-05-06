from __future__ import annotations

import pytest
from src.infrastructure.triton_client import TritonClient, TritonClientError


class _Resp:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {"status": "ok"}
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _AsyncClient:
    last_request = None

    def __init__(self, timeout=10):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url):
        _AsyncClient.last_request = {"method": "GET", "url": url}
        return _Resp({"status": "ready"})

    async def post(self, url, json=None):
        _AsyncClient.last_request = {"method": "POST", "url": url, "json": json or {}}
        return _Resp({"results": [{"index": 1, "score": 0.91}]})


class _SyncClient:
    last_request = None

    def __init__(self, timeout=10):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        _SyncClient.last_request = {"method": "GET", "url": url}
        return _Resp({"status": "ready"})

    def post(self, url, json=None):
        _SyncClient.last_request = {"method": "POST", "url": url, "json": json or {}}
        return _Resp({"results": [{"index": 0, "score": 0.87}]})


@pytest.mark.asyncio
async def test_triton_client_async_health_and_rerank(monkeypatch):
    monkeypatch.setattr("src.infrastructure.triton_client.httpx.AsyncClient", _AsyncClient)
    client = TritonClient(base_url="http://fake-triton.local", timeout_seconds=5)
    health = await client.healthcheck()
    reranked = await client.rerank(query="蓝牙耳机", documents=["充电线", "降噪蓝牙耳机"], top_k=1)
    assert health["status"] == "ok"
    assert reranked[0]["index"] == 1
    assert _AsyncClient.last_request["json"]["top_k"] == 1


def test_triton_client_sync_rerank(monkeypatch):
    monkeypatch.setattr("src.infrastructure.triton_client.httpx.Client", _SyncClient)
    client = TritonClient(base_url="http://fake-triton.local", timeout_seconds=5)
    reranked = client.rerank_sync(query="蓝牙耳机", documents=["降噪蓝牙耳机", "充电线"], top_k=1)
    assert reranked[0]["index"] == 0
    assert _SyncClient.last_request["url"].endswith("/v1/rerank")


def test_triton_client_sync_error(monkeypatch):
    class _BadClient(_SyncClient):
        def post(self, url, json=None):
            raise RuntimeError("boom")

    monkeypatch.setattr("src.infrastructure.triton_client.httpx.Client", _BadClient)
    client = TritonClient(base_url="http://fake-triton.local", timeout_seconds=5)
    with pytest.raises(TritonClientError):
        client.rerank_sync(query="蓝牙耳机", documents=["A"], top_k=1)
