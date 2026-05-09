from __future__ import annotations

from typing import Any

from src.core.logging import get_logger
from src.infrastructure.dashboard_client import DashboardClient, DashboardClientError
from src.infrastructure.database import get_async_session_factory
from src.models.enums import RecommendationCategory, RecommendationPriority
from src.services.recommendation_pool_service import RecommendationPoolService

logger = get_logger(__name__)


class DashboardDomainService:
    """
    Dashboard域服务。

    职责:
    - 封装Dashboard域ERP客户端调用
    - 推送洞察卡片至ERP Dashboard
    - 推送风险预警至ERP Dashboard
    - 管理Dashboard数据展示
    """

    def __init__(self, dashboard_client: DashboardClient, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.dashboard_client = dashboard_client
        self.tenant_id = tenant_id
        self.actor = actor or {}

    async def push_insight_card(
        self,
        *,
        card_type: str,
        title: str,
        summary: str,
        detail: dict[str, Any] | None = None,
        priority: str = "info",
        source_category: RecommendationCategory | None = None,
    ) -> dict[str, Any]:
        payload = {
            "card_type": card_type,
            "title": title,
            "summary": summary,
            "detail": detail or {},
            "priority": priority,
            "tenant_id": self.tenant_id,
        }
        if source_category:
            payload["source_category"] = source_category.value

        try:
            result = await self.dashboard_client.push_insight_card(payload)
            logger.info("洞察卡片已推送: card_type=%s title=%s", card_type, title)
            return result
        except DashboardClientError as e:
            logger.error("推送洞察卡片失败: card_type=%s error=%s", card_type, e)
            raise

    async def push_risk_alert(
        self,
        *,
        alert_type: str,
        title: str,
        description: str,
        risk_level: str,
        risk_score: float,
        affected_entities: list[dict[str, Any]] | None = None,
        mitigations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            try:
                pool_service = RecommendationPoolService(session, tenant_id=self.tenant_id, actor=self.actor)
                priority = RecommendationPriority.CRITICAL if risk_level == "critical" else (
                    RecommendationPriority.HIGH if risk_level == "high" else RecommendationPriority.MEDIUM
                )
                rec_result = await pool_service.create_recommendation(
                    category=RecommendationCategory.RISK_ALERT,
                    target_domain="dashboard",
                    title=title,
                    description=description,
                    priority=priority,
                    score=risk_score,
                    risk_flags=[{"type": alert_type, "level": risk_level}],
                    payload={
                        "alert_type": alert_type,
                        "affected_entities": affected_entities,
                        "mitigations": mitigations,
                    },
                )

                alert_payload = {
                    "alert_type": alert_type,
                    "title": title,
                    "description": description,
                    "risk_level": risk_level,
                    "risk_score": risk_score,
                    "affected_entities": affected_entities or [],
                    "mitigations": mitigations or [],
                    "recommendation_id": rec_result.get("id"),
                    "tenant_id": self.tenant_id,
                }

                erp_result = await self.dashboard_client.push_risk_alert(alert_payload)

                await session.commit()
                return {"recommendation": rec_result, "erp_result": erp_result}
            except Exception:
                await session.rollback()
                raise

    async def push_selection_insight(
        self,
        *,
        task_id: str,
        product_name: str,
        score: float,
        reasoning: str,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        return await self.push_insight_card(
            card_type="selection_insight",
            title=f"选品洞察 - {product_name}",
            summary=reasoning,
            detail={"task_id": task_id, "score": score, "marketplace": marketplace},
            priority="info",
            source_category=RecommendationCategory.SELECTION,
        )

    async def push_pricing_insight(
        self,
        *,
        product_id: str,
        current_price: float,
        suggested_price: float,
        margin_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.push_insight_card(
            card_type="pricing_insight",
            title=f"定价洞察 - 产品 {product_id}",
            summary=f"建议从 ¥{current_price:.2f} 调整为 ¥{suggested_price:.2f}",
            detail={"product_id": product_id, "margin_analysis": margin_analysis},
            priority="warning" if suggested_price < current_price else "info",
            source_category=RecommendationCategory.PRICING,
        )

    async def health_check(self) -> dict[str, Any]:
        try:
            return await self.dashboard_client.test_connection()
        except DashboardClientError as e:
            return {"status": "unhealthy", "error": str(e), "error_code": e.error_code}
