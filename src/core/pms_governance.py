from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.models.enums import ERPSystemType


@dataclass(frozen=True)
class PermissionContext:
    tenant_id: str
    actor_type: str
    actor_id: str
    scope: str
    purpose: str
    trace_id: str
    idempotency_key: str | None = None
    org_id: str | None = None
    department_id: str | None = None
    store_id: str | None = None
    marketplace: str | None = None
    channel: str | None = None
    warehouse_id: str | None = None
    supplier_id: str | None = None
    category_id: str | None = None
    data_level: str = "internal"

    @classmethod
    def from_actor(cls, actor: dict[str, Any] | None, **overrides: Any) -> PermissionContext:
        payload = actor or {}
        tenant_id = overrides.get("tenant_id") or payload.get("tenant_id")
        actor_id = overrides.get("actor_id") or payload.get("user_id") or payload.get("sub") or payload.get("username")
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if not actor_id:
            raise ValueError("actor_id is required")
        data = {
            "tenant_id": str(tenant_id),
            "actor_type": str(overrides.get("actor_type") or payload.get("actor_type") or "user"),
            "actor_id": str(actor_id),
            "scope": str(overrides.get("scope") or payload.get("scope") or "tenant"),
            "purpose": str(overrides.get("purpose") or payload.get("purpose") or "pms_operation"),
            "trace_id": str(overrides.get("trace_id") or payload.get("trace_id") or payload.get("request_id") or "no-trace"),
            "idempotency_key": overrides.get("idempotency_key") or payload.get("idempotency_key"),
            "org_id": overrides.get("org_id") or payload.get("org_id"),
            "department_id": overrides.get("department_id") or payload.get("department_id"),
            "store_id": overrides.get("store_id") or payload.get("store_id"),
            "marketplace": overrides.get("marketplace") or payload.get("marketplace"),
            "channel": overrides.get("channel") or payload.get("channel"),
            "warehouse_id": overrides.get("warehouse_id") or payload.get("warehouse_id"),
            "supplier_id": overrides.get("supplier_id") or payload.get("supplier_id"),
            "category_id": overrides.get("category_id") or payload.get("category_id"),
            "data_level": str(overrides.get("data_level") or payload.get("data_level") or "internal"),
        }
        return cls(**data)  # type: ignore[arg-type]

    def to_filter(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}

    def assert_same_tenant(self, tenant_id: str | None) -> None:
        if tenant_id is not None and str(tenant_id) != self.tenant_id:
            raise PermissionError("tenant mismatch")


AuditContext = PermissionContext


ERP_14_DOMAINS: tuple[ERPSystemType, ...] = (
    ERPSystemType.IAM,
    ERPSystemType.PDM,
    ERPSystemType.SOM,
    ERPSystemType.ADS,
    ERPSystemType.OMS,
    ERPSystemType.SCM,
    ERPSystemType.WMS,
    ERPSystemType.FBA,
    ERPSystemType.TMS,
    ERPSystemType.CRM,
    ERPSystemType.FMS,
    ERPSystemType.BI,
    ERPSystemType.SYS,
    ERPSystemType.DASHBOARD,
)

