from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.core.pms_governance import (
    validate_pms_write_boundary,
    validate_pms_write_object,
)
from src.infrastructure.kafka import send_message
from src.models.enums import (
    RecommendationCategory,
    RecommendationExecutionState,
    RecommendationPriority,
    can_transition,
)
from src.models.models import Recommendation

logger = get_logger(__name__)


class RecommendationPoolService:
    """
    建议池管理服务。

    职责:
    - 创建PMS建议(选品/定价/补货/广告/风控等)
    - 管理建议生命周期(13态状态机)
    - 提交建议至ERP建议池/草稿
    - 接收ERP执行反馈并更新状态
    - 发布建议状态变更事件(Kafka)
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}

    async def create_recommendation(
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
    ) -> dict[str, Any]:
        write_object = self._resolve_write_object(category)
        validate_pms_write_object(write_object)
        validate_pms_write_boundary(target_domain, write_object)

        rec = Recommendation(
            tenant_id=UUID(str(self.tenant_id)) if self.tenant_id else uuid4(),
            category=category,
            priority=priority,
            execution_state=RecommendationExecutionState.SUGGESTED,
            target_domain=target_domain,
            title=title,
            description=description,
            score=score,
            confidence=confidence,
            evidence_chain=evidence_chain,
            data_sources=data_sources,
            risk_flags=risk_flags,
            payload=payload,
            source_task_id=source_task_id,
            source_product_id=source_product_id,
            created_by=UUID(str(self.actor.get("user_id"))) if self.actor.get("user_id") else None,
        )
        self.session.add(rec)
        await self.session.flush()

        await self._publish_event(
            topic="pms.recommendation.created",
            aggregate_id=str(rec.id),
            event_type="recommendation.created",
            payload={
                "recommendation_id": str(rec.id),
                "category": category.value,
                "target_domain": target_domain,
                "priority": priority.value,
                "score": score,
                "confidence": confidence,
            },
        )

        return self._serialize_recommendation(rec)

    async def approve_recommendation(self, recommendation_id: str, *, detail: str | None = None) -> dict[str, Any]:
        rec = await self._get_recommendation(recommendation_id)
        target_state = RecommendationExecutionState.PMS_APPROVED
        if not can_transition(rec.execution_state, target_state):
            return {"error": f"无法从 {rec.execution_state.value} 转换到 {target_state.value}", "current_state": rec.execution_state.value}

        rec.execution_state = target_state
        await self.session.flush()

        await self._publish_event(
            topic="pms.recommendation.approved",
            aggregate_id=str(rec.id),
            event_type="recommendation.pms_approved",
            payload={"recommendation_id": str(rec.id), "detail": detail},
        )

        return self._serialize_recommendation(rec)

    async def reject_recommendation(self, recommendation_id: str, *, reason: str) -> dict[str, Any]:
        rec = await self._get_recommendation(recommendation_id)
        target_state = RecommendationExecutionState.PMS_REJECTED
        if not can_transition(rec.execution_state, target_state):
            return {"error": f"无法从 {rec.execution_state.value} 转换到 {target_state.value}", "current_state": rec.execution_state.value}

        rec.execution_state = target_state
        rec.rejection_reason = reason
        await self.session.flush()

        await self._publish_event(
            topic="pms.recommendation.rejected",
            aggregate_id=str(rec.id),
            event_type="recommendation.pms_rejected",
            payload={"recommendation_id": str(rec.id), "reason": reason},
        )

        return self._serialize_recommendation(rec)

    async def submit_to_erp(self, recommendation_id: str, *, erp_ref_id: str | None = None) -> dict[str, Any]:
        rec = await self._get_recommendation(recommendation_id)
        target_state = RecommendationExecutionState.ERP_SUBMITTED
        if not can_transition(rec.execution_state, target_state):
            return {"error": f"无法从 {rec.execution_state.value} 转换到 {target_state.value}", "current_state": rec.execution_state.value}

        rec.execution_state = target_state
        rec.erp_ref_id = erp_ref_id
        rec.submitted_at = datetime.now(UTC)
        await self.session.flush()

        await self._publish_event(
            topic="pms.recommendation.submitted_to_erp",
            aggregate_id=str(rec.id),
            event_type="recommendation.erp_submitted",
            payload={"recommendation_id": str(rec.id), "erp_ref_id": erp_ref_id, "target_domain": rec.target_domain},
        )

        return self._serialize_recommendation(rec)

    async def advance_state(
        self,
        recommendation_id: str,
        target_state: RecommendationExecutionState,
        *,
        detail: str | None = None,
        erp_ref_id: str | None = None,
    ) -> dict[str, Any]:
        rec = await self._get_recommendation(recommendation_id)
        if not can_transition(rec.execution_state, target_state):
            return {"error": f"无法从 {rec.execution_state.value} 转换到 {target_state.value}", "current_state": rec.execution_state.value}

        rec.execution_state = target_state
        if erp_ref_id:
            rec.erp_ref_id = erp_ref_id
        if target_state == RecommendationExecutionState.CLOSED:
            rec.closed_at = datetime.now(UTC)
        if target_state == RecommendationExecutionState.EXECUTION_FAILED:
            rec.feedback = rec.feedback or {}
            rec.feedback["failure_detail"] = detail
            rec.feedback["failed_at"] = datetime.now(UTC).isoformat()
        await self.session.flush()

        event_topic = "pms.recommendation.state_changed"
        await self._publish_event(
            topic=event_topic,
            aggregate_id=str(rec.id),
            event_type=f"recommendation.{target_state.value}",
            payload={
                "recommendation_id": str(rec.id),
                "from_state": rec.execution_state.value,
                "to_state": target_state.value,
                "detail": detail,
            },
        )

        return self._serialize_recommendation(rec)

    async def receive_erp_feedback(
        self,
        recommendation_id: str,
        *,
        execution_state: str | None = None,
        feedback: dict[str, Any] | None = None,
        erp_ref_id: str | None = None,
    ) -> dict[str, Any]:
        rec = await self._get_recommendation(recommendation_id)
        rec.feedback = feedback or {}
        if erp_ref_id:
            rec.erp_ref_id = erp_ref_id
        if execution_state:
            try:
                target_state = RecommendationExecutionState(execution_state)
                if can_transition(rec.execution_state, target_state):
                    rec.execution_state = target_state
                    if target_state == RecommendationExecutionState.CLOSED:
                        rec.closed_at = datetime.now(UTC)
                        rec.executed_at = rec.executed_at or datetime.now(UTC)
            except ValueError:
                logger.warning("未知的执行状态: %s", execution_state)

        await self.session.flush()

        await self._publish_event(
            topic="pms.recommendation.erp_feedback",
            aggregate_id=str(rec.id),
            event_type="recommendation.erp_feedback_received",
            payload={"recommendation_id": str(rec.id), "execution_state": execution_state, "feedback": feedback},
        )

        return self._serialize_recommendation(rec)

    async def list_recommendations(
        self,
        *,
        category: RecommendationCategory | None = None,
        target_domain: str | None = None,
        execution_state: RecommendationExecutionState | None = None,
        priority: RecommendationPriority | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = select(Recommendation)
        count_query = select(func.count()).select_from(Recommendation)

        if self.tenant_id:
            query = query.where(Recommendation.tenant_id == UUID(str(self.tenant_id)))
            count_query = count_query.where(Recommendation.tenant_id == UUID(str(self.tenant_id)))
        if category:
            query = query.where(Recommendation.category == category)
            count_query = count_query.where(Recommendation.category == category)
        if target_domain:
            query = query.where(Recommendation.target_domain == target_domain)
            count_query = count_query.where(Recommendation.target_domain == target_domain)
        if execution_state:
            query = query.where(Recommendation.execution_state == execution_state)
            count_query = count_query.where(Recommendation.execution_state == execution_state)
        if priority:
            query = query.where(Recommendation.priority == priority)
            count_query = count_query.where(Recommendation.priority == priority)

        query = query.order_by(Recommendation.created_at.desc()).limit(limit).offset(offset)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        result = await self.session.execute(query)
        recommendations = result.scalars().all()

        return {
            "total": total,
            "items": [self._serialize_recommendation(r) for r in recommendations],
            "limit": limit,
            "offset": offset,
        }

    async def get_recommendation(self, recommendation_id: str) -> dict[str, Any]:
        rec = await self._get_recommendation(recommendation_id)
        return self._serialize_recommendation(rec)

    async def get_recommendations_by_task(self, task_id: str, *, limit: int = 50) -> dict[str, Any]:
        query = select(Recommendation).where(
            Recommendation.source_task_id == UUID(task_id)
        ).order_by(Recommendation.created_at.desc()).limit(limit)
        if self.tenant_id:
            query = query.where(Recommendation.tenant_id == UUID(str(self.tenant_id)))

        result = await self.session.execute(query)
        recommendations = result.scalars().all()

        return {
            "task_id": task_id,
            "items": [self._serialize_recommendation(r) for r in recommendations],
            "total": len(recommendations),
        }

    async def get_recommendation_statistics(self) -> dict[str, Any]:
        base_query = select(Recommendation)
        if self.tenant_id:
            base_query = base_query.where(Recommendation.tenant_id == UUID(str(self.tenant_id)))

        stats: dict[str, Any] = {
            "by_state": {},
            "by_category": {},
            "by_domain": {},
            "by_priority": {},
        }

        for state in RecommendationExecutionState:
            count_query = select(func.count()).select_from(Recommendation).where(
                Recommendation.execution_state == state
            )
            if self.tenant_id:
                count_query = count_query.where(Recommendation.tenant_id == UUID(str(self.tenant_id)))
            result = await self.session.execute(count_query)
            stats["by_state"][state.value] = result.scalar() or 0

        for category in RecommendationCategory:
            count_query = select(func.count()).select_from(Recommendation).where(
                Recommendation.category == category
            )
            if self.tenant_id:
                count_query = count_query.where(Recommendation.tenant_id == UUID(str(self.tenant_id)))
            result = await self.session.execute(count_query)
            stats["by_category"][category.value] = result.scalar() or 0

        return stats

    async def _get_recommendation(self, recommendation_id: str) -> Recommendation:
        query = select(Recommendation).where(Recommendation.id == UUID(recommendation_id))
        if self.tenant_id:
            query = query.where(Recommendation.tenant_id == UUID(str(self.tenant_id)))
        result = await self.session.execute(query)
        rec = result.scalar_one_or_none()
        if rec is None:
            raise ValueError(f"建议不存在: {recommendation_id}")
        return rec

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

    @staticmethod
    def _serialize_recommendation(rec: Recommendation) -> dict[str, Any]:
        return {
            "id": str(rec.id),
            "tenant_id": str(rec.tenant_id),
            "category": rec.category.value if rec.category else None,
            "priority": rec.priority.value if rec.priority else None,
            "execution_state": rec.execution_state.value if rec.execution_state else None,
            "target_domain": rec.target_domain,
            "title": rec.title,
            "description": rec.description,
            "score": rec.score,
            "confidence": rec.confidence,
            "evidence_chain": rec.evidence_chain,
            "data_sources": rec.data_sources,
            "risk_flags": rec.risk_flags,
            "payload": rec.payload,
            "source_task_id": str(rec.source_task_id) if rec.source_task_id else None,
            "source_product_id": str(rec.source_product_id) if rec.source_product_id else None,
            "erp_ref_id": rec.erp_ref_id,
            "rejection_reason": rec.rejection_reason,
            "feedback": rec.feedback,
            "created_by": str(rec.created_by) if rec.created_by else None,
            "submitted_at": rec.submitted_at.isoformat() if rec.submitted_at else None,
            "executed_at": rec.executed_at.isoformat() if rec.executed_at else None,
            "closed_at": rec.closed_at.isoformat() if rec.closed_at else None,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
            "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
        }

    async def _publish_event(
        self,
        *,
        topic: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            await send_message(
                topic=topic,
                message={
                    "event_type": event_type,
                    "aggregate_id": aggregate_id,
                    "tenant_id": str(self.tenant_id) if self.tenant_id else None,
                    "payload": payload,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "source": "pms",
                },
                key=aggregate_id.encode("utf-8") if aggregate_id else None,
            )
        except Exception:
            logger.exception("发布建议事件失败: topic=%s aggregate_id=%s", topic, aggregate_id)
