from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from src.core.auth import get_current_user
from src.infrastructure.ads_client import ADSClient
from src.infrastructure.dashboard_client import DashboardClient
from src.infrastructure.database import get_async_session_factory
from src.infrastructure.fba_client import FBAClient
from src.infrastructure.iam_client import IAMClient, IAMClientError
from src.infrastructure.sys_client import SYSClient
from src.infrastructure.tms_client import TMSClient, TMSClientError
from src.services.ads_optimization_service import AdsOptimizationService
from src.services.ai_feature_toggle_service import AIFeatureToggleService
from src.services.dashboard_domain_service import DashboardDomainService
from src.services.erp_feedback_consumer import handle_erp_domain_event, handle_erp_feedback_event
from src.services.fba_restock_service import FBARestockService
from src.services.inventory_prediction_service import InventoryPredictionService
from src.services.pricing_suggestion_service import PricingSuggestionService
from src.services.recommendation_pool_service import RecommendationPoolService
from src.services.risk_scoring_service import RiskScoringService
from src.services.sentiment_analysis_service import SentimentAnalysisService
from src.services.tms_domain_service import TmsDomainService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/erp-domains", tags=["ERP域集成"])


class AdsConfigRequest(BaseModel):
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/health")
    outbound_path: str = Field(default="/recommendations")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class AdsBidAdjustmentRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    campaign_id: str = Field(..., min_length=1)
    current_metrics: dict[str, Any] = Field(default_factory=dict)
    suggested_bid: float | None = None
    confidence: float | None = None
    marketplace: str | None = None


class AdsKeywordRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    campaign_id: str = Field(..., min_length=1)
    current_keywords: list[str] = Field(default_factory=list)
    suggested_keywords: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    marketplace: str | None = None


class AdsBudgetRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    campaign_id: str = Field(..., min_length=1)
    current_budget: float = Field(..., ge=0)
    suggested_budget: float = Field(..., ge=0)
    reasoning: str | None = None
    confidence: float | None = None
    marketplace: str | None = None


class FbaConfigRequest(BaseModel):
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/health")
    outbound_path: str = Field(default="/recommendations")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class FbaRestockRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    sku: str | None = None
    fnsku: str | None = None
    asin: str | None = None
    current_stock: int | None = None
    inbound_quantity: int | None = None
    daily_velocity: float | None = None
    lead_time_days: int | None = None
    marketplace: str | None = None


class FbaBatchRestockRequest(BaseModel):
    items: list[dict[str, Any]] = Field(..., min_length=1)


class TmsConfigRequest(BaseModel):
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/health")
    outbound_path: str = Field(default="/recommendations")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class TmsLogisticsRiskRequest(BaseModel):
    shipment_id: str = Field(..., min_length=1)
    risk_type: str = Field(..., min_length=1)
    risk_description: str = Field(..., min_length=1)
    risk_score: float = Field(..., ge=0, le=100)
    risk_level: str = Field(default="medium")
    mitigation: str | None = None
    evidence: dict[str, Any] | None = None


class TmsShippingRateRequest(BaseModel):
    origin: str = Field(..., min_length=1)
    destination: str = Field(..., min_length=1)
    weight_kg: float | None = None


class DashboardConfigRequest(BaseModel):
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/health")
    outbound_path: str = Field(default="/insight-cards")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class DashboardInsightCardRequest(BaseModel):
    card_type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    detail: dict[str, Any] | None = None
    priority: str = Field(default="info")


class DashboardRiskAlertRequest(BaseModel):
    alert_type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    risk_level: str = Field(default="medium")
    risk_score: float = Field(..., ge=0, le=100)
    affected_entities: list[dict[str, Any]] | None = None
    mitigations: list[dict[str, Any]] | None = None


class IamConfigRequest(BaseModel):
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/health")
    outbound_path: str = Field(default="/access-requests")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class IamPermissionScopeRequest(BaseModel):
    actor_id: str = Field(..., min_length=1)
    scope_type: str = Field(default="tenant")


class SysConfigRequest(BaseModel):
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/health")
    outbound_path: str = Field(default="/config-change-requests")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class SysFeatureConfigRequest(BaseModel):
    feature_key: str = Field(..., min_length=1)


class SysConfigChangeRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class ErpFeedbackEventRequest(BaseModel):
    event_type: str = Field(..., min_length=1)
    aggregate_id: str = Field(..., min_length=1)
    tenant_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ErpDomainEventRequest(BaseModel):
    event_type: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)
    tenant_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class CreateSuggestionRequest(BaseModel):
    category: str = Field(..., min_length=1)
    target_domain: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = None
    priority: str | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_chain: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None


def _extract_actor(user: Any) -> dict[str, Any]:
    if user is None:
        return {}
    if isinstance(user, dict):
        return user
    actor: dict[str, Any] = {}
    for attr in ("tenant_id", "user_id", "sub", "username", "roles", "scope", "actor_type", "trace_id", "request_id", "marketplace", "store_id", "warehouse_id", "supplier_id", "category_id", "channel"):
        val = getattr(user, attr, None)
        if val is not None:
            actor[attr] = str(val) if not isinstance(val, (list, dict)) else val
    return actor


class RecommendationListRequest(BaseModel):
    category: str | None = None
    target_domain: str | None = None
    execution_state: str | None = None
    priority: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class RiskAssessmentRequest(BaseModel):
    risk_type: str = Field(..., min_length=1)
    target_id: str = Field(..., min_length=1)
    target_domain: str = Field(default="oms")
    data: dict[str, Any] = Field(default_factory=dict)


class PricingRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    cost_data: dict[str, Any] = Field(default_factory=dict)
    market_data: dict[str, Any] = Field(default_factory=dict)
    target_margin: float | None = None
    marketplace: str | None = None
    pricing_type: str = Field(default="new_product")


class PricingAdjustmentRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    current_price: float = Field(..., ge=0)
    cost_data: dict[str, Any] = Field(default_factory=dict)
    market_data: dict[str, Any] = Field(default_factory=dict)
    sales_data: dict[str, Any] = Field(default_factory=dict)
    target_margin: float | None = None
    marketplace: str | None = None


class FeatureToggleRequest(BaseModel):
    feature_key: str = Field(..., min_length=1)
    is_enabled: bool | None = None
    rollout_percentage: int | None = None
    config_overrides: dict[str, Any] | None = None
    description: str | None = None
    tenant_id: str | None = None


class InventoryPredictionRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    sku: str | None = None
    current_stock: int | None = None
    historical_sales: list[dict[str, Any]] | None = None
    seasonality_factor: float | None = None
    promotion_calendar: list[dict[str, Any]] | None = None
    lead_time_days: int | None = None
    marketplace: str | None = None


class SentimentAnalysisRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    reviews: list[dict[str, Any]] = Field(default_factory=list)
    marketplace: str | None = None


def _build_ads_client(config: AdsConfigRequest) -> ADSClient:
    return ADSClient(
        api_endpoint=config.api_endpoint,
        api_key=config.api_key,
        secret_key=config.secret_key,
        inbound_path=config.inbound_path,
        outbound_path=config.outbound_path,
        timeout_seconds=config.timeout_seconds,
    )


def _build_fba_client(config: FbaConfigRequest) -> FBAClient:
    return FBAClient(
        api_endpoint=config.api_endpoint,
        api_key=config.api_key,
        secret_key=config.secret_key,
        inbound_path=config.inbound_path,
        outbound_path=config.outbound_path,
        timeout_seconds=config.timeout_seconds,
    )


def _build_tms_client(config: TmsConfigRequest) -> TMSClient:
    return TMSClient(
        api_endpoint=config.api_endpoint,
        api_key=config.api_key,
        secret_key=config.secret_key,
        inbound_path=config.inbound_path,
        outbound_path=config.outbound_path,
        timeout_seconds=config.timeout_seconds,
    )


def _build_dashboard_client(config: DashboardConfigRequest) -> DashboardClient:
    return DashboardClient(
        api_endpoint=config.api_endpoint,
        api_key=config.api_key,
        secret_key=config.secret_key,
        inbound_path=config.inbound_path,
        outbound_path=config.outbound_path,
        timeout_seconds=config.timeout_seconds,
    )


def _build_iam_client(config: IamConfigRequest) -> IAMClient:
    return IAMClient(
        api_endpoint=config.api_endpoint,
        api_key=config.api_key,
        secret_key=config.secret_key,
        inbound_path=config.inbound_path,
        outbound_path=config.outbound_path,
        timeout_seconds=config.timeout_seconds,
    )


