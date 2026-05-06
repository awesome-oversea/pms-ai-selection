from __future__ import annotations

import pytest

from src.core.pms_governance import AuditContext, PermissionContext, validate_erp_api_path
from src.infrastructure.erp_client import BaseERPClient


def _build_audit_context(*, actor_type: str = "service") -> AuditContext:
    actor_id = "pms-selection-service" if actor_type == "service" else "user-001"
    return AuditContext(
        tenant_id="tenant-a",
        actor_type=actor_type,
        actor_id=actor_id,
        scope="tenant",
        purpose="submit_selection_recommendation",
        trace_id="trace-001",
        idempotency_key="idem-001",
        org_id="org-001",
        department_id="dept-001",
        store_id="store-us",
        marketplace="US",
        channel="amazon",
        warehouse_id="wh-001",
        supplier_id="sup-001",
        category_id="cat-001",
        data_level="internal",
    )


def test_permission_context_from_actor_builds_complete_user_filter() -> None:
    context = PermissionContext.from_actor(
        {
            "tenant_id": "tenant-a",
            "user_id": "user-001",
            "store_id": "store-us",
            "marketplace": "US",
            "channel": "amazon",
            "trace_id": "trace-001",
        },
        purpose="selection_submit",
        idempotency_key="idem-001",
    )

    filters = context.to_filter()

    assert context.actor_type == "user"
    assert context.actor_id == "user-001"
    assert filters["tenant_id"] == "tenant-a"
    assert filters["store_id"] == "store-us"
    assert filters["marketplace"] == "US"
    assert filters["channel"] == "amazon"
    assert filters["purpose"] == "selection_submit"
    assert filters["idempotency_key"] == "idem-001"


def test_permission_context_supports_service_actor_and_rejects_cross_tenant() -> None:
    context = PermissionContext.from_actor(
        {"tenant_id": "tenant-a", "trace_id": "trace-service-001"},
        actor_type="service",
        actor_id="pms-selection-service",
        scope="store",
        purpose="erp_submit",
        store_id="store-us",
        marketplace="US",
        channel="amazon",
        idempotency_key="idem-service-001",
    )

    assert context.actor_type == "service"
    assert context.actor_id == "pms-selection-service"
    assert context.scope == "store"
    assert context.store_id == "store-us"
    assert context.marketplace == "US"
    context.assert_same_tenant("tenant-a")

    with pytest.raises(PermissionError, match="tenant mismatch"):
        context.assert_same_tenant("tenant-b")


@pytest.mark.parametrize("actor_type", ["user", "service"])
def test_base_erp_client_build_headers_propagates_complete_audit_context(actor_type: str) -> None:
    audit_context = _build_audit_context(actor_type=actor_type)
    client = BaseERPClient(
        base_url="https://erp.example.com",
        domain="scm",
        api_key="demo-key",
        secret_key="demo-secret",
    )

    path = client.build_path("purchase-suggestions")
    headers = client.build_headers(
        method="POST",
        path=path,
        audit_context=audit_context,
        body={"quantity": 240, "supplier_code": "SUP-001"},
    )

    assert validate_erp_api_path(path) is True
    assert path == "/api/internal/v1/scm/purchase-suggestions"
    assert headers["X-API-Key"] == "demo-key"
    assert headers["X-PMS-Source-System"] == "pms"
    assert headers["X-PMS-Tenant-ID"] == "tenant-a"
    assert headers["X-PMS-Actor-Type"] == actor_type
    assert headers["X-PMS-Actor-ID"] == audit_context.actor_id
    assert headers["X-PMS-Scope"] == "tenant"
    assert headers["X-PMS-Purpose"] == "submit_selection_recommendation"
    assert headers["X-Trace-ID"] == "trace-001"
    assert headers["X-Idempotency-Key"] == "idem-001"
    assert headers["X-PMS-Store-ID"] == "store-us"
    assert headers["X-PMS-Marketplace"] == "US"
    assert headers["X-PMS-Channel"] == "amazon"
    assert headers["X-PMS-Data-Level"] == "internal"
    assert headers["X-PMS-Signature"]


def test_base_erp_client_build_headers_requires_required_audit_fields() -> None:
    client = BaseERPClient(
        base_url="https://erp.example.com",
        domain="pdm",
        api_key="demo-key",
        secret_key="demo-secret",
    )
    path = client.build_path("recommendations")
    incomplete_context = AuditContext(
        tenant_id="tenant-a",
        actor_type="service",
        actor_id="pms-selection-service",
        scope="tenant",
        purpose="",
        trace_id="trace-001",
    )

    with pytest.raises(ValueError, match="missing audit context fields: purpose"):
        client.build_headers(method="POST", path=path, audit_context=incomplete_context, body={"title": "demo"})
