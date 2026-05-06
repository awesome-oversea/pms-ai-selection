from __future__ import annotations

import pytest
from src.infrastructure.crm_client import CRMClient


class _Resp:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {"items": []}
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _Client:
    def __init__(self, timeout=10):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None):
        return _Resp({"items": [{"id": "crm-001", "product_id": "prod-001", "feedback": "很好"}]})

    async def post(self, url, headers=None, json=None):
        return _Resp({"ok": True})


@pytest.mark.asyncio
async def test_crm_client_fetch_and_push(monkeypatch):
    monkeypatch.setattr("src.infrastructure.crm_client.httpx.AsyncClient", _Client)
    client = CRMClient(api_endpoint="http://fake-crm.local", api_key="k", inbound_path="/customer-feedbacks", outbound_path="/followups/bulk-upsert", timeout_seconds=5)
    result = await client.fetch_customer_feedbacks()
    assert result[0]["id"] == "crm-001"
    complaints = await client.fetch_complaints()
    assert complaints[0]["id"] == "crm-001"
    await client.push_followups({"items": []})