def _build_sys_client(config: SysConfigRequest) -> SYSClient:
    return SYSClient(
        api_endpoint=config.api_endpoint,
        api_key=config.api_key,
        secret_key=config.secret_key,
        inbound_path=config.inbound_path,
        outbound_path=config.outbound_path,
        timeout_seconds=config.timeout_seconds,
    )


# ─── ADS 域端点 ───

@router.post("/ads/config", summary="配置ADS域连接")
async def config_ads(request: AdsConfigRequest, user: Any = Depends(get_current_user)):
    client = _build_ads_client(request)
    result = await client.test_connection()
    return {"domain": "ads", "connection": result}


@router.post("/ads/bid-adjustment", summary="生成竞价调整建议")
async def ads_bid_adjustment(request: AdsBidAdjustmentRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = AdsOptimizationService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.generate_bid_adjustment_suggestion(
            product_id=request.product_id,
            campaign_id=request.campaign_id,
            current_metrics=request.current_metrics,
            suggested_bid=request.suggested_bid,
            confidence=request.confidence,
            marketplace=request.marketplace,
        )
        await session.commit()
        return result


@router.post("/ads/keyword-suggestion", summary="生成关键词优化建议")
async def ads_keyword_suggestion(request: AdsKeywordRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = AdsOptimizationService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.generate_keyword_suggestion(
            product_id=request.product_id,
            campaign_id=request.campaign_id,
            current_keywords=request.current_keywords,
            suggested_keywords=request.suggested_keywords,
            confidence=request.confidence,
            marketplace=request.marketplace,
        )
        await session.commit()
        return result


@router.post("/ads/budget-allocation", summary="生成预算分配建议")
async def ads_budget_allocation(request: AdsBudgetRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = AdsOptimizationService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.generate_budget_allocation_suggestion(
            product_id=request.product_id,
            campaign_id=request.campaign_id,
            current_budget=request.current_budget,
            suggested_budget=request.suggested_budget,
            reasoning=request.reasoning,
            confidence=request.confidence,
            marketplace=request.marketplace,
        )
        await session.commit()
        return result


# ─── FBA 域端点 ───

@router.post("/fba/config", summary="配置FBA域连接")
async def config_fba(request: FbaConfigRequest, user: Any = Depends(get_current_user)):
    client = _build_fba_client(request)
    result = await client.test_connection()
    return {"domain": "fba", "connection": result}


@router.post("/fba/restock", summary="生成FBA补货建议")
async def fba_restock(request: FbaRestockRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = FBARestockService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.generate_restock_suggestion(
            product_id=request.product_id,
            sku=request.sku,
            fnsku=request.fnsku,
            asin=request.asin,
            current_stock=request.current_stock,
            inbound_quantity=request.inbound_quantity,
            daily_velocity=request.daily_velocity,
            lead_time_days=request.lead_time_days,
            marketplace=request.marketplace,
        )
        await session.commit()
        return result


@router.post("/fba/batch-restock", summary="批量生成FBA补货建议")
async def fba_batch_restock(request: FbaBatchRestockRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = FBARestockService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.batch_generate_restock_suggestions(request.items)
        await session.commit()
        return result


# ─── TMS 域端点 ───

@router.post("/tms/config", summary="配置TMS域连接")
async def config_tms(request: TmsConfigRequest, user: Any = Depends(get_current_user)):
    client = _build_tms_client(request)
    result = await client.test_connection()
    return {"domain": "tms", "connection": result}


@router.post("/tms/logistics-risk", summary="生成物流风险建议")
async def tms_logistics_risk(request: TmsLogisticsRiskRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = TmsDomainService(
            _build_tms_client(TmsConfigRequest(api_endpoint="http://localhost:8080")),
            tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None,
        )
        result = await service.submit_logistics_risk(
            shipment_id=request.shipment_id,
            risk_type=request.risk_type,
            risk_description=request.risk_description,
            risk_score=request.risk_score,
            risk_level=request.risk_level,
            mitigation=request.mitigation,
            evidence=request.evidence,
        )
        await session.commit()
        return result


@router.post("/tms/shipping-rates", summary="查询运费报价")
async def tms_shipping_rates(request: TmsShippingRateRequest, user: Any = Depends(get_current_user)):
    client = _build_tms_client(TmsConfigRequest(api_endpoint="http://localhost:8080"))
    try:
        result = await client.get_shipping_rates(
            origin=request.origin,
            destination=request.destination,
            weight_kg=request.weight_kg,
        )
        return result
    except TMSClientError as e:
        raise HTTPException(status_code=502, detail=f"TMS域请求失败: {e}")


# ─── Dashboard 域端点 ───

@router.post("/dashboard/config", summary="配置Dashboard域连接")
async def config_dashboard(request: DashboardConfigRequest, user: Any = Depends(get_current_user)):
    client = _build_dashboard_client(request)
    result = await client.test_connection()
    return {"domain": "dashboard", "connection": result}


@router.post("/dashboard/insight-card", summary="推送洞察卡片")
async def dashboard_insight_card(request: DashboardInsightCardRequest, user: Any = Depends(get_current_user)):
    client = _build_dashboard_client(DashboardConfigRequest(api_endpoint="http://localhost:8080"))
    service = DashboardDomainService(client, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
    result = await service.push_insight_card(
        card_type=request.card_type,
        title=request.title,
        summary=request.summary,
        detail=request.detail,
        priority=request.priority,
    )
    return result


@router.post("/dashboard/risk-alert", summary="推送风险预警")
async def dashboard_risk_alert(request: DashboardRiskAlertRequest, user: Any = Depends(get_current_user)):
    client = _build_dashboard_client(DashboardConfigRequest(api_endpoint="http://localhost:8080"))
    service = DashboardDomainService(client, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
    result = await service.push_risk_alert(
        alert_type=request.alert_type,
        title=request.title,
        description=request.description,
        risk_level=request.risk_level,
        risk_score=request.risk_score,
        affected_entities=request.affected_entities,
        mitigations=request.mitigations,
    )
    return result


# ─── IAM 域端点 ───

@router.post("/iam/config", summary="配置IAM域连接")
async def config_iam(request: IamConfigRequest, user: Any = Depends(get_current_user)):
    client = _build_iam_client(request)
    result = await client.test_connection()
    return {"domain": "iam", "connection": result}


@router.post("/iam/permission-scope", summary="查询权限范围")
async def iam_permission_scope(request: IamPermissionScopeRequest, user: Any = Depends(get_current_user)):
    client = _build_iam_client(IamConfigRequest(api_endpoint="http://localhost:8080"))
    try:
        result = await client.get_permission_scope(
            actor_id=request.actor_id,
            scope_type=request.scope_type,
        )
        return result
    except IAMClientError as e:
        raise HTTPException(status_code=502, detail=f"IAM域请求失败: {e}")


# ─── SYS 域端点 ───

@router.post("/sys/config", summary="配置SYS域连接")
async def config_sys(request: SysConfigRequest, user: Any = Depends(get_current_user)):
    client = _build_sys_client(request)
    result = await client.test_connection()
    return {"domain": "sys", "connection": result}


@router.get("/sys/ai-feature/{feature_key}", summary="查询AI功能开关")
async def sys_get_feature_config(feature_key: str, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = AIFeatureToggleService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.get_feature_config(feature_key)
        if result is None:
            raise HTTPException(status_code=404, detail=f"功能开关不存在: {feature_key}")
        return result


@router.post("/sys/ai-feature", summary="设置AI功能开关")
async def sys_set_feature_config(request: FeatureToggleRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = AIFeatureToggleService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.set_feature_config(
            request.feature_key,
            is_enabled=request.is_enabled,
            rollout_percentage=request.rollout_percentage,
            config_overrides=request.config_overrides,
            description=request.description,
            tenant_id=request.tenant_id,
        )
        await session.commit()
        return result


# ─── 建议池管理端点 ───

@router.get("/recommendations", summary="查询建议列表")
async def list_recommendations(
    category: str | None = None,
    target_domain: str | None = None,
    execution_state: str | None = None,
    priority: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: Any = Depends(get_current_user),
):
    from src.models.enums import RecommendationCategory, RecommendationExecutionState, RecommendationPriority
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = RecommendationPoolService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.list_recommendations(
            category=RecommendationCategory(category) if category else None,
            target_domain=target_domain,
            execution_state=RecommendationExecutionState(execution_state) if execution_state else None,
            priority=RecommendationPriority(priority) if priority else None,
            limit=limit,
            offset=offset,
        )
        return result


@router.get("/recommendations/statistics", summary="建议统计")
async def recommendation_statistics(user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = RecommendationPoolService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        return await service.get_recommendation_statistics()


@router.get("/recommendations/{recommendation_id}", summary="查询建议详情")
async def get_recommendation(recommendation_id: str, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = RecommendationPoolService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        try:
            return await service.get_recommendation(recommendation_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))


@router.post("/recommendations/{recommendation_id}/approve", summary="批准建议")
async def approve_recommendation(recommendation_id: str, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = RecommendationPoolService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.approve_recommendation(recommendation_id)
        await session.commit()
        return result


@router.post("/recommendations/{recommendation_id}/reject", summary="拒绝建议")
async def reject_recommendation(recommendation_id: str, reason: str = "", user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = RecommendationPoolService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.reject_recommendation(recommendation_id, reason=reason)
        await session.commit()
        return result


# ─── 建议生命周期管理端点 ───

class SuggestionScoreRequest(BaseModel):
    score: float = Field(..., ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    scoring_summary: dict[str, Any] | None = None


class SuggestionRejectRequest(BaseModel):
    reason: str = Field(..., min_length=2, max_length=500)


class SuggestionSubmitRequest(BaseModel):
    pass


class SuggestionAdvanceRequest(BaseModel):
    target_state: str = Field(..., min_length=1)
    detail: str | None = None


@router.post("/suggestions", summary="创建建议(建议池模式)")
async def create_suggestion(request: CreateSuggestionRequest, user: Any = Depends(get_current_user)):
    from src.core.pms_governance import AuditContext
    from src.models.enums import RecommendationCategory, RecommendationPriority
    from src.services.suggestion_service import SuggestionService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        actor = _extract_actor(user)
        audit_ctx = AuditContext.from_actor(
            actor,
            tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None,
            purpose="create_suggestion",
            trace_id=actor.get("trace_id") or "api-suggestion-create",
        )
        service = SuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None, actor=actor)
        result = await service.create_suggestion(
            category=RecommendationCategory(request.category),
            target_domain=request.target_domain,
            title=request.title,
            description=request.description,
            priority=RecommendationPriority(request.priority) if request.priority else RecommendationPriority.MEDIUM,
            score=request.score,
            confidence=request.confidence,
            evidence_chain=request.evidence_chain,
            payload=request.payload,
            audit_context=audit_ctx,
        )
        await session.commit()
        return result


@router.post("/suggestions/{suggestion_id}/score", summary="评分建议")
async def score_suggestion(suggestion_id: str, request: SuggestionScoreRequest, user: Any = Depends(get_current_user)):
    from src.core.pms_governance import AuditContext
    from src.services.suggestion_service import SuggestionService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        actor = _extract_actor(user)
        audit_ctx = AuditContext.from_actor(
            actor,
            tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None,
            purpose="score_suggestion",
            trace_id=actor.get("trace_id") or f"api-suggestion-score-{suggestion_id}",
        )
        service = SuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None, actor=actor)
        result = await service.score_suggestion(
            suggestion_id, score=request.score, confidence=request.confidence,
            scoring_summary=request.scoring_summary, audit_context=audit_ctx,
        )
        await session.commit()
        return result


@router.post("/suggestions/{suggestion_id}/submit", summary="提交建议至ERP")
async def submit_suggestion(suggestion_id: str, request: SuggestionSubmitRequest, user: Any = Depends(get_current_user)):
    from src.core.pms_governance import AuditContext
    from src.services.suggestion_service import SuggestionService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        actor = _extract_actor(user)
        audit_ctx = AuditContext.from_actor(
            actor,
            tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None,
            purpose="submit_suggestion",
            trace_id=actor.get("trace_id") or f"api-suggestion-submit-{suggestion_id}",
            idempotency_key=f"suggestion-submit:{suggestion_id}",
        )
        service = SuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None, actor=actor)
        result = await service.submit_suggestion(suggestion_id, audit_context=audit_ctx)
        await session.commit()
        return result


@router.post("/suggestions/{suggestion_id}/approve", summary="ERP批准建议")
async def approve_suggestion(suggestion_id: str, user: Any = Depends(get_current_user)):
    from src.services.suggestion_service import SuggestionService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        actor = _extract_actor(user)
        service = SuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None, actor=actor)
        result = await service.approve_suggestion(suggestion_id)
        await session.commit()
        return result


@router.post("/suggestions/{suggestion_id}/reject", summary="拒绝建议")
async def reject_suggestion(suggestion_id: str, request: SuggestionRejectRequest, user: Any = Depends(get_current_user)):
    from src.services.suggestion_service import SuggestionService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        actor = _extract_actor(user)
        service = SuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None, actor=actor)
        result = await service.reject_suggestion(suggestion_id, reason=request.reason)
        await session.commit()
        return result


@router.get("/suggestions/{suggestion_id}/lifecycle", summary="查询建议生命周期状态")
async def get_suggestion_lifecycle(suggestion_id: str, user: Any = Depends(get_current_user)):
    from src.services.suggestion_service import SuggestionService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = SuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        return await service.get_suggestion_lifecycle(suggestion_id)


@router.post("/suggestions/{suggestion_id}/sync-state", summary="从执行状态同步建议状态")
async def sync_suggestion_state(suggestion_id: str, request: SuggestionAdvanceRequest, user: Any = Depends(get_current_user)):
    from src.models.enums import RecommendationExecutionState
    from src.services.suggestion_service import SuggestionService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        actor = _extract_actor(user)
        service = SuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None, actor=actor)
        try:
            target_state = RecommendationExecutionState(request.target_state)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的执行状态: {request.target_state}")
        result = await service.sync_from_execution_state(suggestion_id, target_state, detail=request.detail)
        await session.commit()
        return result


class SuggestionDiscardRequest(BaseModel):
    reason: str | None = None


@router.post("/suggestions/{suggestion_id}/discard", summary="丢弃建议")
async def discard_suggestion(suggestion_id: str, request: SuggestionDiscardRequest, user: Any = Depends(get_current_user)):
    from src.services.suggestion_service import SuggestionService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        actor = _extract_actor(user)
        service = SuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None, actor=actor)
        result = await service.discard_suggestion(suggestion_id, reason=request.reason)
        await session.commit()
        return result


@router.post("/suggestions/{suggestion_id}/expire", summary="过期建议(系统触发)")
async def expire_suggestion(suggestion_id: str, user: Any = Depends(get_current_user)):
    from src.services.suggestion_service import SuggestionService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = SuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.expire_suggestion(suggestion_id)
        await session.commit()
        return result


class TrackSuggestionRequest(BaseModel):
    target_domain: str = Field(default="scm", description="ERP域: scm/wms/ads/som/oms")
    domain_reference_id: str | None = Field(default=None, description="ERP域中的引用ID(默认使用suggestion_id)")


class BatchTrackRequest(BaseModel):
    suggestions: list[dict[str, Any]] = Field(..., min_length=1, description="建议列表，每项需含suggestion_id和target_domain")


@router.post("/suggestions/{suggestion_id}/track", summary="追踪建议执行状态")
async def track_suggestion(suggestion_id: str, request: TrackSuggestionRequest, user: Any = Depends(get_current_user)):
    from src.services.execution_tracking_service import ExecutionTrackingService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        actor = _extract_actor(user)
        service = ExecutionTrackingService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None, actor=actor)
        result = await service.track_suggestion_status(
            suggestion_id,
            target_domain=request.target_domain,
            domain_reference_id=request.domain_reference_id,
        )
        await session.commit()
        return result


@router.post("/suggestions/batch-track", summary="批量追踪建议执行状态")
async def batch_track_suggestions(request: BatchTrackRequest, user: Any = Depends(get_current_user)):
    from src.services.execution_tracking_service import ExecutionTrackingService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        actor = _extract_actor(user)
        service = ExecutionTrackingService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None, actor=actor)
        results = await service.batch_track_suggestions(request.suggestions)
        await session.commit()
        return {"tracked_count": len(results), "results": results}


@router.post("/tasks/{task_id}/track-execution", summary="追踪选品任务ERP执行状态")
async def track_task_execution(task_id: str, user: Any = Depends(get_current_user)):
    from src.services.execution_tracking_service import ExecutionTrackingService
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        actor = _extract_actor(user)
        service = ExecutionTrackingService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None, actor=actor)
        result = await service.track_task_execution(task_id)
        await session.commit()
        return result


# ─── 风控评分端点 ───

@router.post("/risk/assess", summary="执行风控评估")
async def assess_risk(request: RiskAssessmentRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = RiskScoringService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        method_map = {
            "order_risk": service.assess_order_risk,
            "supply_risk": service.assess_supply_risk,
            "inventory_risk": service.assess_inventory_risk,
            "pricing_risk": service.assess_pricing_risk,
        }
        method = method_map.get(request.risk_type)
        if method is None:
            raise HTTPException(status_code=400, detail=f"不支持的风险类型: {request.risk_type}")
        result = await method(target_id=request.target_id, target_domain=request.target_domain, **{request.risk_type.replace("_risk", "") + "_data": request.data})
        await session.commit()
        return result


# ─── 利润中枢闭环端点 (P12-09) ───

class ProfitCenterQueryRequest(BaseModel):
    product_id: str | None = Field(default=None, description="产品ID")
    marketplace: str | None = Field(default=None, description="市场")
    date_from: str | None = Field(default=None, description="起始日期(ISO)")
    date_to: str | None = Field(default=None, description="截止日期(ISO)")


class CrmFeedbackQueryRequest(BaseModel):
    product_id: str | None = Field(default=None, description="产品ID")
    category: str | None = Field(default=None, description="客诉分类: quality/logistics/description/after_sales")
    limit: int = Field(default=50, ge=1, le=200, description="返回条数上限")


@router.post("/profit-center/query", summary="利润中枢数据查询")
async def query_profit_center(request: ProfitCenterQueryRequest, user: Any = Depends(get_current_user)):
    from src.infrastructure.bi_client import BIClient
    from src.infrastructure.database import get_settings
    from src.infrastructure.fms_client import FMSClient
    settings = get_settings()
    result: dict[str, Any] = {"profit_center": {}}
    try:
        fms_client = FMSClient(
            api_endpoint=settings.FMS_API_ENDPOINT if hasattr(settings, "FMS_API_ENDPOINT") else "local://artifacts/fms",
            api_key=settings.FMS_API_KEY if hasattr(settings, "FMS_API_KEY") else None,
        )
        finance_metrics = await fms_client.fetch_finance_metrics()
        profit_facts = await fms_client.fetch_profit_facts()
        ad_spending = await fms_client.fetch_ad_spending()
        result["profit_center"]["finance_metrics"] = finance_metrics
        result["profit_center"]["profit_facts"] = profit_facts
        result["profit_center"]["ad_spending"] = ad_spending
    except Exception as e:
        logger.warning("FMS数据查询失败: %s", e)
        result["profit_center"]["fms_error"] = str(e)
    try:
        bi_client = BIClient(
            api_endpoint=settings.BI_API_ENDPOINT if hasattr(settings, "BI_API_ENDPOINT") else "local://artifacts/bi",
            api_key=settings.BI_API_KEY if hasattr(settings, "BI_API_KEY") else None,
        )
        bi_data = await bi_client.read_dataset()
        result["profit_center"]["bi_dataset"] = bi_data
    except Exception as e:
        logger.warning("BI数据查询失败: %s", e)
        result["profit_center"]["bi_error"] = str(e)
    return result


@router.post("/crm/feedback-query", summary="CRM客诉数据查询")
async def query_crm_feedback(request: CrmFeedbackQueryRequest, user: Any = Depends(get_current_user)):
    from src.infrastructure.crm_client import CRMClient
    from src.infrastructure.database import get_settings
    settings = get_settings()
    try:
        crm_client = CRMClient(
            api_endpoint=settings.CRM_API_ENDPOINT if hasattr(settings, "CRM_API_ENDPOINT") else "local://artifacts/crm",
            api_key=settings.CRM_API_KEY if hasattr(settings, "CRM_API_KEY") else None,
        )
        complaints = await crm_client.fetch_complaints()
        feedbacks = await crm_client.fetch_customer_feedbacks()
        result: dict[str, Any] = {"complaints": complaints, "feedbacks": feedbacks}
        if request.category:
            result["complaints"] = [c for c in complaints if isinstance(c, dict) and c.get("category") == request.category]
        if request.product_id:
            result["complaints"] = [c for c in result["complaints"] if isinstance(c, dict) and c.get("product_id") == request.product_id]
            result["feedbacks"] = [f for f in feedbacks if isinstance(f, dict) and f.get("product_id") == request.product_id]
        if request.limit:
            result["complaints"] = result["complaints"][:request.limit]
            result["feedbacks"] = result["feedbacks"][:request.limit]
        return result
    except Exception as e:
        logger.warning("CRM数据查询失败: %s", e)
        raise HTTPException(status_code=502, detail=f"CRM数据查询失败: {e}")


@router.get("/profit-center/loop-status", summary="利润中枢闭环状态总览")
async def profit_center_loop_status(user: Any = Depends(get_current_user)):
    from src.infrastructure.database import get_async_session_factory
    session_factory = get_async_session_factory()
    result: dict[str, Any] = {
        "domains": {
            "scm": {"status": "available", "description": "采购建议/采购单追踪"},
            "wms": {"status": "available", "description": "库存预留/确认"},
            "oms": {"status": "available", "description": "订单/Listing状态"},
            "som": {"status": "available", "description": "Listing草稿/发布"},
            "ads": {"status": "available", "description": "广告投放优化"},
            "crm": {"status": "available", "description": "客诉/评价数据"},
            "fms": {"status": "available", "description": "财务/广告费/利润"},
            "bi": {"status": "available", "description": "BI数据集/KPI"},
        },
        "tracking_enabled": True,
        "feedback_loop": "active",
    }
    async with session_factory() as session:
        try:
            from src.services.suggestion_service import SuggestionService
            service = SuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None, actor=_extract_actor(user))
            stats = await service.get_suggestion_stats()
            result["suggestion_stats"] = stats
        except Exception as e:
            logger.warning("建议统计查询失败: %s", e)
            result["suggestion_stats"] = {"error": str(e)}
    return result


# ─── 定价建议端点 ───

@router.post("/pricing/suggest", summary="生成定价建议")
async def pricing_suggest(request: PricingRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = PricingSuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.generate_new_product_pricing(
            product_id=request.product_id,
            cost_data=request.cost_data,
            market_data=request.market_data,
            target_margin=request.target_margin,
            marketplace=request.marketplace,
        )
        await session.commit()
        return result


@router.post("/pricing/adjust", summary="生成调价建议")
async def pricing_adjust(request: PricingAdjustmentRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = PricingSuggestionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.generate_price_adjustment(
            product_id=request.product_id,
            current_price=request.current_price,
            cost_data=request.cost_data,
            market_data=request.market_data,
            sales_data=request.sales_data,
            target_margin=request.target_margin,
            marketplace=request.marketplace,
        )
        await session.commit()
        return result


# ─── 库存预测端点 ───

@router.post("/inventory/predict", summary="生成库存预测")
async def inventory_predict(request: InventoryPredictionRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = InventoryPredictionService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.generate_prediction(
            product_id=request.product_id,
            sku=request.sku,
            current_stock=request.current_stock,
            historical_sales=request.historical_sales,
            seasonality_factor=request.seasonality_factor,
            promotion_calendar=request.promotion_calendar,
            lead_time_days=request.lead_time_days,
            marketplace=request.marketplace,
        )
        await session.commit()
        return result


# ─── 情感分析端点 ───

@router.post("/sentiment/analyze", summary="执行情感分析")
async def sentiment_analyze(request: SentimentAnalysisRequest, user: Any = Depends(get_current_user)):
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = SentimentAnalysisService(session, tenant_id=str(user.tenant_id) if hasattr(user, "tenant_id") else None)
        result = await service.analyze_product_sentiment(
            product_id=request.product_id,
            reviews=request.reviews,
            marketplace=request.marketplace,
        )
        await session.commit()
        return result


# ─── ERP事件回流端点 ───

@router.post("/feedback/event", summary="接收ERP执行反馈事件")
async def receive_erp_feedback(request: ErpFeedbackEventRequest, user: Any = Depends(get_current_user)):
    event = {
        "event_type": request.event_type,
        "aggregate_id": request.aggregate_id,
        "tenant_id": request.tenant_id,
        "payload": request.payload,
    }
    result = await handle_erp_feedback_event(event)
    return result


@router.post("/feedback/domain-event", summary="接收ERP域事件")
async def receive_erp_domain_event(request: ErpDomainEventRequest, user: Any = Depends(get_current_user)):
    event = {
        "event_type": request.event_type,
        "domain": request.domain,
        "tenant_id": request.tenant_id,
        "payload": request.payload,
    }
    result = await handle_erp_domain_event(event)
    return result
