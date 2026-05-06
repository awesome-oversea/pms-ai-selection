from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.pms_governance import AuditContext, SuggestionLifecycle, SuggestionStatus, validate_erp_api_path
from src.infrastructure.erp_client import BaseERPClient, ERPClientError


class _Resp:
    def __init__(self, payload=None, status_code=200, content=b"{}"):
        self._payload = payload if payload is not None else {"ok": True}
        self.status_code = status_code
        self.content = content

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("boom", request=SimpleNamespace(), response=SimpleNamespace(status_code=self.status_code))


class _RetryClient:
    calls = 0

    def __init__(self, timeout=None):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, headers=None, json=None):
        _RetryClient.calls += 1
        if _RetryClient.calls < 3:
            return _Resp(status_code=500)
        return _Resp({"accepted": True, "url": url, "headers": headers})


@pytest.fixture
def audit_context() -> AuditContext:
    return AuditContext(
        tenant_id="tenant-001",
        actor_type="service",
        actor_id="pms-selection-service",
        scope="tenant",
        purpose="submit_selection_recommendation",
        trace_id="trace-001",
        idempotency_key="idem-001",
        org_id="org-001",
        department_id="dept-001",
        store_id="store-001",
        marketplace="US",
        channel="amazon",
        warehouse_id="wh-001",
        supplier_id="sup-001",
        category_id="cat-001",
        data_level="internal",
    )


def test_erp_api_path_must_use_internal_v1_prefix():
    assert validate_erp_api_path("/api/internal/v1/pdm/recommendations") is True
    with pytest.raises(PermissionError):
        validate_erp_api_path("/api/v1/pdm/recommendations")


def test_base_erp_client_builds_internal_path_and_audit_headers(audit_context):
    client = BaseERPClient(base_url="https://erp.example.com", domain="pdm", api_key="key", secret_key="secret")
    path = client.build_path("recommendations")
    headers = client.build_headers(method="POST", path=path, audit_context=audit_context, body={"name": "demo"})

    assert path == "/api/internal/v1/pdm/recommendations"
    assert headers["X-API-Key"] == "key"
    assert headers["X-PMS-Source-System"] == "pms"
    assert headers["X-PMS-Tenant-ID"] == "tenant-001"
    assert headers["X-PMS-Actor-Type"] == "service"
    assert headers["X-PMS-Actor-ID"] == "pms-selection-service"
    assert headers["X-PMS-Scope"] == "tenant"
    assert headers["X-PMS-Purpose"] == "submit_selection_recommendation"
    assert headers["X-Trace-ID"] == "trace-001"
    assert headers["X-Idempotency-Key"] == "idem-001"
    assert headers["X-PMS-Signature"]
    assert headers["X-PMS-Marketplace"] == "US"
    assert headers["X-PMS-Channel"] == "amazon"
    assert headers["X-PMS-Data-Level"] == "internal"


@pytest.mark.asyncio
async def test_base_erp_client_retries_and_records_audit(monkeypatch, audit_context):
    _RetryClient.calls = 0
    monkeypatch.setattr("src.infrastructure.erp_client.httpx.AsyncClient", _RetryClient)

    client = BaseERPClient(base_url="https://erp.example.com", domain="pdm", api_key="key", secret_key="secret")
    result = await client.request("POST", "recommendations", audit_context=audit_context, json_body={"title": "demo"})

    assert result["accepted"] is True
    assert _RetryClient.calls == 3
    assert [item["result"] for item in client.audit_log] == ["retry", "retry", "success"]
    assert all(item["trace_id"] == "trace-001" for item in client.audit_log)
    assert client.audit_log[-1]["path"] == "/api/internal/v1/pdm/recommendations"


def test_suggestion_lifecycle_v11_transitions(audit_context):
    lifecycle = SuggestionLifecycle(suggestion_id="sug-001")
    path = [
        SuggestionStatus.SCORED,
        SuggestionStatus.SUBMITTED,
        SuggestionStatus.ACCEPTED,
        SuggestionStatus.PENDING_APPROVAL,
        SuggestionStatus.APPROVED,
        SuggestionStatus.EXECUTING,
        SuggestionStatus.EXECUTED,
        SuggestionStatus.MEASURED,
        SuggestionStatus.REVIEWED,
    ]
    for status in path:
        lifecycle.transition(status, audit_context)

    assert lifecycle.status == SuggestionStatus.REVIEWED
    assert len(lifecycle.audit_log) == len(path)
    assert lifecycle.audit_log[0]["from_status"] == "created"
    assert lifecycle.audit_log[-1]["controller"] == "pms"

    with pytest.raises(ValueError):
        lifecycle.transition(SuggestionStatus.SUBMITTED, audit_context)


@pytest.mark.asyncio
async def test_base_erp_client_non_retryable_4xx(monkeypatch, audit_context):
    class _Fail4xxClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None):
            return _Resp(status_code=403)

    monkeypatch.setattr("src.infrastructure.erp_client.httpx.AsyncClient", _Fail4xxClient)
    client = BaseERPClient(base_url="https://erp.example.com", domain="pdm", api_key="key", secret_key="secret")

    with pytest.raises(ERPClientError) as exc_info:
        await client.request("POST", "recommendations", audit_context=audit_context, json_body={"title": "demo"})

    assert exc_info.value.retryable is False
    assert exc_info.value.error_code == "upstream_4xx"
    assert len(client.audit_log) == 1
    assert client.audit_log[0]["result"] == "failed"
