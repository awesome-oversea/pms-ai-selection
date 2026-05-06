from __future__ import annotations

import pytest
from src.infrastructure.fms_client import FMSClient


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
        return _Resp({"items": [{"id": "fms-001", "product_id": "prod-001", "gross_profit": 99.0, "cost": 20.0}]})

    async def post(self, url, headers=None, json=None):
        return _Resp({"ok": True})


@pytest.mark.asyncio
async def test_fms_client_fetch_and_push(monkeypatch):
    monkeypatch.setattr("src.infrastructure.fms_client.httpx.AsyncClient", _Client)
    client = FMSClient(api_endpoint="http://fake-fms.local", api_key="k", inbound_path="/finance-metrics", outbound_path="/profit-plans/bulk-upsert", timeout_seconds=5)
    result = await client.fetch_finance_metrics()
    assert result[0]["id"] == "fms-001"
    facts = await client.fetch_profit_facts()
    assert facts[0]["product_id"] == "prod-001"
    ad_spending = await client.fetch_ad_spending()
    assert ad_spending[0]["product_id"] == "prod-001"
    await client.push_profit_plan({"items": []})
