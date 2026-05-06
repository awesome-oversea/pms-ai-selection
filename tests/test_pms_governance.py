from __future__ import annotations

import pytest

from src.core.pms_governance import (
    DATA_SOVEREIGNTY_MATRIX,
    ERP_14_DOMAINS,
    PermissionContext,
    SuggestionLifecycle,
    SuggestionStatus,
    build_domain_status_sync_contract,
    build_erp_14_domain_contract,
    get_domain_write_contract,
    validate_domain_write,
    validate_erp_api_path,
    validate_pms_write_boundary,
    validate_pms_write_object,
)


def test_erp_14_domain_contract_contains_required_domains_and_context_fields():
    contract = build_erp_14_domain_contract()

    assert len(ERP_14_DOMAINS) == 14
    assert set(contract["domains"]) == {
        "iam",
        "pdm",
        "som",
        "ads",
        "oms",
        "scm",
        "wms",
        "fba",
        "tms",
        "crm",
        "fms",
        "bi",
        "sys",
        "dashboard",
    }
    assert contract["api_prefixes"] == ["/api/internal/v1", "/api/pms/v1", "/api/open/v1/pms"]
    assert contract["forbidden_api_prefixes"] == ["/api/admin/v1", "/api/v1"]
    assert set(contract["write_object_whitelist"]) == {"recommendation", "draft", "pending_action", "risk_alert", "insight_card"}
    assert set(contract["domain_write_contracts"]) == set(contract["domains"])
    assert contract["domain_write_contracts"]["som"]["pms_role"] == "listing_draft"
    assert contract["domain_write_contracts"]["oms"]["pms_role"] == "order_risk_insight"
    assert set(contract["required_write_context_fields"]) == {
        "tenant_id",
        "actor_type",
        "actor_id",
        "scope",
        "purpose",
        "trace_id",
        "idempotency_key",
    }
    assert set(contract["error_codes"]) >= {"permission_denied", "tenant_mismatch", "idempotency_conflict", "illegal_state", "not_found", "external_unavailable"}


def test_permission_context_builds_permission_filter_and_rejects_cross_tenant():
    context = PermissionContext.from_actor(
        {
            "tenant_id": "tenant-a",
            "user_id": "user-001",
            "store_id": "store-us",
            "marketplace": "US",
            "trace_id": "trace-001",
        },
        purpose="selection_create",
        idempotency_key="idem-001",
    )

    filters = context.to_filter()
    assert filters["tenant_id"] == "tenant-a"
    assert filters["store_id"] == "store-us"
    assert filters["marketplace"] == "US"
    assert filters["purpose"] == "selection_create"
    assert filters["idempotency_key"] == "idem-001"
    context.assert_same_tenant("tenant-a")
    with pytest.raises(PermissionError):
        context.assert_same_tenant("tenant-b")


@pytest.mark.parametrize("entity_type", ["product_master", "sku_spu", "listing", "order", "inventory", "purchase", "cost_profit", "kpi"])
def test_data_sovereignty_blocks_pms_terminal_writes_to_erp_owned_data(entity_type: str):
    assert DATA_SOVEREIGNTY_MATRIX[entity_type]["owner_system"] == "erp"
    with pytest.raises(PermissionError):
        validate_pms_write_boundary(entity_type, "create_terminal")
    with pytest.raises(PermissionError):
        validate_pms_write_boundary(entity_type, "approve_and_execute")
    assert validate_pms_write_boundary(entity_type, "suggest") is True


@pytest.mark.parametrize("entity_type", ["selection_task", "ai_recommendation", "evidence_chain", "external_signal", "model_feature"])
def test_data_sovereignty_allows_pms_owned_terminal_writes(entity_type: str):
    assert DATA_SOVEREIGNTY_MATRIX[entity_type]["owner_system"] == "pms"
    assert validate_pms_write_boundary(entity_type, "create_terminal") is True


