from __future__ import annotations

import pytest
from src.infrastructure.oms_client import OMSClient, OMSClientError


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
        return _Resp(
            {
                "items": [
                    {
                        "id": "oms-001",
                        "name": "demo",
                        "tenant_id": "tenant-a",
                        "org_id": "org-1",
                        "department_id": "dep-1",
                        "store_id": "store-us",
                        "marketplace": "US",
                        "channel": "amazon",
                        "warehouse_id": "wh-1",
                        "supplier_id": "sup-1",
                        "category_id": "cat-1",
                        "data_level": "internal",
                    },
                    {"id": "oms-002", "name": "blocked", "tenant_id": "tenant-b", "store_id": "store-eu", "marketplace": "EU"},
                ]
            }
        )

    async def post(self, url, headers=None, json=None):
        return _Resp({"ok": True})


@pytest.mark.asyncio
async def test_oms_client_fetch_and_push(monkeypatch):
    monkeypatch.setattr("src.infrastructure.oms_client.httpx.AsyncClient", _Client)
    client = OMSClient(api_endpoint="http://fake-oms.local", api_key="k", inbound_path="/products", outbound_path="/products/bulk-upsert", timeout_seconds=5)
    result = await client.fetch_products()
    assert len(result) == 2
    filtered = await client.fetch_orders(
        permission_context={
            "tenant_id": "tenant-a",
            "org_id": "org-1",
            "department_id": "dep-1",
            "store_id": "store-us",
            "marketplace": "US",
            "channel": "amazon",
            "warehouse_id": "wh-1",
            "supplier_id": "sup-1",
            "category_id": "cat-1",
            "data_level": "internal",
        }
    )
    assert [item["id"] for item in filtered] == ["oms-001"]
    await client.push_products({"items": []})


@pytest.mark.asyncio
async def test_oms_client_rejects_listing_draft_write_by_v11_boundary():
    client = OMSClient(api_endpoint="http://fake-oms.local", api_key="k", inbound_path="/orders", outbound_path="/listing-drafts", timeout_seconds=5)
    with pytest.raises(OMSClientError) as exc_info:
        await client.push_listing_draft({"task_id": "task-001"})
    assert exc_info.value.error_code == "boundary_violation"
    assert exc_info.value.retryable is False
