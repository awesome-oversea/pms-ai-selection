from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.enums import RecommendationCategory, RecommendationPriority
from src.models.models import PricingSuggestion
from src.services.recommendation_pool_service import RecommendationPoolService

logger = get_logger(__name__)


class PricingSuggestionService:
    """
    定价建议服务。

    职责:
    - 基于市场数据、竞品分析、成本结构生成定价建议
    - 支持新品定价、调价、促销定价等场景
    - 将定价建议提交至ERP SOM域建议池
    - 跟踪定价效果反馈
    """

    DEFAULT_TARGET_MARGIN = 0.25
    PRICE_COMPETITIVENESS_THRESHOLD = 1.15

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.pool_service = RecommendationPoolService(session, tenant_id=self.tenant_id, actor=self.actor)

    async def generate_new_product_pricing(
        self,
        *,
        product_id: str,
        cost_data: dict[str, Any],
        market_data: dict[str, Any],
        target_margin: float | None = None,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        effective_margin = target_margin or self.DEFAULT_TARGET_MARGIN
        cost_price = cost_data.get("total_cost", 0)
        suggested_price = self._calculate_cost_plus_price(cost_price, effective_margin)
        market_adjusted_price = self._adjust_for_market(suggested_price, market_data)
        competitor_price = market_data.get("avg_competitor_price")
        final_price = self._resolve_final_price(market_adjusted_price, competitor_price, cost_price, effective_margin)

        margin_analysis = self._analyze_margin(final_price, cost_price)
        competitiveness = self._analyze_competitiveness(final_price, market_data)

        suggestion = PricingSuggestion(
            tenant_id=UUID(str(self.tenant_id)) if self.tenant_id else uuid4(),
            product_id=UUID(product_id) if product_id else None,
            suggestion_type="new_product_pricing",
            current_price=None,
            suggested_price=final_price,
            cost_price=cost_price,
            target_margin=effective_margin,
            margin_analysis=margin_analysis,
            competitor_analysis=competitiveness,
            marketplace=marketplace,
            confidence=self._calculate_confidence(market_data, cost_data),
        )
        self.session.add(suggestion)
        await self.session.flush()

        pool_result = await self.pool_service.create_recommendation(
            category=RecommendationCategory.PRICING,
            target_domain="som",
            title=f"新品定价建议 - 产品 {product_id}",
            description=f"建议定价 ¥{final_price:.2f}, 目标利润率 {effective_margin:.0%}",
            priority=RecommendationPriority.MEDIUM,
            score=self._calculate_pricing_score(margin_analysis, competitiveness),
            confidence=suggestion.confidence,
            evidence_chain={"cost_data": cost_data, "market_data": market_data, "margin_analysis": margin_analysis},
            data_sources=[{"type": "cost_analysis"}, {"type": "market_analysis", "marketplace": marketplace}],
            risk_flags=self._identify_pricing_risks(final_price, cost_price, market_data),
            payload={"suggestion_id": str(suggestion.id), "suggested_price": final_price, "margin": margin_analysis},
            source_product_id=UUID(product_id) if product_id else None,
        )

        suggestion.recommendation_id = UUID(pool_result["id"])
        await self.session.flush()

        return self._serialize_suggestion(suggestion, pool_result)

    async def generate_price_adjustment(
        self,
        *,
        product_id: str,
        current_price: float,
        cost_data: dict[str, Any],
        market_data: dict[str, Any],
        sales_data: dict[str, Any],
        target_margin: float | None = None,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        effective_margin = target_margin or self.DEFAULT_TARGET_MARGIN
        cost_price = cost_data.get("total_cost", 0)

        suggested_price = self._calculate_adjusted_price(
            current_price, cost_price, effective_margin, market_data, sales_data
        )
        margin_analysis = self._analyze_margin(suggested_price, cost_price)
        competitiveness = self._analyze_competitiveness(suggested_price, market_data)
        price_impact = self._estimate_price_impact(current_price, suggested_price, sales_data)

        suggestion = PricingSuggestion(
            tenant_id=UUID(str(self.tenant_id)) if self.tenant_id else uuid4(),
            product_id=UUID(product_id) if product_id else None,
            suggestion_type="price_adjustment",
            current_price=current_price,
            suggested_price=suggested_price,
            cost_price=cost_price,
            target_margin=effective_margin,
            margin_analysis=margin_analysis,
            competitor_analysis=competitiveness,
            price_impact_estimate=price_impact,
            marketplace=marketplace,
            confidence=self._calculate_confidence(market_data, cost_data, sales_data),
        )
        self.session.add(suggestion)
        await self.session.flush()

        price_change_pct = (suggested_price - current_price) / max(current_price, 0.01)
        priority = RecommendationPriority.HIGH if abs(price_change_pct) > 0.1 else RecommendationPriority.MEDIUM

        pool_result = await self.pool_service.create_recommendation(
            category=RecommendationCategory.PRICING,
            target_domain="som",
            title=f"调价建议 - 产品 {product_id}",
            description=f"建议从 ¥{current_price:.2f} 调整为 ¥{suggested_price:.2f} ({price_change_pct:+.1%})",
            priority=priority,
            score=self._calculate_pricing_score(margin_analysis, competitiveness),
            confidence=suggestion.confidence,
            evidence_chain={
                "current_price": current_price,
                "suggested_price": suggested_price,
                "margin_analysis": margin_analysis,
                "price_impact": price_impact,
            },
            data_sources=[{"type": "cost_analysis"}, {"type": "market_analysis"}, {"type": "sales_analysis"}],
            risk_flags=self._identify_pricing_risks(suggested_price, cost_price, market_data),
            payload={
                "suggestion_id": str(suggestion.id),
                "current_price": current_price,
                "suggested_price": suggested_price,
                "price_change_pct": price_change_pct,
            },
            source_product_id=UUID(product_id) if product_id else None,
        )

        suggestion.recommendation_id = UUID(pool_result["id"])
        await self.session.flush()

        return self._serialize_suggestion(suggestion, pool_result)

    async def generate_promotional_pricing(
        self,
        *,
        product_id: str,
        current_price: float,
        cost_data: dict[str, Any],
        promotion_data: dict[str, Any],
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        cost_price = cost_data.get("total_cost", 0)
        min_margin = promotion_data.get("min_margin", 0.05)
        discount_pct = promotion_data.get("discount_pct", 0.15)
        promo_price = current_price * (1 - discount_pct)
        min_price = cost_price / (1 - min_margin)
        final_promo_price = max(promo_price, min_price)

        margin_analysis = self._analyze_margin(final_promo_price, cost_price)

        suggestion = PricingSuggestion(
            tenant_id=UUID(str(self.tenant_id)) if self.tenant_id else uuid4(),
            product_id=UUID(product_id) if product_id else None,
            suggestion_type="promotional_pricing",
            current_price=current_price,
            suggested_price=final_promo_price,
            cost_price=cost_price,
            target_margin=min_margin,
            margin_analysis=margin_analysis,
            marketplace=marketplace,
            confidence=0.7,
        )
        self.session.add(suggestion)
        await self.session.flush()

        pool_result = await self.pool_service.create_recommendation(
            category=RecommendationCategory.PRICING,
            target_domain="som",
            title=f"促销定价建议 - 产品 {product_id}",
            description=f"建议促销价 ¥{final_promo_price:.2f} (原价 ¥{current_price:.2f}, 折扣 {discount_pct:.0%})",
            priority=RecommendationPriority.MEDIUM,
            score=margin_analysis.get("margin_rate", 0) * 100,
            confidence=0.7,
            evidence_chain={"current_price": current_price, "promo_price": final_promo_price, "promotion_data": promotion_data},
            payload={"suggestion_id": str(suggestion.id), "promo_price": final_promo_price, "discount_pct": discount_pct},
            source_product_id=UUID(product_id) if product_id else None,
        )

        suggestion.recommendation_id = UUID(pool_result["id"])
        await self.session.flush()

        return self._serialize_suggestion(suggestion, pool_result)

    async def list_suggestions(
        self,
        *,
        suggestion_type: str | None = None,
        status: str | None = None,
        marketplace: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = select(PricingSuggestion)
        count_query = select(func.count()).select_from(PricingSuggestion)

        if self.tenant_id:
            query = query.where(PricingSuggestion.tenant_id == UUID(str(self.tenant_id)))
            count_query = count_query.where(PricingSuggestion.tenant_id == UUID(str(self.tenant_id)))
        if suggestion_type:
            query = query.where(PricingSuggestion.suggestion_type == suggestion_type)
            count_query = count_query.where(PricingSuggestion.suggestion_type == suggestion_type)
        if status:
            query = query.where(PricingSuggestion.status == status)
            count_query = count_query.where(PricingSuggestion.status == status)
        if marketplace:
            query = query.where(PricingSuggestion.marketplace == marketplace)
            count_query = count_query.where(PricingSuggestion.marketplace == marketplace)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(PricingSuggestion.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        suggestions = result.scalars().all()

        return {
            "total": total,
            "items": [self._serialize_suggestion(s) for s in suggestions],
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def _calculate_cost_plus_price(cost: float, target_margin: float) -> float:
        if cost <= 0:
            return 0.0
        return cost / (1 - target_margin)

    @staticmethod
    def _adjust_for_market(base_price: float, market_data: dict[str, Any]) -> float:
        price_elasticity = market_data.get("price_elasticity", 1.0)
        if price_elasticity > 1.5:
            adjusted = base_price * 0.95
        elif price_elasticity < 0.8:
            adjusted = base_price * 1.05
        else:
            adjusted = base_price
        return max(adjusted, base_price * 0.7)

    @staticmethod
    def _resolve_final_price(
        market_price: float,
        competitor_price: float | None,
        cost: float,
        min_margin: float,
    ) -> float:
        floor_price = cost / (1 - min_margin)
        if competitor_price and competitor_price > floor_price:
            return min(market_price, competitor_price * 1.02)
        return max(market_price, floor_price)

    @staticmethod
    def _analyze_margin(price: float, cost: float) -> dict[str, Any]:
        if price <= 0:
            return {"margin_rate": 0, "margin_amount": 0, "is_profitable": False}
        margin_rate = (price - cost) / price
        return {
            "margin_rate": round(margin_rate, 4),
            "margin_amount": round(price - cost, 2),
            "is_profitable": margin_rate > 0,
        }

    @staticmethod
    def _analyze_competitiveness(price: float, market_data: dict[str, Any]) -> dict[str, Any]:
        avg_competitor = market_data.get("avg_competitor_price")
        if not avg_competitor or avg_competitor <= 0:
            return {"competitiveness": "unknown", "price_position": "unknown"}
        ratio = price / avg_competitor
        if ratio < 0.9:
            position = "below_market"
        elif ratio <= 1.1:
            position = "at_market"
        else:
            position = "above_market"
        return {
            "competitiveness": position,
            "price_position": position,
            "price_vs_avg": round(ratio, 4),
            "avg_competitor_price": avg_competitor,
        }

    @staticmethod
    def _calculate_adjusted_price(
        current_price: float,
        cost: float,
        target_margin: float,
        market_data: dict[str, Any],
        sales_data: dict[str, Any],
    ) -> float:
        target_price = cost / (1 - target_margin)
        avg_market = market_data.get("avg_market_price", current_price)
        sales_trend = sales_data.get("sales_trend_30d", 0)

        if sales_trend < -0.2:
            suggested = min(target_price, avg_market * 0.95)
        elif sales_trend > 0.2:
            suggested = max(target_price, current_price * 1.03)
        else:
            suggested = target_price

        floor = cost / (1 - 0.05)
        return max(suggested, floor)

    @staticmethod
    def _estimate_price_impact(current_price: float, suggested_price: float, sales_data: dict[str, Any]) -> dict[str, Any]:
        change_pct = (suggested_price - current_price) / max(current_price, 0.01)
        elasticity = sales_data.get("price_elasticity", 1.0)
        volume_change = -change_pct * elasticity
        revenue_change = change_pct + volume_change + change_pct * volume_change
        return {
            "price_change_pct": round(change_pct, 4),
            "estimated_volume_change": round(volume_change, 4),
            "estimated_revenue_change": round(revenue_change, 4),
        }

    @staticmethod
    def _calculate_confidence(market_data: dict[str, Any], cost_data: dict[str, Any], sales_data: dict[str, Any] | None = None) -> float:
        confidence = 0.5
        if market_data.get("avg_competitor_price"):
            confidence += 0.15
        if market_data.get("price_elasticity"):
            confidence += 0.1
        if cost_data.get("total_cost"):
            confidence += 0.15
        if sales_data and sales_data.get("sales_trend_30d") is not None:
            confidence += 0.1
        return min(1.0, confidence)

    @staticmethod
    def _calculate_pricing_score(margin_analysis: dict[str, Any], competitiveness: dict[str, Any]) -> float:
        score = 50.0
        margin = margin_analysis.get("margin_rate", 0)
        if 0.15 <= margin <= 0.4:
            score += 30
        elif margin > 0:
            score += 15
        position = competitiveness.get("price_position", "unknown")
        if position == "at_market":
            score += 20
        elif position == "below_market":
            score += 10
        return min(100, score)

    @staticmethod
    def _identify_pricing_risks(price: float, cost: float, market_data: dict[str, Any]) -> list[dict[str, Any]]:
        risks = []
        if price <= cost:
            risks.append({"type": "loss_pricing", "detail": "定价低于成本", "severity": "critical"})
        margin = (price - cost) / max(price, 0.01)
        if margin < 0.1:
            risks.append({"type": "low_margin", "detail": f"利润率过低({margin:.1%})", "severity": "high"})
        avg_price = market_data.get("avg_competitor_price")
        if avg_price and price > avg_price * 1.3:
            risks.append({"type": "overpriced", "detail": "定价高于竞品均价30%+", "severity": "medium"})
        return risks

    @staticmethod
    def _serialize_suggestion(suggestion: PricingSuggestion, pool_data: dict[str, Any] | None = None) -> dict[str, Any]:
        result = {
            "id": str(suggestion.id),
            "tenant_id": str(suggestion.tenant_id),
            "recommendation_id": str(suggestion.recommendation_id) if suggestion.recommendation_id else None,
            "product_id": str(suggestion.product_id) if suggestion.product_id else None,
            "suggestion_type": suggestion.suggestion_type,
            "current_price": suggestion.current_price,
            "suggested_price": suggestion.suggested_price,
            "cost_price": suggestion.cost_price,
            "target_margin": suggestion.target_margin,
            "margin_analysis": suggestion.margin_analysis,
            "competitor_analysis": suggestion.competitor_analysis,
            "price_impact_estimate": suggestion.price_impact_estimate,
            "marketplace": suggestion.marketplace,
            "status": suggestion.status,
            "confidence": suggestion.confidence,
            "created_at": suggestion.created_at.isoformat() if suggestion.created_at else None,
        }
        if pool_data:
            result["recommendation_pool"] = pool_data
        return result
