from __future__ import annotations

import pytest

from src.core.pms_governance import PermissionContext, SuggestionLifecycle, SuggestionStatus


def _context() -> PermissionContext:
    return PermissionContext.from_actor(
        {
            "tenant_id": "tenant-a",
            "user_id": "operator-001",
            "trace_id": "trace-state-machine-001",
        },
        purpose="suggestion_state_machine_test",
        idempotency_key="idem-state-machine-001",
    )


def test_suggestion_status_catalog_contains_v11_core_states() -> None:
    implemented_states = {status.value for status in SuggestionStatus}

    assert implemented_states >= {
        "created",
        "scored",
        "submitted",
        "accepted",
        "rejected",
        "pending_approval",
        "approved",
        "executing",
        "partially_executed",
        "executed",
        "failed",
        "rolled_back",
        "measured",
        "reviewed",
    }


def test_suggestion_state_machine_allows_main_reviewed_path() -> None:
    lifecycle = SuggestionLifecycle("sug-001")
    context = _context()
    path = [
        SuggestionStatus.SCORED,
        SuggestionStatus.SUBMITTED,
        SuggestionStatus.ACCEPTED,
        SuggestionStatus.PENDING_APPROVAL,
        SuggestionStatus.APPROVED,
        SuggestionStatus.EXECUTING,
        SuggestionStatus.PARTIALLY_EXECUTED,
        SuggestionStatus.EXECUTED,
        SuggestionStatus.MEASURED,
        SuggestionStatus.REVIEWED,
    ]

    for status in path:
        lifecycle.transition(status, context, reason=f"move to {status.value}")

    assert lifecycle.status == SuggestionStatus.REVIEWED
    assert [item["to_status"] for item in lifecycle.audit_log] == [status.value for status in path]
    assert lifecycle.audit_log[0]["from_status"] == "created"
    assert lifecycle.audit_log[2]["controller"] == "erp"
    assert lifecycle.audit_log[8]["controller"] == "erp_bi"
    assert lifecycle.audit_log[-1]["controller"] == "pms"


def test_suggestion_state_machine_allows_rejected_terminal_path() -> None:
    lifecycle = SuggestionLifecycle("sug-002")
    context = _context()

    lifecycle.transition(SuggestionStatus.SCORED, context, reason="scored by rules")
    lifecycle.transition(SuggestionStatus.SUBMITTED, context, reason="submitted to ERP")
    rejection_audit = lifecycle.transition(SuggestionStatus.REJECTED, context, reason="rejected by ERP")

    assert lifecycle.status == SuggestionStatus.REJECTED
    assert rejection_audit["controller"] == "erp"
    assert rejection_audit["reason"] == "rejected by ERP"

    with pytest.raises(ValueError, match="illegal suggestion status transition"):
        lifecycle.transition(SuggestionStatus.APPROVED, context, reason="should stay terminal")


def test_suggestion_state_machine_allows_failed_resubmission() -> None:
    lifecycle = SuggestionLifecycle("sug-003")
    context = _context()

    for status in [
        SuggestionStatus.SCORED,
        SuggestionStatus.SUBMITTED,
        SuggestionStatus.ACCEPTED,
        SuggestionStatus.PENDING_APPROVAL,
        SuggestionStatus.APPROVED,
        SuggestionStatus.EXECUTING,
        SuggestionStatus.FAILED,
    ]:
        lifecycle.transition(status, context, reason=f"move to {status.value}")

    resubmission_audit = lifecycle.transition(SuggestionStatus.SUBMITTED, context, reason="retry after failure")

    assert lifecycle.status == SuggestionStatus.SUBMITTED
    assert resubmission_audit["from_status"] == "failed"
    assert resubmission_audit["to_status"] == "submitted"


def test_suggestion_state_machine_allows_rollback_then_measure() -> None:
    lifecycle = SuggestionLifecycle("sug-004")
    context = _context()

    for status in [
        SuggestionStatus.SCORED,
        SuggestionStatus.SUBMITTED,
        SuggestionStatus.ACCEPTED,
        SuggestionStatus.PENDING_APPROVAL,
        SuggestionStatus.APPROVED,
        SuggestionStatus.EXECUTING,
        SuggestionStatus.EXECUTED,
        SuggestionStatus.ROLLED_BACK,
        SuggestionStatus.MEASURED,
        SuggestionStatus.REVIEWED,
    ]:
        lifecycle.transition(status, context, reason=f"move to {status.value}")

    assert lifecycle.status == SuggestionStatus.REVIEWED
    assert lifecycle.audit_log[7]["to_status"] == "rolled_back"
    assert lifecycle.audit_log[8]["to_status"] == "measured"


def test_suggestion_state_machine_rejects_illegal_transition() -> None:
    lifecycle = SuggestionLifecycle("sug-005")

    with pytest.raises(ValueError, match="illegal suggestion status transition: created->approved"):
        lifecycle.transition(SuggestionStatus.APPROVED, _context(), reason="skip approval chain")
