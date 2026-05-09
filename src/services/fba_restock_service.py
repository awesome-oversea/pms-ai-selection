from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.infrastructure.fba_client import FBAClient, FBAClientError
from src.models.enums import RecommendationCategory, RecommendationPriority
from src.models.models import FBARestockSuggestion
from src.services.recommendation_pool_service import RecommendationPoolService

logger = get_logger(__name__)


class FBARestockService:
    """
    FBA补货建议服务。

    职责:
    - 基于库存水平、销售速度、采购提前期生成补货建议
    - 将补货建议提交至ERP FBA域建议池
    - 接收FBA域执行反馈
    - 计算补货紧急程度和安全库存
    """

    SAFETY_STOCK_FACTOR = 1.5
    DEFAULT_LEAD_TIME_DAYS = 30
    CRITICAL_DAYS_OF_SUPPLY = 14
    HIGH_URGENCY_DAYS_OF_SUPPLY = 30

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.pool_service = RecommendationPoolService(session, tenant_id=self.tenant_id, actor=self.actor)

    async def generate_restock_suggestion(
        self,
        *,
        product_id: str,
        sku: str | None = None,
        fnsku: str | None = None,
        asin: str | None = None,
        current_stock: int | None = None,
        inbound_quantity: int | None = None,
        daily_velocity: float | None = None,
        lead_time_days: int | None = None,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        effective_lead_time = lead_time_days or self.DEFAULT_LEAD_TIME_DAYS
        effective_velocity = daily_velocity or 0.0
        effective_stock = current_stock or 0
        effective_inbound = inbound_quantity or 0

        safety_stock = self._calculate_safety_stock(effective_velocity, effective_lead_time)
        days_of_supply = self._calculate_days_of_supply(effective_stock, effective_inbound, effective_velocity)
        suggested_quantity = self._calculate_restock_quantity(
            effective_stock, effective_inbound, effective_velocity, effective_lead_time, safety_stock
        )
        urgency = self._determine_urgency(days_of_supply)

        suggestion = FBARestockSuggestion(
            tenant_id=UUID(str(self.tenant_id)) if self.tenant_id else uuid4(),
            product_id=UUID(product_id) if product_id else None,
            sku=sku,
            fnsku=fnsku,
            asin=asin,
            current_stock=effective_stock,
            inbound_quantity=effective_inbound,
            daily_velocity=effective_velocity,
            days_of_supply=days_of_supply,
            suggested_quantity=suggested_quantity,
            urgency=urgency,
            lead_time_days=effective_lead_time,
            safety_stock=safety_stock,
            marketplace=marketplace,
            confidence=self._calculate_confidence(effective_velocity, effective_lead_time),
        )
        self.session.add(suggestion)
        await self.session.flush()

        priority = self._urgency_to_priority(urgency)
        pool_result = await self.pool_service.create_recommendation(
            category=RecommendationCategory.RESTOCK,
            target_domain="fba",
            title=f"FBA补货建议 - {sku or asin or product_id}",
            description=f"当前库存 {effective_stock}，可供货 {days_of_supply:.0f} 天，建议补货 {suggested_quantity} 件",
            priority=priority,
            score=self._calculate_restock_score(days_of_supply),
            confidence=suggestion.confidence,
            evidence_chain={
                "current_stock": effective_stock,
                "inbound_quantity": effective_inbound,
                "daily_velocity": effective_velocity,
                "days_of_supply": days_of_supply,
                "safety_stock": safety_stock,
                "lead_time_days": effective_lead_time,
            },
            data_sources=[{"type": "fba_inventory", "sku": sku, "asin": asin}],
            risk_flags=self._identify_restock_risks(days_of_supply, effective_velocity, effective_lead_time),
            payload={
                "suggestion_id": str(suggestion.id),
                "suggested_quantity": suggested_quantity,
                "urgency": urgency,
                "safety_stock": safety_stock,
            },
            source_product_id=UUID(product_id) if product_id else None,
        )

        suggestion.recommendation_id = UUID(pool_result["id"])
        await self.session.flush()

        return self._serialize_suggestion(suggestion, pool_result)

    async def batch_generate_restock_suggestions(
        self,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        results = []
        for item in items:
            try:
                result = await self.generate_restock_suggestion(**item)
                results.append(result)
            except Exception as e:
                logger.exception("批量生成补货建议失败: product_id=%s", item.get("product_id"))
                results.append({"product_id": item.get("product_id"), "error": str(e)})

        return {
            "total": len(items),
            "generated": len([r for r in results if "error" not in r]),
            "failed": len([r for r in results if "error" in r]),
            "items": results,
        }

    async def submit_to_fba_domain(
        self,
        suggestion_id: str,
        fba_client: FBAClient,
    ) -> dict[str, Any]:
        query = select(FBARestockSuggestion).where(FBARestockSuggestion.id == UUID(suggestion_id))
        if self.tenant_id:
            query = query.where(FBARestockSuggestion.tenant_id == UUID(str(self.tenant_id)))
        result = await self.session.execute(query)
        suggestion = result.scalar_one_or_none()
        if suggestion is None:
            raise ValueError(f"FBA补货建议不存在: {suggestion_id}")

        payload = {
            "suggestion_id": str(suggestion.id),
            "sku": suggestion.sku,
            "fnsku": suggestion.fnsku,
            "asin": suggestion.asin,
            "suggested_quantity": suggestion.suggested_quantity,
            "urgency": suggestion.urgency,
            "safety_stock": suggestion.safety_stock,
            "marketplace": suggestion.marketplace,
        }

        try:
            erp_result = await fba_client.submit_restock_suggestion(payload)
            suggestion.status = "submitted"
            await self.session.flush()

            if suggestion.recommendation_id:
                await self.pool_service.submit_to_erp(
                    str(suggestion.recommendation_id),
                    erp_ref_id=erp_result.get("suggestion_id"),
                )

            return {"suggestion_id": str(suggestion.id), "status": "submitted", "erp_result": erp_result}
        except FBAClientError as e:
            suggestion.status = "submission_failed"
            await self.session.flush()
            raise ValueError(f"提交FBA域失败: {e}") from e

    async def receive_fba_feedback(
        self,
        suggestion_id: str,
        *,
        status: str,
        execution_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = select(FBARestockSuggestion).where(FBARestockSuggestion.id == UUID(suggestion_id))
        if self.tenant_id:
            query = query.where(FBARestockSuggestion.tenant_id == UUID(str(self.tenant_id)))
        result = await self.session.execute(query)
        suggestion = result.scalar_one_or_none()
        if suggestion is None:
            raise ValueError(f"FBA补货建议不存在: {suggestion_id}")

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
        urgency: str | None = None,
        status: str | None = None,
        sku: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = select(FBARestockSuggestion)
        count_query = select(func.count()).select_from(FBARestockSuggestion)

        if self.tenant_id:
            query = query.where(FBARestockSuggestion.tenant_id == UUID(str(self.tenant_id)))
            count_query = count_query.where(FBARestockSuggestion.tenant_id == UUID(str(self.tenant_id)))
        if urgency:
            query = query.where(FBARestockSuggestion.urgency == urgency)
            count_query = count_query.where(FBARestockSuggestion.urgency == urgency)
        if status:
            query = query.where(FBARestockSuggestion.status == status)
            count_query = count_query.where(FBARestockSuggestion.status == status)
        if sku:
            query = query.where(FBARestockSuggestion.sku == sku)
            count_query = count_query.where(FBARestockSuggestion.sku == sku)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(FBARestockSuggestion.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        suggestions = result.scalars().all()

        return {
            "total": total,
            "items": [self._serialize_suggestion(s) for s in suggestions],
            "limit": limit,
            "offset": offset,
        }

    def _calculate_safety_stock(self, daily_velocity: float, lead_time_days: int) -> int:
        return max(1, int(daily_velocity * lead_time_days * self.SAFETY_STOCK_FACTOR / 30))

    def _calculate_days_of_supply(self, current_stock: int, inbound: int, daily_velocity: float) -> float:
        if daily_velocity <= 0:
            return 999.0
        available = current_stock + inbound
        return available / daily_velocity

    def _calculate_restock_quantity(
        self,
        current_stock: int,
        inbound: int,
        daily_velocity: float,
        lead_time_days: int,
        safety_stock: int,
    ) -> int:
        demand_during_lead_time = int(daily_velocity * lead_time_days)
        target_stock = demand_during_lead_time + safety_stock
        current_available = current_stock + inbound
        needed = target_stock - current_available
        return max(0, needed)

    def _determine_urgency(self, days_of_supply: float) -> str:
        if days_of_supply <= self.CRITICAL_DAYS_OF_SUPPLY:
            return "critical"
        if days_of_supply <= self.HIGH_URGENCY_DAYS_OF_SUPPLY:
            return "high"
        if days_of_supply <= 60:
            return "normal"
        return "low"

    def _urgency_to_priority(self, urgency: str) -> RecommendationPriority:
        mapping = {
            "critical": RecommendationPriority.CRITICAL,
            "high": RecommendationPriority.HIGH,
            "normal": RecommendationPriority.MEDIUM,
            "low": RecommendationPriority.LOW,
        }
        return mapping.get(urgency, RecommendationPriority.MEDIUM)

    @staticmethod
    def _calculate_restock_score(days_of_supply: float) -> float:
        if days_of_supply <= 7:
            return 95.0
        if days_of_supply <= 14:
            return 85.0
        if days_of_supply <= 30:
            return 70.0
        if days_of_supply <= 60:
            return 50.0
        return 30.0

    @staticmethod
    def _calculate_confidence(daily_velocity: float, lead_time_days: int) -> float:
        if daily_velocity <= 0:
            return 0.3
        if lead_time_days > 60:
            return 0.5
        if daily_velocity < 1:
            return 0.6
        return 0.8

    @staticmethod
    def _identify_restock_risks(days_of_supply: float, daily_velocity: float, lead_time_days: int) -> list[dict[str, Any]]:
        risks = []
        if days_of_supply <= 7:
            risks.append({"type": "stockout_risk", "detail": "库存即将耗尽", "severity": "critical"})
        if daily_velocity <= 0:
            risks.append({"type": "velocity_risk", "detail": "无销售速度数据", "severity": "high"})
        if lead_time_days > 45:
            risks.append({"type": "lead_time_risk", "detail": f"采购提前期过长({lead_time_days}天)", "severity": "medium"})
        return risks

    @staticmethod
    def _serialize_suggestion(suggestion: FBARestockSuggestion, pool_data: dict[str, Any] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": str(suggestion.id),
            "tenant_id": str(suggestion.tenant_id),
            "recommendation_id": str(suggestion.recommendation_id) if suggestion.recommendation_id else None,
            "product_id": str(suggestion.product_id) if suggestion.product_id else None,
            "sku": suggestion.sku,
            "fnsku": suggestion.fnsku,
            "asin": suggestion.asin,
            "current_stock": suggestion.current_stock,
            "inbound_quantity": suggestion.inbound_quantity,
            "daily_velocity": suggestion.daily_velocity,
            "days_of_supply": suggestion.days_of_supply,
            "suggested_quantity": suggestion.suggested_quantity,
            "urgency": suggestion.urgency,
            "lead_time_days": suggestion.lead_time_days,
            "safety_stock": suggestion.safety_stock,
            "marketplace": suggestion.marketplace,
            "status": suggestion.status,
            "confidence": suggestion.confidence,
            "created_at": suggestion.created_at.isoformat() if suggestion.created_at else None,
        }
        if pool_data:
            result["recommendation_pool"] = pool_data
        return result
