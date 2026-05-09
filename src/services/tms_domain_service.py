from __future__ import annotations

from typing import Any

from src.core.logging import get_logger
from src.core.pms_governance import AuditContext
from src.infrastructure.database import get_async_session_factory
from src.infrastructure.tms_client import TMSClient, TMSClientError
from src.models.enums import RecommendationCategory, RecommendationPriority
from src.services.recommendation_pool_service import RecommendationPoolService

logger = get_logger(__name__)


class TmsDomainService:
    """
    TMS域服务。

    职责:
    - 封装TMS域ERP客户端调用
    - 生成物流风险建议并提交至ERP
    - 管理物流数据查询
    """

    def __init__(self, tms_client: TMSClient, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.tms_client = tms_client
        self.tenant_id = tenant_id
        self.actor = actor or {}

    async def submit_logistics_risk(
        self,
        *,
        shipment_id: str,
        risk_type: str,
        risk_description: str,
        risk_score: float,
        risk_level: str,
        mitigation: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            try:
                pool_service = RecommendationPoolService(session, tenant_id=self.tenant_id, actor=self.actor)
                priority = RecommendationPriority.CRITICAL if risk_level == "critical" else (
                    RecommendationPriority.HIGH if risk_level == "high" else RecommendationPriority.MEDIUM
                )
                result = await pool_service.create_recommendation(
                    category=RecommendationCategory.LOGISTICS_RISK,
                    target_domain="tms",
                    title=f"物流风险预警 - {risk_type} - {shipment_id}",
                    description=risk_description,
                    priority=priority,
                    score=risk_score,
                    evidence_chain=evidence or {},
                    risk_flags=[{"type": risk_type, "level": risk_level, "score": risk_score}],
                    payload={
                        "shipment_id": shipment_id,
                        "risk_type": risk_type,
                        "mitigation": mitigation,
                    },
                )
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    async def get_shipping_rates(
        self,
        origin: str,
        destination: str,
        weight_kg: float | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.tms_client.get_shipping_rates(
                origin=origin,
                destination=destination,
                weight_kg=weight_kg,
                audit_context=audit_context,
            )
        except TMSClientError as e:
            logger.error("获取运费报价失败: origin=%s destination=%s error=%s", origin, destination, e)
            raise

    async def push_suggestion_to_erp(
        self,
        payload: dict[str, Any],
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.tms_client.submit_logistics_risk_suggestion(payload, audit_context=audit_context)
        except TMSClientError as e:
            logger.error("提交物流风险建议至ERP失败: error=%s", e)
            raise

    async def health_check(self) -> dict[str, Any]:
        try:
            return await self.tms_client.test_connection()
        except TMSClientError as e:
            return {"status": "unhealthy", "error": str(e), "error_code": e.error_code}
