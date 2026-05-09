from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.enums import RecommendationCategory, RecommendationPriority
from src.models.models import InventoryPrediction
from src.services.recommendation_pool_service import RecommendationPoolService

logger = get_logger(__name__)


class InventoryPredictionService:
    """
    库存预测服务。

    职责:
    - 基于历史销售数据预测未来库存需求
    - 支持短期(7天)/中期(30天)/长期(90天)预测
    - 生成补货建议关联至建议池
    - 跟踪预测准确度
    """

    SHORT_TERM_DAYS = 7
    MEDIUM_TERM_DAYS = 30
    LONG_TERM_DAYS = 90

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.pool_service = RecommendationPoolService(session, tenant_id=self.tenant_id, actor=self.actor)

    async def generate_prediction(
        self,
        *,
        product_id: str,
        sku: str | None = None,
        current_stock: int | None = None,
        historical_sales: list[dict[str, Any]] | None = None,
        seasonality_factor: float | None = None,
        promotion_calendar: list[dict[str, Any]] | None = None,
        lead_time_days: int | None = None,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        effective_sales = historical_sales or []
        avg_daily_sales = self._calculate_avg_daily_sales(effective_sales)
        trend = self._detect_sales_trend(effective_sales)
        seasonal_factor = seasonality_factor or self._estimate_seasonality(effective_sales)

        short_term = self._predict_demand(avg_daily_sales, trend, seasonal_factor, self.SHORT_TERM_DAYS, promotion_calendar)
        medium_term = self._predict_demand(avg_daily_sales, trend, seasonal_factor, self.MEDIUM_TERM_DAYS, promotion_calendar)
        long_term = self._predict_demand(avg_daily_sales, trend, seasonal_factor, self.LONG_TERM_DAYS, promotion_calendar)

        effective_stock = current_stock or 0
        effective_lead_time = lead_time_days or 30
        stockout_risk = self._assess_stockout_risk(effective_stock, short_term, medium_term)
        reorder_point = self._calculate_reorder_point(avg_daily_sales, effective_lead_time, seasonal_factor)
        optimal_order_qty = self._calculate_eoq(avg_daily_sales, effective_lead_time, seasonal_factor)

        prediction = InventoryPrediction(
            tenant_id=UUID(str(self.tenant_id)) if self.tenant_id else uuid4(),
            product_id=UUID(product_id) if product_id else None,
            sku=sku,
            prediction_horizon_days=self.MEDIUM_TERM_DAYS,
            predicted_demand_short=short_term,
            predicted_demand_medium=medium_term,
            predicted_demand_long=long_term,
            confidence=self._calculate_prediction_confidence(effective_sales, seasonal_factor),
            model_version="v1_weighted_avg",
            input_features={
                "avg_daily_sales": avg_daily_sales,
                "trend": trend,
                "seasonality_factor": seasonal_factor,
                "current_stock": effective_stock,
                "lead_time_days": effective_lead_time,
                "promotion_count": len(promotion_calendar or []),
            },
            current_stock=effective_stock,
            stockout_risk_score=stockout_risk["score"],
            stockout_risk_level=stockout_risk["level"],
            reorder_point=reorder_point,
            optimal_order_quantity=optimal_order_qty,
            marketplace=marketplace,
        )
        self.session.add(prediction)
        await self.session.flush()

        if stockout_risk["level"] in {"high", "critical"}:
            priority = RecommendationPriority.CRITICAL if stockout_risk["level"] == "critical" else RecommendationPriority.HIGH
            pool_result = await self.pool_service.create_recommendation(
                category=RecommendationCategory.INVENTORY_PREDICTION,
                target_domain="wms",
                title=f"库存预测预警 - {sku or product_id}",
                description=f"预计{self.MEDIUM_TERM_DAYS}天需求 {medium_term:.0f} 件，断货风险 {stockout_risk['level']}",
                priority=priority,
                score=stockout_risk["score"],
                confidence=prediction.confidence,
                evidence_chain={
                    "predicted_demand_medium": medium_term,
                    "current_stock": effective_stock,
                    "stockout_risk": stockout_risk,
                    "reorder_point": reorder_point,
                },
                data_sources=[{"type": "inventory_prediction", "model_version": prediction.model_version}],
                risk_flags=[{"type": "stockout_risk", "level": stockout_risk["level"], "score": stockout_risk["score"]}],
                payload={
                    "prediction_id": str(prediction.id),
                    "optimal_order_qty": optimal_order_qty,
                    "reorder_point": reorder_point,
                },
                source_product_id=UUID(product_id) if product_id else None,
            )
            prediction.recommendation_id = UUID(pool_result["id"])
            await self.session.flush()

        return self._serialize_prediction(prediction)

    async def list_predictions(
        self,
        *,
        sku: str | None = None,
        stockout_risk_level: str | None = None,
        marketplace: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = select(InventoryPrediction)
        count_query = select(func.count()).select_from(InventoryPrediction)

        if self.tenant_id:
            query = query.where(InventoryPrediction.tenant_id == UUID(str(self.tenant_id)))
            count_query = count_query.where(InventoryPrediction.tenant_id == UUID(str(self.tenant_id)))
        if sku:
            query = query.where(InventoryPrediction.sku == sku)
            count_query = count_query.where(InventoryPrediction.sku == sku)
        if stockout_risk_level:
            query = query.where(InventoryPrediction.stockout_risk_level == stockout_risk_level)
            count_query = count_query.where(InventoryPrediction.stockout_risk_level == stockout_risk_level)
        if marketplace:
            query = query.where(InventoryPrediction.marketplace == marketplace)
            count_query = count_query.where(InventoryPrediction.marketplace == marketplace)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(InventoryPrediction.stockout_risk_score.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        predictions = result.scalars().all()

        return {
            "total": total,
            "items": [self._serialize_prediction(p) for p in predictions],
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def _calculate_avg_daily_sales(historical_sales: list[dict[str, Any]]) -> float:
        if not historical_sales:
            return 0.0
        recent = historical_sales[-30:] if len(historical_sales) > 30 else historical_sales
        total = sum(s.get("quantity", 0) for s in recent)
        days = len(recent) or 1
        return total / days

    @staticmethod
    def _detect_sales_trend(historical_sales: list[dict[str, Any]]) -> str:
        if len(historical_sales) < 14:
            return "stable"
        recent_7 = sum(s.get("quantity", 0) for s in historical_sales[-7:])
        prev_7 = sum(s.get("quantity", 0) for s in historical_sales[-14:-7])
        if prev_7 == 0:
            return "growing" if recent_7 > 0 else "stable"
        change = (recent_7 - prev_7) / prev_7
        if change > 0.15:
            return "growing"
        if change < -0.15:
            return "declining"
        return "stable"

    @staticmethod
    def _estimate_seasonality(historical_sales: list[dict[str, Any]]) -> float:
        if len(historical_sales) < 60:
            return 1.0
        quantities = [s.get("quantity", 0) for s in historical_sales]
        avg = sum(quantities) / len(quantities)
        if avg == 0:
            return 1.0
        recent_avg = sum(quantities[-7:]) / 7
        return recent_avg / avg

    def _predict_demand(
        self,
        avg_daily: float,
        trend: str,
        seasonality: float,
        horizon_days: int,
        promotions: list[dict[str, Any]] | None = None,
    ) -> float:
        base_demand = avg_daily * horizon_days * seasonality
        trend_multiplier = {"growing": 1.1, "declining": 0.9, "stable": 1.0}.get(trend, 1.0)
        base_demand *= trend_multiplier
        promo_boost = 0.0
        if promotions:
            for promo in promotions:
                boost_pct = promo.get("expected_demand_increase", 0.2)
                promo_boost += base_demand * boost_pct * 0.1
        return max(0, base_demand + promo_boost)

    def _assess_stockout_risk(self, current_stock: int, short_term_demand: float, medium_term_demand: float) -> dict[str, Any]:
        if short_term_demand <= 0:
            return {"score": 0, "level": "low"}
        days_of_supply = current_stock / (short_term_demand / self.SHORT_TERM_DAYS) if short_term_demand > 0 else 999
        if days_of_supply <= 7:
            score = 90 + min(10, (7 - days_of_supply) * 2)
            level = "critical"
        elif days_of_supply <= 14:
            score = 60 + (14 - days_of_supply) * 3
            level = "high"
        elif days_of_supply <= 30:
            score = 30 + (30 - days_of_supply)
            level = "medium"
        else:
            score = max(0, 30 - (days_of_supply - 30) * 0.5)
            level = "low"
        return {"score": min(100, max(0, score)), "level": level, "days_of_supply": days_of_supply}

    @staticmethod
    def _calculate_reorder_point(avg_daily: float, lead_time_days: int, seasonality: float) -> int:
        safety_days = 7
        return max(1, int(avg_daily * (lead_time_days + safety_days) * seasonality))

    @staticmethod
    def _calculate_eoq(avg_daily: float, lead_time_days: int, seasonality: float) -> int:
        demand_lead_time = avg_daily * lead_time_days * seasonality
        safety = avg_daily * 14 * seasonality
        return max(0, int(demand_lead_time + safety))

    @staticmethod
    def _calculate_prediction_confidence(historical_sales: list[dict[str, Any]], seasonality: float) -> float:
        confidence = 0.5
        if len(historical_sales) >= 90:
            confidence += 0.2
        elif len(historical_sales) >= 30:
            confidence += 0.1
        if 0.8 <= seasonality <= 1.2:
            confidence += 0.1
        elif seasonality > 1.5 or seasonality < 0.5:
            confidence -= 0.1
        return max(0.2, min(0.95, confidence))

    @staticmethod
    def _serialize_prediction(prediction: InventoryPrediction) -> dict[str, Any]:
        return {
            "id": str(prediction.id),
            "tenant_id": str(prediction.tenant_id),
            "recommendation_id": str(prediction.recommendation_id) if prediction.recommendation_id else None,
            "product_id": str(prediction.product_id) if prediction.product_id else None,
            "sku": prediction.sku,
            "prediction_horizon_days": prediction.prediction_horizon_days,
            "predicted_demand_short": prediction.predicted_demand_short,
            "predicted_demand_medium": prediction.predicted_demand_medium,
            "predicted_demand_long": prediction.predicted_demand_long,
            "confidence": prediction.confidence,
            "model_version": prediction.model_version,
            "input_features": prediction.input_features,
            "current_stock": prediction.current_stock,
            "stockout_risk_score": prediction.stockout_risk_score,
            "stockout_risk_level": prediction.stockout_risk_level,
            "reorder_point": prediction.reorder_point,
            "optimal_order_quantity": prediction.optimal_order_quantity,
            "marketplace": prediction.marketplace,
            "created_at": prediction.created_at.isoformat() if prediction.created_at else None,
        }
