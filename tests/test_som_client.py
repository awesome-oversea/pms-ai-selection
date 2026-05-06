from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.pms_governance import AuditContext
from src.infrastructure.som_client import SOMClient, SOMClientError


class _Resp:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {"listing_draft_id": "LST-http-001", "status": "pending_approval"}
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
        return _Resp({"listing_draft_id": json["listing_draft_id"], "status": "draft_created"})


@pytest.mark.asyncio
async def test_som_client_create_listing_draft_local_artifact(tmp_path):
    (tmp_path / "listings.json").write_text('{"items": []}', encoding="utf-8")
    client = SOMClient(
        api_endpoint=f"file://{tmp_path.as_posix()}",
        api_key=None,
        inbound_path="/listings.json",
        outbound_path="/listing-draft.json",
        timeout_seconds=5,
    )

    assert (await client.test_connection())["status"] == "ok"
    result = await client.create_listing_draft({"task_id": "task-001", "listing_draft_id": "LST-task-001"})

    assert result["status"] == "pending_approval"
    assert result["owner_domain"] == "som"
    payload = json.loads((tmp_path / "listing-draft.json").read_text(encoding="utf-8"))
    assert payload["owner_domain"] == "som"
    assert payload["write_object"] == "draft"
    assert payload["status"] == "pending_approval"
    assert "listing_id" not in payload
    assert "published_at" not in payload


@pytest.mark.asyncio
async def test_som_client_create_listing_draft_http(monkeypatch):
    _Client.calls.clear()
    monkeypatch.setattr("src.infrastructure.erp_client.httpx.AsyncClient", _Client)
    client = SOMClient(api_endpoint="http://fake-som.local", api_key="k", inbound_path="/listings", outbound_path="/listing-drafts", timeout_seconds=5)
    audit = AuditContext(
        tenant_id="tenant-001",
        actor_type="service",
        actor_id="pms-selection-service",
        scope="tenant",
        purpose="submit_listing_draft",
        trace_id="trace-som-001",
        idempotency_key="idem-som-001",
    )
    result = await client.create_listing_draft(
        {"task_id": "task-001", "listing_draft_id": "LST-task-001"},
        audit_context=audit,
    )
    assert result["listing_draft_id"] == "LST-task-001"
    assert result["status"] == "pending_approval"
    assert result["owner_domain"] == "som"
    assert result["write_object"] == "draft"
    assert len(_Client.calls) == 1
    call = _Client.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "http://fake-som.local/api/internal/v1/som/listing-drafts"
    headers = call["headers"]
    assert headers["X-PMS-Source-System"] == "pms"
    assert headers["X-PMS-Tenant-ID"] == "tenant-001"
    assert headers["X-PMS-Actor-ID"] == "pms-selection-service"
    assert headers["X-Trace-ID"] == "trace-som-001"
    assert headers["X-Idempotency-Key"] == "idem-som-001"
    payload = call["json"]
    assert payload["audit_context"]["tenant_id"] == "tenant-001"
    assert payload["audit_context"]["purpose"] == "submit_listing_draft"


@pytest.mark.asyncio
async def test_som_client_rejects_formal_listing_status():
    client = SOMClient(api_endpoint="http://fake-som.local", api_key="k", inbound_path="/listings", outbound_path="/listing-drafts", timeout_seconds=5)
    with pytest.raises(SOMClientError) as exc:
        await client.create_listing_draft({"task_id": "task-001", "listing_draft_id": "LST-task-001", "status": "published"})
    assert exc.value.error_code == "write_boundary_violation"
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_som_client_rejects_formal_listing_fields():
    client = SOMClient(api_endpoint="http://fake-som.local", api_key="k", inbound_path="/listings", outbound_path="/listing-drafts", timeout_seconds=5)
    with pytest.raises(SOMClientError) as exc:
        await client.create_listing_draft({"task_id": "task-001", "listing_draft_id": "LST-task-001", "listing_id": "LIVE-001"})
    assert exc.value.error_code == "write_boundary_violation"
