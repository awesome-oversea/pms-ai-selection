from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.enums import RecommendationCategory, RecommendationPriority
from src.models.models import RiskAssessment
from src.services.recommendation_pool_service import RecommendationPoolService

logger = get_logger(__name__)


class RiskScoringService:
    """
    风控评分服务。

    职责:
    - 对订单/供应/库存/合规/定价风险进行AI评分
    - 生成风控建议并推送至ERP对应域
    - 跟踪风险状态变化
    - 提供风险缓解建议
    """

    RISK_THRESHOLDS = {
        "low": (0, 30),
        "medium": (30, 60),
        "high": (60, 80),
        "critical": (80, 100),
    }

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.pool_service = RecommendationPoolService(session, tenant_id=self.tenant_id, actor=self.actor)

    async def assess_order_risk(
        self,
        *,
        target_id: str,
        order_data: dict[str, Any],
        target_domain: str = "oms",
    ) -> dict[str, Any]:
        risk_score = self._score_order_risk(order_data)
        risk_level = self._determine_risk_level(risk_score)
        risk_factors = self._identify_order_risk_factors(order_data, risk_score)
        mitigations = self._suggest_order_risk_mitigations(risk_factors)

        return await self._create_assessment(
            risk_type="order_risk",
            target_domain=target_domain,
            target_id=target_id,
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=risk_factors,
            mitigations=mitigations,
            evidence=order_data,
        )

    async def assess_supply_risk(
        self,
        *,
        target_id: str,
        supply_data: dict[str, Any],
        target_domain: str = "scm",
    ) -> dict[str, Any]:
        risk_score = self._score_supply_risk(supply_data)
        risk_level = self._determine_risk_level(risk_score)
        risk_factors = self._identify_supply_risk_factors(supply_data, risk_score)
        mitigations = self._suggest_supply_risk_mitigations(risk_factors)

        return await self._create_assessment(
            risk_type="supply_risk",
            target_domain=target_domain,
            target_id=target_id,
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=risk_factors,
            mitigations=mitigations,
            evidence=supply_data,
        )

    async def assess_inventory_risk(
        self,
        *,
        target_id: str,
        inventory_data: dict[str, Any],
        target_domain: str = "wms",
    ) -> dict[str, Any]:
        risk_score = self._score_inventory_risk(inventory_data)
        risk_level = self._determine_risk_level(risk_score)
        risk_factors = self._identify_inventory_risk_factors(inventory_data, risk_score)
        mitigations = self._suggest_inventory_risk_mitigations(risk_factors)

        return await self._create_assessment(
            risk_type="inventory_risk",
            target_domain=target_domain,
            target_id=target_id,
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=risk_factors,
            mitigations=mitigations,
            evidence=inventory_data,
        )

    async def assess_pricing_risk(
        self,
        *,
        target_id: str,
        pricing_data: dict[str, Any],
        target_domain: str = "som",
    ) -> dict[str, Any]:
        risk_score = self._score_pricing_risk(pricing_data)
        risk_level = self._determine_risk_level(risk_score)
        risk_factors = self._identify_pricing_risk_factors(pricing_data, risk_score)
        mitigations = self._suggest_pricing_risk_mitigations(risk_factors)

        return await self._create_assessment(
            risk_type="pricing_risk",
            target_domain=target_domain,
            target_id=target_id,
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=risk_factors,
            mitigations=mitigations,
            evidence=pricing_data,
        )

    async def list_assessments(
        self,
        *,
        risk_type: str | None = None,
        risk_level: str | None = None,
        target_domain: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = select(RiskAssessment)
        count_query = select(func.count()).select_from(RiskAssessment)

        if self.tenant_id:
            query = query.where(RiskAssessment.tenant_id == UUID(str(self.tenant_id)))
            count_query = count_query.where(RiskAssessment.tenant_id == UUID(str(self.tenant_id)))
        if risk_type:
            query = query.where(RiskAssessment.risk_type == risk_type)
            count_query = count_query.where(RiskAssessment.risk_type == risk_type)
        if risk_level:
            query = query.where(RiskAssessment.risk_level == risk_level)
            count_query = count_query.where(RiskAssessment.risk_level == risk_level)
        if target_domain:
            query = query.where(RiskAssessment.target_domain == target_domain)
            count_query = count_query.where(RiskAssessment.target_domain == target_domain)
        if status:
            query = query.where(RiskAssessment.status == status)
            count_query = count_query.where(RiskAssessment.status == status)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(RiskAssessment.risk_score.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        assessments = result.scalars().all()

        return {
            "total": total,
            "items": [self._serialize_assessment(a) for a in assessments],
            "limit": limit,
            "offset": offset,
        }

    async def acknowledge_risk(self, assessment_id: str, *, notes: str | None = None) -> dict[str, Any]:
        query = select(RiskAssessment).where(RiskAssessment.id == UUID(assessment_id))
        if self.tenant_id:
            query = query.where(RiskAssessment.tenant_id == UUID(str(self.tenant_id)))
        result = await self.session.execute(query)
        assessment = result.scalar_one_or_none()
        if assessment is None:
            raise ValueError(f"风控评估不存在: {assessment_id}")

        assessment.status = "acknowledged"
        await self.session.flush()
        return self._serialize_assessment(assessment)

    async def _create_assessment(
        self,
        *,
        risk_type: str,
        target_domain: str,
        target_id: str,
        risk_score: float,
        risk_level: str,
        risk_factors: list[dict[str, Any]],
        mitigations: list[dict[str, Any]],
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        assessment = RiskAssessment(
            tenant_id=UUID(str(self.tenant_id)) if self.tenant_id else uuid4(),
            risk_type=risk_type,
            target_domain=target_domain,
            target_id=target_id,
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=risk_factors,
            mitigation_suggestions=mitigations,
            evidence=evidence,
        )
        self.session.add(assessment)
        await self.session.flush()

        if risk_level in {"high", "critical"}:
            priority = RecommendationPriority.CRITICAL if risk_level == "critical" else RecommendationPriority.HIGH
            pool_result = await self.pool_service.create_recommendation(
                category=RecommendationCategory.RISK_ALERT,
                target_domain=target_domain,
                title=f"风险预警 - {risk_type} - {target_id}",
                description=f"风险等级: {risk_level}, 评分: {risk_score:.1f}",
                priority=priority,
                score=risk_score,
                evidence_chain=evidence,
                risk_flags=risk_factors,
                payload={"assessment_id": str(assessment.id), "mitigations": mitigations},
            )
            assessment.recommendation_id = UUID(pool_result["id"])
            await self.session.flush()

        return self._serialize_assessment(assessment)

    def _determine_risk_level(self, score: float) -> str:
        for level, (low, high) in self.RISK_THRESHOLDS.items():
            if low <= score < high:
                return level
        return "critical"

    @staticmethod
    def _score_order_risk(data: dict[str, Any]) -> float:
        score = 0.0
        if data.get("return_rate", 0) > 0.15:
            score += 30
        if data.get("chargeback_rate", 0) > 0.05:
            score += 25
        if data.get("late_shipment_rate", 0) > 0.1:
            score += 20
        if data.get("order_defect_rate", 0) > 0.05:
            score += 25
        return min(100, score)

    @staticmethod
    def _score_supply_risk(data: dict[str, Any]) -> float:
        score = 0.0
        if data.get("supplier_reliability", 1.0) < 0.7:
            score += 30
        if data.get("lead_time_variability", 0) > 0.3:
            score += 25
        if data.get("single_source", False):
            score += 20
        if data.get("quality_rejection_rate", 0) > 0.05:
            score += 25
        return min(100, score)

    @staticmethod
    def _score_inventory_risk(data: dict[str, Any]) -> float:
        score = 0.0
        days_of_supply = data.get("days_of_supply", 999)
        if days_of_supply <= 7:
            score += 40
        elif days_of_supply <= 14:
            score += 30
        elif days_of_supply <= 30:
            score += 15
        if data.get("stockout_count_30d", 0) > 3:
            score += 30
        if data.get("overstock_ratio", 0) > 0.5:
            score += 20
        return min(100, score)

    @staticmethod
    def _score_pricing_risk(data: dict[str, Any]) -> float:
        score = 0.0
        margin = data.get("margin_rate", 0.3)
        if margin < 0.05:
            score += 40
        elif margin < 0.1:
            score += 25
        if data.get("price_competitiveness", 1.0) > 1.3:
            score += 30
        if data.get("price_volatility_30d", 0) > 0.2:
            score += 20
        return min(100, score)

    @staticmethod
    def _identify_order_risk_factors(data: dict[str, Any], score: float) -> list[dict[str, Any]]:
        factors = []
        if data.get("return_rate", 0) > 0.15:
            factors.append({"factor": "high_return_rate", "value": data["return_rate"], "threshold": 0.15})
        if data.get("chargeback_rate", 0) > 0.05:
            factors.append({"factor": "high_chargeback_rate", "value": data["chargeback_rate"], "threshold": 0.05})
        if data.get("order_defect_rate", 0) > 0.05:
            factors.append({"factor": "high_defect_rate", "value": data["order_defect_rate"], "threshold": 0.05})
        return factors

    @staticmethod
    def _identify_supply_risk_factors(data: dict[str, Any], score: float) -> list[dict[str, Any]]:
        factors = []
        if data.get("supplier_reliability", 1.0) < 0.7:
            factors.append({"factor": "low_supplier_reliability", "value": data["supplier_reliability"], "threshold": 0.7})
        if data.get("single_source", False):
            factors.append({"factor": "single_source_dependency", "value": True})
        return factors

    @staticmethod
    def _identify_inventory_risk_factors(data: dict[str, Any], score: float) -> list[dict[str, Any]]:
        factors = []
        days = data.get("days_of_supply", 999)
        if days <= 14:
            factors.append({"factor": "low_stock", "value": days, "threshold": 14})
        if data.get("stockout_count_30d", 0) > 3:
            factors.append({"factor": "frequent_stockout", "value": data["stockout_count_30d"], "threshold": 3})
        return factors

    @staticmethod
    def _identify_pricing_risk_factors(data: dict[str, Any], score: float) -> list[dict[str, Any]]:
        factors = []
        margin = data.get("margin_rate", 0.3)
        if margin < 0.1:
            factors.append({"factor": "low_margin", "value": margin, "threshold": 0.1})
        return factors

    @staticmethod
    def _suggest_order_risk_mitigations(factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mitigations = []
        for f in factors:
            if f["factor"] == "high_return_rate":
                mitigations.append({"action": "review_product_quality", "priority": "high", "detail": "审查产品质量和描述准确性"})
            if f["factor"] == "high_chargeback_rate":
                mitigations.append({"action": "investigate_fraud", "priority": "critical", "detail": "调查欺诈行为并加强风控"})
        return mitigations

    @staticmethod
    def _suggest_supply_risk_mitigations(factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mitigations = []
        for f in factors:
            if f["factor"] == "single_source_dependency":
                mitigations.append({"action": "diversify_suppliers", "priority": "high", "detail": "开发备选供应商"})
            if f["factor"] == "low_supplier_reliability":
                mitigations.append({"action": "evaluate_supplier", "priority": "medium", "detail": "评估供应商并制定改善计划"})
        return mitigations

    @staticmethod
    def _suggest_inventory_risk_mitigations(factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mitigations = []
        for f in factors:
            if f["factor"] == "low_stock":
                mitigations.append({"action": "urgent_restock", "priority": "critical", "detail": "紧急补货"})
            if f["factor"] == "frequent_stockout":
                mitigations.append({"action": "adjust_safety_stock", "priority": "high", "detail": "调整安全库存水平"})
        return mitigations

    @staticmethod
    def _suggest_pricing_risk_mitigations(factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mitigations = []
        for f in factors:
            if f["factor"] == "low_margin":
                mitigations.append({"action": "review_pricing_strategy", "priority": "high", "detail": "审查定价策略并优化成本"})
        return mitigations

    @staticmethod
    def _serialize_assessment(assessment: RiskAssessment) -> dict[str, Any]:
        return {
            "id": str(assessment.id),
            "tenant_id": str(assessment.tenant_id),
            "recommendation_id": str(assessment.recommendation_id) if assessment.recommendation_id else None,
            "risk_type": assessment.risk_type,
            "target_domain": assessment.target_domain,
            "target_id": assessment.target_id,
            "risk_score": assessment.risk_score,
            "risk_level": assessment.risk_level,
            "risk_factors": assessment.risk_factors,
            "mitigation_suggestions": assessment.mitigation_suggestions,
            "evidence": assessment.evidence,
            "status": assessment.status,
            "created_at": assessment.created_at.isoformat() if assessment.created_at else None,
        }