DATA_SOVEREIGNTY_MATRIX: dict[str, dict[str, Any]] = {
    "product_master": {"owner_system": "erp", "domains": ["pdm"], "pms_permissions": ["read", "suggest", "draft"], "terminal_write_allowed": False},
    "sku_spu": {"owner_system": "erp", "domains": ["pdm"], "pms_permissions": ["read", "suggest", "draft"], "terminal_write_allowed": False},
    "listing": {"owner_system": "erp", "domains": ["som"], "pms_permissions": ["read", "suggest", "draft"], "terminal_write_allowed": False},
    "order": {"owner_system": "erp", "domains": ["oms"], "pms_permissions": ["read", "suggest"], "terminal_write_allowed": False},
    "inventory": {"owner_system": "erp", "domains": ["wms", "fba"], "pms_permissions": ["read", "suggest"], "terminal_write_allowed": False},
    "purchase": {"owner_system": "erp", "domains": ["scm"], "pms_permissions": ["read", "suggest", "draft"], "terminal_write_allowed": False},
    "cost_profit": {"owner_system": "erp", "domains": ["fms"], "pms_permissions": ["read", "suggest"], "terminal_write_allowed": False},
    "kpi": {"owner_system": "erp", "domains": ["bi"], "pms_permissions": ["read"], "terminal_write_allowed": False},
    "selection_task": {"owner_system": "pms", "domains": ["pms"], "pms_permissions": ["read", "write", "manage"], "terminal_write_allowed": True},
    "ai_recommendation": {"owner_system": "pms", "domains": ["pms"], "pms_permissions": ["read", "write", "manage"], "terminal_write_allowed": True},
    "evidence_chain": {"owner_system": "pms", "domains": ["pms"], "pms_permissions": ["read", "write"], "terminal_write_allowed": True},
    "external_signal": {"owner_system": "pms", "domains": ["pms"], "pms_permissions": ["read", "write"], "terminal_write_allowed": True},
    "model_feature": {"owner_system": "pms", "domains": ["pms"], "pms_permissions": ["read", "write"], "terminal_write_allowed": True},
}


PMS_WRITE_OBJECT_WHITELIST: tuple[str, ...] = (
    "recommendation",
    "draft",
    "pending_action",
    "risk_alert",
    "insight_card",
)


DOMAIN_WRITE_CONTRACTS: dict[str, dict[str, Any]] = {
    "iam": {"allowed_objects": ["pending_action", "risk_alert"], "feedback_source": "erp_iam", "pms_role": "scope_request"},
    "pdm": {"allowed_objects": ["recommendation", "draft", "risk_alert"], "feedback_source": "erp_pdm", "pms_role": "product_proposal"},
    "som": {"allowed_objects": ["recommendation", "draft", "risk_alert"], "feedback_source": "erp_som", "pms_role": "listing_draft"},
    "ads": {"allowed_objects": ["recommendation", "pending_action", "insight_card"], "feedback_source": "erp_ads", "pms_role": "ad_optimization_suggestion"},
    "oms": {"allowed_objects": ["recommendation", "risk_alert", "insight_card"], "feedback_source": "erp_oms", "pms_role": "order_risk_insight"},
    "scm": {"allowed_objects": ["recommendation", "draft", "risk_alert"], "feedback_source": "erp_scm", "pms_role": "purchase_suggestion"},
    "wms": {"allowed_objects": ["recommendation", "risk_alert", "insight_card"], "feedback_source": "erp_wms", "pms_role": "inventory_forecast"},
    "fba": {"allowed_objects": ["recommendation", "draft", "risk_alert"], "feedback_source": "erp_fba", "pms_role": "fba_replenishment_suggestion"},
    "tms": {"allowed_objects": ["recommendation", "risk_alert", "insight_card"], "feedback_source": "erp_tms", "pms_role": "logistics_risk_suggestion"},
    "crm": {"allowed_objects": ["recommendation", "risk_alert", "insight_card"], "feedback_source": "erp_crm", "pms_role": "customer_feedback_insight"},
    "fms": {"allowed_objects": ["recommendation", "risk_alert", "insight_card"], "feedback_source": "erp_fms", "pms_role": "profit_risk_insight"},
    "bi": {"allowed_objects": ["insight_card"], "feedback_source": "erp_bi", "pms_role": "review_report"},
    "sys": {"allowed_objects": ["recommendation", "pending_action", "risk_alert"], "feedback_source": "erp_sys", "pms_role": "config_change_request"},
    "dashboard": {"allowed_objects": ["pending_action", "risk_alert", "insight_card"], "feedback_source": "erp_dashboard", "pms_role": "workbench_card"},
}


ERP_TERMINAL_WRITE_ACTIONS: tuple[str, ...] = (
    "create_terminal",
    "update_terminal",
    "delete_terminal",
    "finalize",
    "approve_and_execute",
    "publish",
    "change_order_status",
    "write_inventory_ledger",
    "create_financial_voucher",
)


