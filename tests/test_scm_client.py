from __future__ import annotations

import pytest

from src.core.pms_governance import AuditContext
from src.infrastructure.scm_client import SCMClient


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
            return _Resp({"items": [{"id": "scm-001", "name": "supplier product"}]})
        return _Resp({"purchase_order_id": "PO-task-001", "status": "pending_review"})

    async def get(self, url, headers=None):
        return _Resp({"items": [{"id": "scm-001", "name": "supplier product"}]})

    async def post(self, url, headers=None, json=None):
        return _Resp({"ok": True})


@pytest.mark.asyncio
async def test_scm_client_fetch_and_push(monkeypatch):
    _Client.calls.clear()
    monkeypatch.setattr("src.infrastructure.erp_client.httpx.AsyncClient", _Client)
    client = SCMClient(api_endpoint="http://fake-scm.local", api_key="k", inbound_path="/supplier-products", outbound_path="/product-plans/bulk-upsert", timeout_seconds=5)
    audit = AuditContext(
        tenant_id="tenant-001",
        actor_type="service",
        actor_id="pms-selection-service",
        scope="tenant",
        purpose="submit_purchase_recommendation",
        trace_id="trace-scm-001",
        idempotency_key="idem-scm-001",
    )
    result = await client.fetch_supplier_products(audit_context=audit)
    assert result[0]["id"] == "scm-001"
    receipt = await client.create_purchase_suggestion(
        {"task_id": "task-001", "supplier_code": "SUP-001"},
        audit_context=audit,
    )
    assert receipt["status"] == "pending_review"
    assert receipt["owner_domain"] == "scm"
    assert len(_Client.calls) == 2
    fetch_call = _Client.calls[0]
    assert fetch_call["method"] == "GET"
    assert fetch_call["url"] == "http://fake-scm.local/api/internal/v1/scm/supplier-products"
    write_call = _Client.calls[1]
    assert write_call["method"] == "POST"
    assert write_call["url"] == "http://fake-scm.local/api/internal/v1/scm/product-plans/bulk-upsert"
    headers = write_call["headers"]
    assert headers["X-PMS-Tenant-ID"] == "tenant-001"
    assert headers["X-PMS-Actor-ID"] == "pms-selection-service"
    assert headers["X-Trace-ID"] == "trace-scm-001"
    payload = write_call["json"]
    assert payload["owner_domain"] == "scm"
    assert payload["write_object"] == "recommendation"
    assert payload["audit_context"]["purpose"] == "submit_purchase_recommendation"