def test_suggestion_lifecycle_allows_valid_v11_flow_and_records_audit_controllers():
    context = PermissionContext.from_actor(
        {"tenant_id": "tenant-a", "user_id": "operator-001", "trace_id": "trace-001"},
        purpose="suggestion_lifecycle",
    )
    lifecycle = SuggestionLifecycle("sg-001")

    lifecycle.transition(SuggestionStatus.SCORED, context, reason="scored by rules")
    lifecycle.transition(SuggestionStatus.SUBMITTED, context, reason="submit for ERP validation")
    lifecycle.transition(SuggestionStatus.ACCEPTED, context, reason="ERP accepted suggestion pool record")
    lifecycle.transition(SuggestionStatus.PENDING_APPROVAL, context, reason="ERP rules require approval")
    lifecycle.transition(SuggestionStatus.APPROVED, context, reason="approved by ERP approver")
    lifecycle.transition(SuggestionStatus.EXECUTING, context, reason="ERP starts execution")
    lifecycle.transition(SuggestionStatus.EXECUTED, context, reason="ERP callback success")
    lifecycle.transition(SuggestionStatus.MEASURED, context, reason="BI metrics returned")
    audit = lifecycle.transition(SuggestionStatus.REVIEWED, context, reason="PMS model review completed")

    assert lifecycle.status == SuggestionStatus.REVIEWED
    assert len(lifecycle.audit_log) == 9
    assert audit["from_status"] == "measured"
    assert audit["to_status"] == "reviewed"
    assert audit["controller"] == "pms"
    assert lifecycle.audit_log[2]["controller"] == "erp"
    assert lifecycle.audit_log[7]["controller"] == "erp_bi"
    assert audit["actor_id"] == "operator-001"
    assert audit["trace_id"] == "trace-001"


def test_suggestion_lifecycle_rejects_illegal_transition():
    context = PermissionContext.from_actor(
        {"tenant_id": "tenant-a", "user_id": "operator-001", "trace_id": "trace-001"},
        purpose="suggestion_lifecycle",
    )
    lifecycle = SuggestionLifecycle("sg-002")

    with pytest.raises(ValueError):
        lifecycle.transition(SuggestionStatus.EXECUTED, context, reason="skip approval")


def test_v11_api_path_and_write_object_boundaries():
    assert validate_erp_api_path("/api/internal/v1/pms/recommendations") is True
    assert validate_erp_api_path("/api/pms/v1/recommendations") is True
    assert validate_pms_write_object("recommendation") is True
    assert validate_pms_write_object("draft") is True
    assert validate_pms_write_object("pending_action") is True
    assert validate_pms_write_object("risk_alert") is True
    assert validate_pms_write_object("insight_card") is True
    with pytest.raises(PermissionError):
        validate_erp_api_path("/api/v1/orders")
    with pytest.raises(PermissionError):
        validate_erp_api_path("/api/admin/v1/config")
    with pytest.raises(PermissionError):
        validate_pms_write_object("purchase_order")


@pytest.mark.parametrize("domain", [domain.value for domain in ERP_14_DOMAINS])
def test_each_erp_domain_has_write_permission_and_status_sync_contract(domain: str):
    contract = get_domain_write_contract(domain)
    status_contract = build_domain_status_sync_contract(domain)

    assert contract["domain"] == domain
    assert contract["allowed_objects"]
    assert set(contract["allowed_objects"]).issubset({"recommendation", "draft", "pending_action", "risk_alert", "insight_card"})
    assert status_contract["domain"] == domain
    assert status_contract["status_owner"].startswith("erp_")
    assert "pending_approval" in status_contract["required_statuses"]
    assert "executed" in status_contract["required_statuses"]
    assert set(status_contract["audit_context_required"]) == {
        "tenant_id",
        "actor_type",
        "actor_id",
        "scope",
        "purpose",
        "trace_id",
        "idempotency_key",
    }
    for allowed_object in contract["allowed_objects"]:
        assert validate_domain_write(domain, allowed_object, action="suggest") is True


@pytest.mark.parametrize(
    ("domain", "forbidden_object"),
    [
        ("iam", "draft"),
        ("oms", "draft"),
        ("wms", "draft"),
        ("crm", "draft"),
        ("fms", "draft"),
        ("bi", "recommendation"),
        ("dashboard", "draft"),
    ],
)
def test_domain_write_contract_rejects_cross_domain_or_terminal_writes(domain: str, forbidden_object: str):
    with pytest.raises(PermissionError):
        validate_domain_write(domain, forbidden_object, action="suggest")
    with pytest.raises(PermissionError):
        validate_domain_write(domain, get_domain_write_contract(domain)["allowed_objects"][0], action="approve_and_execute")
