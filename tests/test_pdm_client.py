from __future__ import annotations

import json

import pytest

from src.core.pms_governance import AuditContext
from src.infrastructure.pdm_client import PDMClient


class _Resp:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {"recommendation_id": "REC-http-001", "status": "submitted"}
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
        return _Resp({"recommendation_id": json["recommendation_id"], "status": json["status"]})


@pytest.mark.asyncio
async def test_pdm_client_submit_selection_recommendation_local_artifact(tmp_path):
    (tmp_path / "recommendations.json").write_text('{"items": []}', encoding="utf-8")
    client = PDMClient(
        api_endpoint=f"file://{tmp_path.as_posix()}",
        api_key=None,
        inbound_path="/recommendations.json",
        outbound_path="/recommendation-submission.json",
        timeout_seconds=5,
    )

    assert (await client.test_connection())["status"] == "ok"
    result = await client.submit_selection_recommendation({"task_id": "task-001", "recommendation_id": "REC-task-001"})

    assert result["status"] == "submitted"
    assert result["owner_domain"] == "pdm"
    assert result["write_object"] == "recommendation"
    payload = json.loads((tmp_path / "recommendation-submission.json").read_text(encoding="utf-8"))
    assert payload["owner_domain"] == "pdm"
    assert payload["write_object"] == "recommendation"


@pytest.mark.asyncio
async def test_pdm_client_submit_selection_recommendation_http(monkeypatch):
    _Client.calls.clear()
    monkeypatch.setattr("src.infrastructure.erp_client.httpx.AsyncClient", _Client)
    client = PDMClient(api_endpoint="http://fake-pdm.local", api_key="k", inbound_path="/recommendations", outbound_path="/recommendations", timeout_seconds=5)
    audit = AuditContext(
        tenant_id="tenant-001",
        actor_type="service",
        actor_id="pms-selection-service",
        scope="tenant",
        purpose="submit_selection_recommendation",
        trace_id="trace-pdm-001",
        idempotency_key="idem-pdm-001",
    )
    result = await client.submit_selection_recommendation(
        {"task_id": "task-001", "recommendation_id": "REC-task-001"},
        audit_context=audit,
    )
    assert result["recommendation_id"] == "REC-task-001"
    assert result["owner_domain"] == "pdm"
    assert result["write_object"] == "recommendation"
    assert len(_Client.calls) == 1
    call = _Client.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "http://fake-pdm.local/api/internal/v1/pdm/recommendations"
    headers = call["headers"]
    assert headers["X-PMS-Source-System"] == "pms"
    assert headers["X-PMS-Tenant-ID"] == "tenant-001"
    assert headers["X-PMS-Actor-ID"] == "pms-selection-service"
    assert headers["X-Trace-ID"] == "trace-pdm-001"
    assert headers["X-Idempotency-Key"] == "idem-pdm-001"
    payload = call["json"]
    assert payload["audit_context"]["tenant_id"] == "tenant-001"
    assert payload["audit_context"]["purpose"] == "submit_selection_recommendation"