def build_erp_14_domain_contract() -> dict[str, Any]:
    return {
        "api_prefixes": ["/api/internal/v1", "/api/pms/v1", "/api/open/v1/pms"],
        "forbidden_api_prefixes": ["/api/admin/v1", "/api/v1"],
        "required_write_context_fields": ["tenant_id", "actor_type", "actor_id", "scope", "purpose", "trace_id", "idempotency_key"],
        "required_call_context_fields": ["tenant_id", "actor_type", "actor_id", "scope", "purpose", "trace_id", "source_system", "signature"],
        "domains": [domain.value for domain in ERP_14_DOMAINS],
        "domain_write_contracts": {domain: {**contract} for domain, contract in DOMAIN_WRITE_CONTRACTS.items()},
        "write_object_whitelist": list(PMS_WRITE_OBJECT_WHITELIST),
        "error_codes": ["permission_denied", "tenant_mismatch", "idempotency_conflict", "illegal_state", "not_found", "external_unavailable"],
        "boundary": "PMS writes recommendations, drafts, pending approval actions, risk alerts, and insight cards only; ERP owns terminal business records, approval, execution, rollback, audit, and KPI definitions.",
    }


def validate_pms_write_boundary(entity_type: str, action: str) -> bool:
    item = DATA_SOVEREIGNTY_MATRIX.get(entity_type)
    if item is None:
        raise ValueError(f"unknown entity_type: {entity_type}")
    normalized = str(action or "").lower()
    if normalized in ERP_TERMINAL_WRITE_ACTIONS and not item.get("terminal_write_allowed"):
        raise PermissionError("PMS cannot write ERP terminal business data")
    return True


def validate_pms_write_object(object_type: str) -> bool:
    if str(object_type or "").lower() not in PMS_WRITE_OBJECT_WHITELIST:
        raise PermissionError("PMS can only write recommendation, draft, pending action, risk alert, or insight card objects")
    return True


def get_domain_write_contract(domain: ERPSystemType | str) -> dict[str, Any]:
    domain_key = domain.value if isinstance(domain, ERPSystemType) else str(domain or "").lower()
    contract = DOMAIN_WRITE_CONTRACTS.get(domain_key)
    if contract is None:
        raise ValueError(f"unknown ERP domain: {domain_key}")
    return {"domain": domain_key, **contract}


def validate_domain_write(domain: ERPSystemType | str, object_type: str, action: str = "suggest") -> bool:
    domain_key = domain.value if isinstance(domain, ERPSystemType) else str(domain or "").lower()
    validate_pms_write_object(object_type)
    contract = get_domain_write_contract(domain_key)
    normalized_object = str(object_type or "").lower()
    if normalized_object not in contract["allowed_objects"]:
        raise PermissionError(f"PMS cannot write {normalized_object} objects to ERP {domain_key} domain")
    normalized_action = str(action or "").lower()
    if normalized_action in ERP_TERMINAL_WRITE_ACTIONS:
        raise PermissionError(f"PMS cannot execute terminal action {normalized_action} in ERP {domain_key} domain")
    return True


def build_domain_status_sync_contract(domain: ERPSystemType | str) -> dict[str, Any]:
    contract = get_domain_write_contract(domain)
    return {
        "domain": contract["domain"],
        "pms_write_role": contract["pms_role"],
        "allowed_write_objects": list(contract["allowed_objects"]),
        "status_owner": contract["feedback_source"],
        "required_statuses": ["accepted", "rejected", "pending_approval", "approved", "executing", "executed", "failed", "rolled_back", "measured"],
        "audit_context_required": ["tenant_id", "actor_type", "actor_id", "scope", "purpose", "trace_id", "idempotency_key"],
    }


def validate_erp_api_path(path: str) -> bool:
    normalized = str(path or "")
    contract = build_erp_14_domain_contract()
    if any(normalized.startswith(prefix) for prefix in contract["forbidden_api_prefixes"]):
        raise PermissionError("PMS must not call ERP admin or ordinary frontend business APIs")
    if not any(normalized.startswith(prefix) for prefix in contract["api_prefixes"]):
        raise PermissionError("PMS ERP calls must use internal, PMS-dedicated, or approved open API prefixes")
    return True


class SuggestionStatus(StrEnum):
    CREATED = "created"
    SCORED = "scored"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PENDING_APPROVAL = "pending_approval"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVED = "approved"
    EXECUTING = "executing"
    PARTIALLY_EXECUTED = "partially_executed"
    EXECUTED = "executed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    MEASURED = "measured"
    REVIEWED = "reviewed"


