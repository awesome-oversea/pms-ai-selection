from __future__ import annotations

from typing import Any

from src.core.logging import get_logger
from src.core.pms_governance import AuditContext
from src.infrastructure.ads_client import ADSClient, ADSClientError
from src.infrastructure.database import get_async_session_factory
from src.services.ads_optimization_service import AdsOptimizationService

logger = get_logger(__name__)


class AdsDomainService:
    """
    ADS域服务。

    职责:
    - 封装ADS域ERP客户端调用
    - 协调广告优化建议的创建、审批、提交全流程
    - 管理ADS域数据同步
    """

    def __init__(self, ads_client: ADSClient, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.ads_client = ads_client
        self.tenant_id = tenant_id
        self.actor = actor or {}

    async def submit_bid_adjustment(
        self,
        *,
        product_id: str,
        campaign_id: str,
        current_metrics: dict[str, Any],
        suggested_bid: float | None = None,
        confidence: float | None = None,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            try:
                ads_service = AdsOptimizationService(session, tenant_id=self.tenant_id, actor=self.actor)
                suggestion = await ads_service.generate_bid_adjustment_suggestion(
                    product_id=product_id,
                    campaign_id=campaign_id,
                    current_metrics=current_metrics,
                    suggested_bid=suggested_bid,
                    confidence=confidence,
                    marketplace=marketplace,
                )
                await session.commit()
                return suggestion
            except Exception:
                await session.rollback()
                raise

    async def submit_keyword_suggestion(
        self,
        *,
        product_id: str,
        campaign_id: str,
        current_keywords: list[str],
        suggested_keywords: list[dict[str, Any]],
        confidence: float | None = None,
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            try:
                ads_service = AdsOptimizationService(session, tenant_id=self.tenant_id, actor=self.actor)
                suggestion = await ads_service.generate_keyword_suggestion(
                    product_id=product_id,
                    campaign_id=campaign_id,
                    current_keywords=current_keywords,
                    suggested_keywords=suggested_keywords,
                    confidence=confidence,
                    marketplace=marketplace,
                )
                await session.commit()
                return suggestion
            except Exception:
                await session.rollback()
                raise

    async def submit_budget_allocation(
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
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            try:
                ads_service = AdsOptimizationService(session, tenant_id=self.tenant_id, actor=self.actor)
                suggestion = await ads_service.generate_budget_allocation_suggestion(
                    product_id=product_id,
                    campaign_id=campaign_id,
                    current_budget=current_budget,
                    suggested_budget=suggested_budget,
                    reasoning=reasoning,
                    confidence=confidence,
                    marketplace=marketplace,
                )
                await session.commit()
                return suggestion
            except Exception:
                await session.rollback()
                raise

    async def push_suggestion_to_erp(self, suggestion_id: str) -> dict[str, Any]:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            try:
                ads_service = AdsOptimizationService(session, tenant_id=self.tenant_id, actor=self.actor)
                result = await ads_service.submit_to_ads_domain(suggestion_id, self.ads_client)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    async def get_campaign_metrics(
        self,
        campaign_id: str,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.ads_client.get_campaign_metrics(campaign_id, audit_context=audit_context)
        except ADSClientError as e:
            logger.error("获取广告活动指标失败: campaign_id=%s error=%s", campaign_id, e)
            raise

    async def health_check(self) -> dict[str, Any]:
        try:
            return await self.ads_client.test_connection()
        except ADSClientError as e:
            return {"status": "unhealthy", "error": str(e), "error_code": e.error_code}
