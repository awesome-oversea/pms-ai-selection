from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.core.pms_governance import (
    ALLOWED_SUGGESTION_TRANSITIONS,
    SUGGESTION_STATUS_CONTROLLER,
    AuditContext,
    SuggestionLifecycle,
    SuggestionStatus,
    validate_domain_write,
    validate_pms_write_object,
)
from src.infrastructure.kafka import send_message
from src.models.enums import (
    RecommendationCategory,
    RecommendationExecutionState,
    RecommendationPriority,
)
from src.services.recommendation_pool_service import RecommendationPoolService

logger = get_logger(__name__)

SUGGESTION_TO_EXECUTION_STATE: dict[SuggestionStatus, RecommendationExecutionState] = {
    SuggestionStatus.CREATED: RecommendationExecutionState.SUGGESTED,
    SuggestionStatus.SCORED: RecommendationExecutionState.SUGGESTED,
    SuggestionStatus.SUBMITTED: RecommendationExecutionState.ERP_SUBMITTED,
    SuggestionStatus.ACCEPTED: RecommendationExecutionState.ERP_APPROVED,
    SuggestionStatus.REJECTED: RecommendationExecutionState.ERP_REJECTED,
    SuggestionStatus.PENDING_APPROVAL: RecommendationExecutionState.ERP_PENDING_REVIEW,
    SuggestionStatus.APPROVAL_REJECTED: RecommendationExecutionState.ERP_REJECTED,
    SuggestionStatus.APPROVED: RecommendationExecutionState.ERP_APPROVED,
    SuggestionStatus.EXECUTING: RecommendationExecutionState.SCM_REVIEWING,
    SuggestionStatus.PARTIALLY_EXECUTED: RecommendationExecutionState.PARTIALLY_EXECUTED,
    SuggestionStatus.EXECUTED: RecommendationExecutionState.EXECUTED,
    SuggestionStatus.FAILED: RecommendationExecutionState.EXECUTION_FAILED,
    SuggestionStatus.ROLLED_BACK: RecommendationExecutionState.CLOSED,
    SuggestionStatus.MEASURED: RecommendationExecutionState.CLOSED,
    SuggestionStatus.REVIEWED: RecommendationExecutionState.CLOSED,
    SuggestionStatus.EXPIRED: RecommendationExecutionState.CLOSED,
    SuggestionStatus.DISCARDED: RecommendationExecutionState.CLOSED,
}

EXECUTION_TO_SUGGESTION_STATE: dict[RecommendationExecutionState, SuggestionStatus] = {
    RecommendationExecutionState.SUGGESTED: SuggestionStatus.CREATED,
    RecommendationExecutionState.PMS_APPROVED: SuggestionStatus.SCORED,
    RecommendationExecutionState.PMS_REJECTED: SuggestionStatus.REJECTED,
    RecommendationExecutionState.ERP_SUBMITTED: SuggestionStatus.SUBMITTED,
    RecommendationExecutionState.ERP_APPROVED: SuggestionStatus.APPROVED,
    RecommendationExecutionState.ERP_REJECTED: SuggestionStatus.REJECTED,
    RecommendationExecutionState.ERP_DRAFT_CREATED: SuggestionStatus.ACCEPTED,
    RecommendationExecutionState.ERP_PENDING_REVIEW: SuggestionStatus.PENDING_APPROVAL,
    RecommendationExecutionState.SCM_REVIEWING: SuggestionStatus.EXECUTING,
    RecommendationExecutionState.SCM_APPROVED: SuggestionStatus.EXECUTING,
    RecommendationExecutionState.SCM_REJECTED: SuggestionStatus.REJECTED,
    RecommendationExecutionState.SCM_ORDERED: SuggestionStatus.EXECUTING,
    RecommendationExecutionState.WMS_RESERVED: SuggestionStatus.EXECUTING,
    RecommendationExecutionState.WMS_CONFIRMED: SuggestionStatus.EXECUTING,
    RecommendationExecutionState.OMS_DRAFT_CREATED: SuggestionStatus.EXECUTING,
    RecommendationExecutionState.OMS_PUBLISHED: SuggestionStatus.EXECUTING,
    RecommendationExecutionState.OMS_ACTIVE: SuggestionStatus.EXECUTED,
    RecommendationExecutionState.EXECUTED: SuggestionStatus.EXECUTED,
    RecommendationExecutionState.PARTIALLY_EXECUTED: SuggestionStatus.PARTIALLY_EXECUTED,
    RecommendationExecutionState.EXECUTION_FAILED: SuggestionStatus.FAILED,
    RecommendationExecutionState.CLOSED: SuggestionStatus.REVIEWED,
}