SUGGESTION_STATUS_CONTROLLER: dict[SuggestionStatus, str] = {
    SuggestionStatus.CREATED: "pms",
    SuggestionStatus.SCORED: "pms",
    SuggestionStatus.SUBMITTED: "pms",
    SuggestionStatus.ACCEPTED: "erp",
    SuggestionStatus.REJECTED: "erp",
    SuggestionStatus.PENDING_APPROVAL: "erp",
    SuggestionStatus.APPROVAL_REJECTED: "erp",
    SuggestionStatus.APPROVED: "erp",
    SuggestionStatus.EXECUTING: "erp",
    SuggestionStatus.PARTIALLY_EXECUTED: "erp",
    SuggestionStatus.EXECUTED: "erp",
    SuggestionStatus.FAILED: "erp",
    SuggestionStatus.ROLLED_BACK: "erp",
    SuggestionStatus.MEASURED: "erp_bi",
    SuggestionStatus.REVIEWED: "pms",
}


ALLOWED_SUGGESTION_TRANSITIONS: dict[SuggestionStatus, set[SuggestionStatus]] = {
    SuggestionStatus.CREATED: {SuggestionStatus.SCORED, SuggestionStatus.SUBMITTED, SuggestionStatus.REJECTED},
    SuggestionStatus.SCORED: {SuggestionStatus.SUBMITTED, SuggestionStatus.REJECTED},
    SuggestionStatus.SUBMITTED: {SuggestionStatus.ACCEPTED, SuggestionStatus.REJECTED},
    SuggestionStatus.ACCEPTED: {SuggestionStatus.PENDING_APPROVAL, SuggestionStatus.REJECTED},
    SuggestionStatus.PENDING_APPROVAL: {SuggestionStatus.APPROVED, SuggestionStatus.APPROVAL_REJECTED},
    SuggestionStatus.APPROVAL_REJECTED: set(),
    SuggestionStatus.APPROVED: {SuggestionStatus.EXECUTING, SuggestionStatus.FAILED},
    SuggestionStatus.REJECTED: set(),
    SuggestionStatus.EXECUTING: {SuggestionStatus.PARTIALLY_EXECUTED, SuggestionStatus.EXECUTED, SuggestionStatus.FAILED},
    SuggestionStatus.PARTIALLY_EXECUTED: {SuggestionStatus.EXECUTED, SuggestionStatus.FAILED},
    SuggestionStatus.EXECUTED: {SuggestionStatus.MEASURED, SuggestionStatus.ROLLED_BACK},
    SuggestionStatus.FAILED: {SuggestionStatus.SUBMITTED},
    SuggestionStatus.ROLLED_BACK: {SuggestionStatus.MEASURED},
    SuggestionStatus.MEASURED: {SuggestionStatus.REVIEWED},
    SuggestionStatus.REVIEWED: set(),
}


@dataclass
class SuggestionLifecycle:
    suggestion_id: str
    status: SuggestionStatus = SuggestionStatus.CREATED
    audit_log: list[dict[str, Any]] = field(default_factory=list)

    def transition(self, next_status: SuggestionStatus | str, context: PermissionContext, reason: str | None = None) -> dict[str, Any]:
        target = next_status if isinstance(next_status, SuggestionStatus) else SuggestionStatus(str(next_status))
        allowed = ALLOWED_SUGGESTION_TRANSITIONS[self.status]
        if target not in allowed:
            raise ValueError(f"illegal suggestion status transition: {self.status.value}->{target.value}")
        previous = self.status
        self.status = target
        item = {
            "suggestion_id": self.suggestion_id,
            "from_status": previous.value,
            "to_status": target.value,
            "actor_type": context.actor_type,
            "actor_id": context.actor_id,
            "tenant_id": context.tenant_id,
            "trace_id": context.trace_id,
            "reason": reason,
            "controller": SUGGESTION_STATUS_CONTROLLER[target],
            "changed_at": datetime.now(UTC).isoformat(),
        }
        self.audit_log.append(item)
        return item
