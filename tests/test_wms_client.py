from __future__ import annotations

import pytest

from src.core.pms_governance import AuditContext
from src.infrastructure.wms_client import WMSClient


class _Resp:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {"items": []}
        self.status_code = status_code
        self.content = b"{}"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _Client:
    calls: list[dict[str, object]] = []

    def __init__(self, timeout=10):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, headers=None, json=None):
        _Client.calls.append({"method": method, "url": url, "headers": headers or {}, "json": json})
        if method == "GET":
            return _Resp({"items": [{"id": "wms-001", "sku": "SKU-001", "warehouse_id": "WH-01", "available_quantity": 18, "safety_stock": 10}]})
        return _Resp({"reservation_id": "RSV-task-001", "status": "reserved", "location_code": "WH-A-01"})

    async def get(self, url, headers=None):
        return _Resp({"items": [{"id": "wms-001", "sku": "SKU-001", "warehouse_id": "WH-01", "available_quantity": 18, "safety_stock": 10}]})

    async def post(self, url, headers=None, json=None):
        return _Resp({"ok": True})


@pytest.mark.asyncio
async def test_wms_client_fetch_and_push(monkeypatch):
    _Client.calls.clear()
    monkeypatch.setattr("src.infrastructure.erp_client.httpx.AsyncClient", _Client)
    client = WMSClient(api_endpoint="http://fake-wms.local", api_key="k", inbound_path="/inventory-snapshots", outbound_path="/replenishment-plans/bulk-upsert", timeout_seconds=5)
    audit = AuditContext(
        tenant_id="tenant-001",
        actor_type="service",
        actor_id="pms-selection-service",
        scope="tenant",
        purpose="submit_capacity_suggestion",
        trace_id="trace-wms-001",
        idempotency_key="idem-wms-001",
    )
    result = await client.fetch_inventory_snapshots(audit_context=audit)
    assert result[0]["id"] == "wms-001"
    receipt = await client.create_reservation(
        {"task_id": "task-001", "sku": "SKU-001"},
        audit_context=audit,
    )
    assert receipt["status"] == "reserved"
    assert receipt["owner_domain"] == "wms"
    assert len(_Client.calls) == 2
    fetch_call = _Client.calls[0]
    assert fetch_call["method"] == "GET"
    assert fetch_call["url"] == "http://fake-wms.local/api/internal/v1/wms/inventory-snapshots"
    write_call = _Client.calls[1]
    assert write_call["method"] == "POST"
    assert write_call["url"] == "http://fake-wms.local/api/internal/v1/wms/replenishment-plans/bulk-upsert"
    headers = write_call["headers"]
    assert headers["X-PMS-Tenant-ID"] == "tenant-001"
    assert headers["X-PMS-Actor-ID"] == "pms-selection-service"
    assert headers["X-Trace-ID"] == "trace-wms-001"
    payload = write_call["json"]
    assert payload["owner_domain"] == "wms"
    assert payload["write_object"] == "recommendation"
    assert payload["audit_context"]["purpose"] == "submit_capacity_suggestion"