DOMAIN_SUGGESTION_TYPE_MAP: dict[str, str] = {
    "ads": "ad_optimization",
    "scm": "purchase_suggestion",
    "wms": "inventory_forecast",
    "fba": "fba_replenishment_suggestion",
    "som": "listing_draft",
    "pdm": "product_proposal",
    "oms": "order_risk_insight",
    "tms": "logistics_risk_suggestion",
    "crm": "customer_feedback_insight",
    "fms": "profit_risk_insight",
    "iam": "scope_request",
    "bi": "review_report",
    "sys": "config_change_request",
    "dashboard": "workbench_card",
}


class SuggestionService:
    """
    建议生命周期管理服务。

    职责:
    - 统一管理建议的15态状态机(SuggestionStatus)与21态执行状态(RecommendationExecutionState)映射
    - 创建建议并自动关联建议池(Recommendation)
    - 推进建议状态，校验合法转换，记录审计日志
    - 提交建议至ERP对应域，遵循建议池模式(PMS建议→ERP审批执行)
    - 接收ERP反馈并同步更新建议状态
    - 发布建议状态变更事件(Kafka)
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.pool_service = RecommendationPoolService(session, tenant_id=self.tenant_id, actor=self.actor)
        self._lifecycles: dict[str, SuggestionLifecycle] = {}

    async def create_suggestion(
        self,
        *,
        category: RecommendationCategory,
        target_domain: str,
        title: str,
        description: str | None = None,
        priority: RecommendationPriority = RecommendationPriority.MEDIUM,
        score: float | None = None,
        confidence: float | None = None,
        evidence_chain: dict[str, Any] | None = None,
        data_sources: list[dict[str, Any]] | None = None,
        risk_flags: list[dict[str, Any]] | None = None,
        payload: dict[str, Any] | None = None,
        source_task_id: UUID | None = None,
        source_product_id: UUID | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        rate_limit = await self.check_tenant_rate_limit()
        if not rate_limit.get("allowed", True):
            raise ValueError(f"租户建议提交限流: 当前已提交{rate_limit.get('current_count', 0)}条/小时, 上限{rate_limit.get('max_per_hour', 100)}条/小时")

        write_object = self._resolve_write_object(category)
        validate_pms_write_object(write_object)
        validate_domain_write(target_domain, write_object, "suggest")

        rec = await self.pool_service.create_recommendation(
            category=category,
            target_domain=target_domain,
            title=title,
            description=description,
            priority=priority,
            score=score,
            confidence=confidence,
            evidence_chain=evidence_chain,
            data_sources=data_sources,
            risk_flags=risk_flags,
            payload=payload,
            source_task_id=source_task_id,
            source_product_id=source_product_id,
        )

        rec_id = rec["id"]
        lifecycle = SuggestionLifecycle(
            suggestion_id=rec_id,
            metadata={
                "target_domain": target_domain,
                "category": category.value,
                "priority": priority.value,
            },
        )
        self._lifecycles[rec_id] = lifecycle

        if audit_context:
            lifecycle.transition(SuggestionStatus.CREATED, audit_context, reason="suggestion_created")

        await self._publish_suggestion_event(
            suggestion_id=rec_id,
            event_type="suggestion.created",
            payload={
                "category": category.value,
                "target_domain": target_domain,
                "priority": priority.value,
                "score": score,
                "confidence": confidence,
                "suggestion_type": DOMAIN_SUGGESTION_TYPE_MAP.get(target_domain, "generic"),
            },
        )

        return {**rec, "suggestion_status": lifecycle.status.value, "audit_log": lifecycle.audit_log}

    async def score_suggestion(
        self,
        suggestion_id: str,
        *,
        score: float,
        confidence: float | None = None,
        scoring_summary: dict[str, Any] | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        ctx = audit_context or self._build_system_audit_context("score_suggestion")
        lifecycle.transition(SuggestionStatus.SCORED, ctx, reason=f"scored:{score:.1f}")

        rec = await self.pool_service.get_recommendation(suggestion_id)
        update_payload: dict[str, Any] = {"score": score}
        if confidence is not None:
            update_payload["confidence"] = confidence
        if scoring_summary:
            rec_payload = rec.get("payload") or {}
            rec_payload["scoring_summary"] = scoring_summary
            update_payload["payload"] = rec_payload

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.scored",
            payload={"score": score, "confidence": confidence},
        )

        return {**rec, "suggestion_status": lifecycle.status.value, "score": score, "confidence": confidence}

    async def submit_suggestion(
        self,
        suggestion_id: str,
        *,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        ctx = audit_context or self._build_system_audit_context("submit_suggestion")
        ctx.validate_for_write()
        lifecycle.transition(SuggestionStatus.SUBMITTED, ctx, reason="submitted_to_erp")

        rec = await self.pool_service.submit_to_erp(suggestion_id)

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.submitted",
            payload={"target_domain": rec.get("target_domain"), "erp_ref_id": rec.get("erp_ref_id")},
        )

        return {**rec, "suggestion_status": lifecycle.status.value}

    async def approve_suggestion(
        self,
        suggestion_id: str,
        *,
        detail: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        ctx = audit_context or self._build_system_audit_context("approve_suggestion")
        lifecycle.transition(SuggestionStatus.APPROVED, ctx, reason=detail or "erp_approved")

        target_state = SUGGESTION_TO_EXECUTION_STATE.get(SuggestionStatus.APPROVED, RecommendationExecutionState.ERP_APPROVED)
        rec = await self.pool_service.advance_state(suggestion_id, target_state, detail=detail)

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.approved",
            payload={"detail": detail, "execution_state": target_state.value},
        )

        return {**rec, "suggestion_status": lifecycle.status.value}

    async def reject_suggestion(
        self,
        suggestion_id: str,
        *,
        reason: str,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        ctx = audit_context or self._build_system_audit_context("reject_suggestion")
        lifecycle.transition(SuggestionStatus.REJECTED, ctx, reason=reason)

        rec = await self.pool_service.reject_recommendation(suggestion_id, reason=reason)

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.rejected",
            payload={"reason": reason},
        )

        return {**rec, "suggestion_status": lifecycle.status.value}

    async def mark_executing(
        self,
        suggestion_id: str,
        *,
        detail: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        ctx = audit_context or self._build_system_audit_context("mark_executing")
        lifecycle.transition(SuggestionStatus.EXECUTING, ctx, reason=detail or "erp_executing")

        rec = await self.pool_service.advance_state(
            suggestion_id, RecommendationExecutionState.SCM_REVIEWING, detail=detail
        )

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.executing",
            payload={"detail": detail},
        )

        return {**rec, "suggestion_status": lifecycle.status.value}

    async def mark_executed(
        self,
        suggestion_id: str,
        *,
        detail: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        ctx = audit_context or self._build_system_audit_context("mark_executed")
        lifecycle.transition(SuggestionStatus.EXECUTED, ctx, reason=detail or "erp_executed")

        rec = await self.pool_service.advance_state(
            suggestion_id, RecommendationExecutionState.EXECUTED, detail=detail
        )

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.executed",
            payload={"detail": detail},
        )

        return {**rec, "suggestion_status": lifecycle.status.value}

    async def mark_failed(
        self,
        suggestion_id: str,
        *,
        detail: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        ctx = audit_context or self._build_system_audit_context("mark_failed")
        lifecycle.transition(SuggestionStatus.FAILED, ctx, reason=detail or "execution_failed")

        rec = await self.pool_service.advance_state(
            suggestion_id, RecommendationExecutionState.EXECUTION_FAILED, detail=detail
        )

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.failed",
            payload={"detail": detail},
        )

        return {**rec, "suggestion_status": lifecycle.status.value}

    async def mark_measured(
        self,
        suggestion_id: str,
        *,
        measurement: dict[str, Any] | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        ctx = audit_context or self._build_system_audit_context("mark_measured")
        lifecycle.transition(SuggestionStatus.MEASURED, ctx, reason="effect_measured")

        rec = await self.pool_service.advance_state(
            suggestion_id, RecommendationExecutionState.CLOSED, detail="effect_measured"
        )

        if measurement:
            await self.pool_service.receive_erp_feedback(
                suggestion_id, feedback={"measurement": measurement}
            )

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.measured",
            payload={"measurement": measurement},
        )

        return {**rec, "suggestion_status": lifecycle.status.value}

    async def mark_reviewed(
        self,
        suggestion_id: str,
        *,
        review_notes: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        ctx = audit_context or self._build_system_audit_context("mark_reviewed")
        lifecycle.transition(SuggestionStatus.REVIEWED, ctx, reason=review_notes or "review_completed")

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.reviewed",
            payload={"review_notes": review_notes},
        )

        return {"suggestion_id": suggestion_id, "suggestion_status": lifecycle.status.value}

    async def discard_suggestion(
        self,
        suggestion_id: str,
        *,
        reason: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        ctx = audit_context or self._build_system_audit_context("discard_suggestion")
        lifecycle.transition(SuggestionStatus.DISCARDED, ctx, reason=reason or "user_discarded")

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.discarded",
            payload={"reason": reason},
        )

        return {"suggestion_id": suggestion_id, "suggestion_status": lifecycle.status.value}

    async def expire_suggestion(
        self,
        suggestion_id: str,
        *,
        reason: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        ctx = audit_context or self._build_system_audit_context("expire_suggestion")
        lifecycle.transition(SuggestionStatus.EXPIRED, ctx, reason=reason or "approval_timeout_24h")

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.expired",
            payload={"reason": reason or "approval_timeout_24h"},
        )

        return {"suggestion_id": suggestion_id, "suggestion_status": lifecycle.status.value}

    async def check_and_expire_submitted(
        self,
        submitted_ids: list[dict[str, Any]],
        *,
        timeout_hours: int = 24,
    ) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        expired_results: list[dict[str, Any]] = []
        for item in submitted_ids:
            suggestion_id = item.get("suggestion_id") or item.get("id")
            submitted_at_str = item.get("submitted_at")
            if not suggestion_id or not submitted_at_str:
                continue
            try:
                submitted_at = datetime.fromisoformat(submitted_at_str.replace("Z", "+00:00")) if isinstance(submitted_at_str, str) else submitted_at_str
            except (ValueError, AttributeError):
                continue
            elapsed_hours = (now - submitted_at).total_seconds() / 3600
            if elapsed_hours > timeout_hours:
                result = await self.expire_suggestion(suggestion_id)
                expired_results.append(result)
        if expired_results:
            logger.info("自动过期建议: %d 条", len(expired_results))
        return expired_results

    async def check_tenant_rate_limit(
        self,
        *,
        tenant_id: str | None = None,
        max_per_hour: int = 100,
    ) -> dict[str, Any]:
        tid = tenant_id or str(self.tenant_id)
        if not tid:
            return {"allowed": True, "reason": "no_tenant_id"}
        current_count = await self._get_tenant_submission_count(tid)
        allowed = current_count < max_per_hour
        return {
            "allowed": allowed,
            "tenant_id": tid,
            "current_count": current_count,
            "max_per_hour": max_per_hour,
            "remaining": max(0, max_per_hour - current_count),
        }

    async def _get_tenant_submission_count(self, tenant_id: str) -> int:
        try:
            stats = await self.pool_service.get_recommendation_statistics()
            return stats.get("submitted_last_hour", 0)
        except Exception:
            logger.exception("获取租户提交计数失败: tenant_id=%s", tenant_id)
            return 0

    async def sync_from_execution_state(
        self,
        suggestion_id: str,
        execution_state: RecommendationExecutionState,
        *,
        detail: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        target_suggestion_status = EXECUTION_TO_SUGGESTION_STATE.get(execution_state)
        if target_suggestion_status is None:
            logger.warning("无法映射执行状态到建议状态: %s", execution_state.value)
            return {"suggestion_id": suggestion_id, "error": "unmapped_execution_state", "execution_state": execution_state.value}

        lifecycle = self._get_lifecycle(suggestion_id)
        allowed = ALLOWED_SUGGESTION_TRANSITIONS.get(lifecycle.status, set())
        if target_suggestion_status not in allowed:
            logger.warning(
                "建议状态转换不合法: %s -> %s (执行状态: %s)",
                lifecycle.status.value,
                target_suggestion_status.value,
                execution_state.value,
            )
            return {"suggestion_id": suggestion_id, "error": "illegal_transition", "from": lifecycle.status.value, "to": target_suggestion_status.value}

        ctx = audit_context or self._build_system_audit_context("sync_from_execution_state")
        lifecycle.transition(target_suggestion_status, ctx, reason=detail or f"synced_from_{execution_state.value}")

        await self._publish_suggestion_event(
            suggestion_id=suggestion_id,
            event_type="suggestion.state_synced",
            payload={"execution_state": execution_state.value, "suggestion_status": target_suggestion_status.value},
        )

        return {"suggestion_id": suggestion_id, "suggestion_status": lifecycle.status.value, "execution_state": execution_state.value}

    async def get_suggestion_lifecycle(self, suggestion_id: str) -> dict[str, Any]:
        lifecycle = self._get_lifecycle(suggestion_id)
        allowed_next = ALLOWED_SUGGESTION_TRANSITIONS.get(lifecycle.status, set())
        controller = SUGGESTION_STATUS_CONTROLLER.get(lifecycle.status, "unknown")
        return {
            "suggestion_id": suggestion_id,
            "current_status": lifecycle.status.value,
            "controller": controller,
            "allowed_transitions": [s.value for s in allowed_next],
            "audit_log": lifecycle.audit_log,
        }

    def _get_lifecycle(self, suggestion_id: str) -> SuggestionLifecycle:
        if suggestion_id not in self._lifecycles:
            self._lifecycles[suggestion_id] = SuggestionLifecycle(suggestion_id=suggestion_id)
        return self._lifecycles[suggestion_id]

    def _build_system_audit_context(self, purpose: str) -> AuditContext:
        from uuid import uuid4
        return AuditContext(
            tenant_id=str(self.tenant_id) if self.tenant_id else "system",
            actor_type="service",
            actor_id=self.actor.get("user_id") or self.actor.get("sub") or "pms-suggestion-service",
            scope="tenant",
            purpose=purpose,
            trace_id=f"suggestion-{uuid4()}",
            idempotency_key=None,
            source_system="pms",
        )

    @staticmethod
    def _resolve_write_object(category: RecommendationCategory) -> str:
        mapping = {
            RecommendationCategory.SELECTION: "recommendation",
            RecommendationCategory.PRICING: "recommendation",
            RecommendationCategory.RESTOCK: "recommendation",
            RecommendationCategory.AD_OPTIMIZATION: "recommendation",
            RecommendationCategory.RISK_ALERT: "risk_alert",
            RecommendationCategory.LISTING_DRAFT: "draft",
            RecommendationCategory.PURCHASE_DRAFT: "draft",
            RecommendationCategory.INVENTORY_PREDICTION: "recommendation",
            RecommendationCategory.SENTIMENT_INSIGHT: "insight_card",
            RecommendationCategory.LOGISTICS_RISK: "risk_alert",
            RecommendationCategory.PROFIT_INSIGHT: "insight_card",
        }
        return mapping.get(category, "recommendation")

    async def _publish_suggestion_event(
        self,
        *,
        suggestion_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            await send_message(
                topic="pms.suggestion.lifecycle",
                message={
                    "event_type": event_type,
                    "aggregate_id": suggestion_id,
                    "tenant_id": str(self.tenant_id) if self.tenant_id else None,
                    "payload": payload,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "source": "pms",
                },
                key=suggestion_id.encode("utf-8") if suggestion_id else None,
            )
        except Exception:
            logger.exception("发布建议生命周期事件失败: suggestion_id=%s event_type=%s", suggestion_id, event_type)

    async def get_suggestion_stats(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        domain_counts: dict[str, int] = {}
        total = len(self._lifecycles)
        for lifecycle in self._lifecycles.values():
            status_key = lifecycle.status.value
            status_counts[status_key] = status_counts.get(status_key, 0) + 1
            domain_key = lifecycle.metadata.get("target_domain", "unknown")
            domain_counts[domain_key] = domain_counts.get(domain_key, 0) + 1
        return {
            "total_suggestions": total,
            "by_status": status_counts,
            "by_domain": domain_counts,
        }
