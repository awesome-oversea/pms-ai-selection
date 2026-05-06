from __future__ import annotations

import pytest
from src.infrastructure.remote_llm_client import RemoteLLMClient


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
        return _Resp({"data": {"response": "remote ok", "provider_mode": "remote-service"}})


@pytest.mark.asyncio
async def test_remote_llm_client_route(monkeypatch):
    monkeypatch.setattr("src.infrastructure.remote_llm_client.httpx.AsyncClient", _Client)
    client = RemoteLLMClient()
    result = await client.route(payload={"prompt": "测试"}, token="Bearer token")
    assert result["response"] == "remote ok"
    assert _Client.last_request["headers"]["Authorization"] == "Bearer token"
    status = client.build_status()
    assert status["deployment"] == "k8s/llm-service.yml"
    assert status["status_endpoint"].endswith("/status")
    assert status["route_endpoint"].endswith("/llm/route")
