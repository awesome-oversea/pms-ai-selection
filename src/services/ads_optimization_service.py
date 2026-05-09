from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.infrastructure.ads_client import ADSClient, ADSClientError
from src.models.enums import RecommendationCategory, RecommendationPriority
from src.models.models import AdOptimizationSuggestion
from src.services.recommendation_pool_service import RecommendationPoolService

logger = get_logger(__name__)


class AdsOptimizationService:
    """
    广告优化闭环服务。

    职责:
    - 基于广告指标生成优化建议(竞价调整/关键词建议/预算分配/活动优化)
    - 将建议提交至ERP ADS域建议池
    - 接收ADS域执行反馈并更新建议状态
    - 跟踪广告优化效果
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.pool_service = RecommendationPoolService(session, tenant_id=self.tenant_id, actor=self.actor)

    async def generate_bid_adjustment_suggestion(
        self,
        *,
        product_id: str,
        campaign_id: str,
        ad_group_id: str | None = None,
        current_metrics: dict[str, Any],
        suggested_bid: float | None = None,
        confidence: float | None = None,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        suggested_changes = {"bid": {"current": current_metrics.get("current_bid"), "suggested": suggested_bid}}
        expected_impact = self._estimate_bid_impact(current_metrics, suggested_bid)

        suggestion = AdOptimizationSuggestion(
            tenant_id=UUID(str(self.tenant_id)) if self.tenant_id else uuid4(),
            product_id=UUID(product_id) if product_id else None,
            suggestion_type="bid_adjustment",
            current_metrics=current_metrics,
            suggested_changes=suggested_changes,
            expected_impact=expected_impact,
            confidence=confidence,
            campaign_id=campaign_id,
            ad_group_id=ad_group_id,
            marketplace=marketplace,
        )
        self.session.add(suggestion)
        await self.session.flush()

        pool_result = await self.pool_service.create_recommendation(
            category=RecommendationCategory.AD_OPTIMIZATION,
            target_domain="ads",
            title=f"竞价调整建议 - 活动 {campaign_id}",
            description=f"建议将竞价从 {current_metrics.get('current_bid')} 调整为 {suggested_bid}",
            priority=self._resolve_priority(current_metrics),
            score=self._calculate_optimization_score(current_metrics),
            confidence=confidence,
            evidence_chain={"current_metrics": current_metrics, "suggested_bid": suggested_bid},
            data_sources=[{"type": "ads_metrics", "campaign_id": campaign_id}],
            risk_flags=self._identify_bid_risks(current_metrics, suggested_bid),
            payload={"suggestion_id": str(suggestion.id), "suggestion_type": "bid_adjustment", "suggested_changes": suggested_changes},
            source_product_id=UUID(product_id) if product_id else None,
        )

        suggestion.recommendation_id = UUID(pool_result["id"])
        await self.session.flush()

        return self._serialize_suggestion(suggestion, pool_result)

    async def generate_keyword_suggestion(
        self,
        *,
        product_id: str,
        campaign_id: str,
        current_keywords: list[str],
        suggested_keywords: list[dict[str, Any]],
        confidence: float | None = None,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        suggested_changes = {
            "keywords": {
                "current": current_keywords,
                "suggested": suggested_keywords,
            }
        }
        current_metrics = {"current_keyword_count": len(current_keywords)}

        suggestion = AdOptimizationSuggestion(
            tenant_id=UUID(str(self.tenant_id)) if self.tenant_id else uuid4(),
            product_id=UUID(product_id) if product_id else None,
            suggestion_type="keyword_suggestion",
            current_metrics=current_metrics,
            suggested_changes=suggested_changes,
            expected_impact={"estimated_ctr_improvement": 0.05, "estimated_impression_increase": 0.1},
            confidence=confidence,
            campaign_id=campaign_id,
            marketplace=marketplace,
        )
        self.session.add(suggestion)
        await self.session.flush()

        pool_result = await self.pool_service.create_recommendation(
            category=RecommendationCategory.AD_OPTIMIZATION,
            target_domain="ads",
            title=f"关键词优化建议 - 活动 {campaign_id}",
            description=f"建议新增 {len(suggested_keywords)} 个关键词",
            priority=RecommendationPriority.MEDIUM,
            score=self._calculate_keyword_score(suggested_keywords),
            confidence=confidence,
            evidence_chain={"current_keywords": current_keywords, "suggested_keywords": suggested_keywords},
            data_sources=[{"type": "ads_keyword_analysis", "campaign_id": campaign_id}],
            payload={"suggestion_id": str(suggestion.id), "suggestion_type": "keyword_suggestion", "suggested_changes": suggested_changes},
            source_product_id=UUID(product_id) if product_id else None,
        )

        suggestion.recommendation_id = UUID(pool_result["id"])
        await self.session.flush()

        return self._serialize_suggestion(suggestion, pool_result)

    async def generate_budget_allocation_suggestion(
        self,
        *,
        product_id: str,
        campaign_id: str,
        current_budget: float,
        suggested_budget: float,
        reasoning: str | None = None,
        confidence: float | None = None,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        suggested_changes = {"budget": {"current": current_budget, "suggested": suggested_budget}}
        current_metrics = {"current_budget": current_budget, "current_acos": None}
        expected_impact = {"budget_change_pct": (suggested_budget - current_budget) / max(current_budget, 0.01)}

        suggestion = AdOptimizationSuggestion(
            tenant_id=UUID(str(self.tenant_id)) if self.tenant_id else uuid4(),
            product_id=UUID(product_id) if product_id else None,
            suggestion_type="budget_allocation",
            current_metrics=current_metrics,
            suggested_changes=suggested_changes,
            expected_impact=expected_impact,
            confidence=confidence,
            campaign_id=campaign_id,
            marketplace=marketplace,
        )
        self.session.add(suggestion)
        await self.session.flush()

        pool_result = await self.pool_service.create_recommendation(
            category=RecommendationCategory.AD_OPTIMIZATION,
            target_domain="ads",
            title=f"预算分配建议 - 活动 {campaign_id}",
            description=reasoning or f"建议将预算从 ${current_budget:.2f} 调整为 ${suggested_budget:.2f}",
            priority=RecommendationPriority.MEDIUM,
            confidence=confidence,
            evidence_chain={"current_budget": current_budget, "suggested_budget": suggested_budget, "reasoning": reasoning},
            data_sources=[{"type": "ads_budget_analysis", "campaign_id": campaign_id}],
            payload={"suggestion_id": str(suggestion.id), "suggestion_type": "budget_allocation", "suggested_changes": suggested_changes},
            source_product_id=UUID(product_id) if product_id else None,
        )

        suggestion.recommendation_id = UUID(pool_result["id"])
        await self.session.flush()

        return self._serialize_suggestion(suggestion, pool_result)

    async def submit_to_ads_domain(
        self,
        suggestion_id: str,
        ads_client: ADSClient,
    ) -> dict[str, Any]:
        query = select(AdOptimizationSuggestion).where(AdOptimizationSuggestion.id == UUID(suggestion_id))
        if self.tenant_id:
            query = query.where(AdOptimizationSuggestion.tenant_id == UUID(str(self.tenant_id)))
        result = await self.session.execute(query)
        suggestion = result.scalar_one_or_none()
        if suggestion is None:
            raise ValueError(f"广告优化建议不存在: {suggestion_id}")

        payload = {
            "suggestion_id": str(suggestion.id),
            "suggestion_type": suggestion.suggestion_type,
            "suggested_changes": suggestion.suggested_changes,
            "expected_impact": suggestion.expected_impact,
            "confidence": suggestion.confidence,
            "campaign_id": suggestion.campaign_id,
            "ad_group_id": suggestion.ad_group_id,
            "marketplace": suggestion.marketplace,
        }

        try:
            erp_result = await ads_client.submit_ad_optimization_suggestion(payload)
            suggestion.status = "submitted"
            await self.session.flush()

            if suggestion.recommendation_id:
                await self.pool_service.submit_to_erp(
                    str(suggestion.recommendation_id),
                    erp_ref_id=erp_result.get("suggestion_id"),
                )

            return {"suggestion_id": str(suggestion.id), "status": "submitted", "erp_result": erp_result}
        except ADSClientError as e:
            suggestion.status = "submission_failed"
            await self.session.flush()
            raise ValueError(f"提交ADS域失败: {e}") from e

    async def receive_ads_feedback(
        self,
        suggestion_id: str,
        *,
        status: str,
        execution_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = select(AdOptimizationSuggestion).where(AdOptimizationSuggestion.id == UUID(suggestion_id))
        if self.tenant_id:
            query = query.where(AdOptimizationSuggestion.tenant_id == UUID(str(self.tenant_id)))
        result = await self.session.execute(query)
        suggestion = result.scalar_one_or_none()
        if suggestion is None:
            raise ValueError(f"广告优化建议不存在: {suggestion_id}")

        suggestion.status = status
        if suggestion.recommendation_id and execution_result:
            await self.pool_service.receive_erp_feedback(
                str(suggestion.recommendation_id),
                execution_state=execution_result.get("execution_state"),
                feedback=execution_result,
            )
        await self.session.flush()

        return self._serialize_suggestion(suggestion)

    async def list_suggestions(
        self,
        *,
        suggestion_type: str | None = None,
        status: str | None = None,
        campaign_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = select(AdOptimizationSuggestion)
        count_query = select(func.count()).select_from(AdOptimizationSuggestion)

        if self.tenant_id:
            query = query.where(AdOptimizationSuggestion.tenant_id == UUID(str(self.tenant_id)))
            count_query = count_query.where(AdOptimizationSuggestion.tenant_id == UUID(str(self.tenant_id)))
        if suggestion_type:
            query = query.where(AdOptimizationSuggestion.suggestion_type == suggestion_type)
            count_query = count_query.where(AdOptimizationSuggestion.suggestion_type == suggestion_type)
        if status:
            query = query.where(AdOptimizationSuggestion.status == status)
            count_query = count_query.where(AdOptimizationSuggestion.status == status)
        if campaign_id:
            query = query.where(AdOptimizationSuggestion.campaign_id == campaign_id)
            count_query = count_query.where(AdOptimizationSuggestion.campaign_id == campaign_id)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(AdOptimizationSuggestion.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        suggestions = result.scalars().all()

        return {
            "total": total,
            "items": [self._serialize_suggestion(s) for s in suggestions],
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def _estimate_bid_impact(current_metrics: dict[str, Any], suggested_bid: float | None) -> dict[str, Any]:
        current_bid = current_metrics.get("current_bid", 0)
        if not suggested_bid or not current_bid:
            return {}
        bid_change = (suggested_bid - current_bid) / max(current_bid, 0.01)
        return {
            "bid_change_pct": bid_change,
            "estimated_position_change": "improve" if bid_change > 0 else "maintain",
            "estimated_cost_change_pct": bid_change,
        }

    @staticmethod
    def _resolve_priority(current_metrics: dict[str, Any]) -> RecommendationPriority:
        acos = current_metrics.get("acos", 0)
        if acos and acos > 0.5:
            return RecommendationPriority.HIGH
        if acos and acos > 0.35:
            return RecommendationPriority.MEDIUM
        return RecommendationPriority.LOW

    @staticmethod
    def _calculate_optimization_score(current_metrics: dict[str, Any]) -> float:
        acos = current_metrics.get("acos", 0.3)
        roas = current_metrics.get("roas", 2.0)
        ctr = current_metrics.get("ctr", 0.1)
        score = 100.0
        if acos > 0.4:
            score -= 30
        elif acos > 0.3:
            score -= 15
        if roas < 2.0:
            score -= 20
        if ctr < 0.05:
            score -= 15
        return max(0, min(100, score))

    @staticmethod
    def _calculate_keyword_score(suggested_keywords: list[dict[str, Any]]) -> float:
        if not suggested_keywords:
            return 0.0
        avg_relevance = sum(kw.get("relevance_score", 50) for kw in suggested_keywords) / len(suggested_keywords)
        return min(100, avg_relevance)

    @staticmethod
    def _identify_bid_risks(current_metrics: dict[str, Any], suggested_bid: float | None) -> list[dict[str, Any]]:
        risks = []
        if suggested_bid and current_metrics.get("current_bid"):
            increase_pct = (suggested_bid - current_metrics["current_bid"]) / max(current_metrics["current_bid"], 0.01)
            if increase_pct > 0.5:
                risks.append({"type": "budget_risk", "detail": f"竞价提升超过50%({increase_pct:.0%})", "severity": "high"})
            if increase_pct > 0.3:
                risks.append({"type": "budget_risk", "detail": f"竞价提升超过30%({increase_pct:.0%})", "severity": "medium"})
        return risks

    @staticmethod
    def _serialize_suggestion(suggestion: AdOptimizationSuggestion, pool_data: dict[str, Any] | None = None) -> dict[str, Any]:
        result = {
            "id": str(suggestion.id),
            "tenant_id": str(suggestion.tenant_id),
            "recommendation_id": str(suggestion.recommendation_id) if suggestion.recommendation_id else None,
            "product_id": str(suggestion.product_id) if suggestion.product_id else None,
            "suggestion_type": suggestion.suggestion_type,
            "current_metrics": suggestion.current_metrics,
            "suggested_changes": suggestion.suggested_changes,
            "expected_impact": suggestion.expected_impact,
            "confidence": suggestion.confidence,
            "status": suggestion.status,
            "campaign_id": suggestion.campaign_id,
            "ad_group_id": suggestion.ad_group_id,
            "marketplace": suggestion.marketplace,
            "created_at": suggestion.created_at.isoformat() if suggestion.created_at else None,
        }
        if pool_data:
            result["recommendation_pool"] = pool_data
        return result
