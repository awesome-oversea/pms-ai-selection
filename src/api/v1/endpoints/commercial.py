from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from src.core.auth import get_current_user
from src.core.security import add_audit_log
from src.services.profit_optimization_service import ProfitOptimizationService

router = APIRouter(prefix="/commercial", tags=["利润优化"])


class ProfitOptimizationRequest(BaseModel):
    category: str = Field(..., min_length=1)
    target_price: float = Field(..., gt=0)
    monthly_volume_est: int = Field(..., gt=0)
    unit_cost_1688: float = Field(..., gt=0)
    competitor_prices: list[float] = Field(default_factory=list)
    pricing_strategy: str = Field(default="competitive")
    initial_investment: float = Field(default=50000, gt=0)
    logistics_cost_per_unit: float = Field(default=0.0, ge=0)
    platform_fee_rate: float = Field(default=0.0, ge=0, le=1)
    marketing_cost_per_unit: float = Field(default=0.0, ge=0)
    product_id: str | None = None
    fms_api_endpoint: str | None = None
    fms_api_key: str | None = None
    fms_inbound_path: str = "/finance-metrics"
    currency: str = Field(default="USD")
    exchange_rate: float = Field(default=1.0, gt=0)
    tax_cost_per_unit: float = Field(default=0.0, ge=0)


class QuoteCacheRequest(BaseModel):
    product_keyword: str = Field(..., min_length=1)
    max_suppliers: int = Field(default=10, ge=1, le=50)


class RestockPlanRequest(BaseModel):
    product_keyword: str = Field(..., min_length=1)
    monthly_demand: int = Field(..., gt=0)
    current_inventory_units: int = Field(..., ge=0)
    target_price: float = Field(..., gt=0)
    max_suppliers: int = Field(default=10, ge=1, le=50)
    preferred_supplier_code: str | None = None
    oms_api_endpoint: str | None = None
    oms_api_key: str | None = None
    oms_inbound_path: str = "/orders"
    product_id: str | None = None


class SupplierReliabilityRequest(BaseModel):
    product_keyword: str = Field(..., min_length=1)
    scm_api_endpoint: str = Field(..., min_length=1)
    scm_api_key: str | None = None
    scm_inbound_path: str = "/supplier-products"
    preferred_supplier_code: str | None = None


class FmsCostSnapshotRequest(BaseModel):
    product_id: str | None = None
    fms_api_endpoint: str = Field(..., min_length=1)
    fms_api_key: str | None = None
    fms_inbound_path: str = "/finance-metrics"
    ad_spending_path: str | None = None
    currency: str = Field(default="USD")
    exchange_rate: float = Field(default=1.0, gt=0)


class OmsPriceElasticityRequest(BaseModel):
    oms_api_endpoint: str = Field(..., min_length=1)
    oms_api_key: str | None = None
    oms_inbound_path: str = "/orders"
    product_id: str | None = None
    target_price: float = Field(..., gt=0)


@router.post("/optimize", response_model=dict)
async def optimize_profit(request: ProfitOptimizationRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ProfitOptimizationService()
        result = await service.optimize(
            category=request.category,
            target_price=request.target_price,
            monthly_volume_est=request.monthly_volume_est,
            unit_cost_1688=request.unit_cost_1688,
            competitor_prices=request.competitor_prices,
            pricing_strategy=request.pricing_strategy,
            initial_investment=request.initial_investment,
            logistics_cost_per_unit=request.logistics_cost_per_unit,
            platform_fee_rate=request.platform_fee_rate,
            marketing_cost_per_unit=request.marketing_cost_per_unit,
            product_id=request.product_id,
            fms_api_endpoint=request.fms_api_endpoint,
            fms_api_key=request.fms_api_key,
            fms_inbound_path=request.fms_inbound_path,
            currency=request.currency,
            exchange_rate=request.exchange_rate,
            tax_cost_per_unit=request.tax_cost_per_unit,
        )
        add_audit_log("commercial.optimize", actor=current_user, target_type="commercial_analysis", result="success", detail={"category": request.category})
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"利润优化失败: {e}")


@router.post("/quote-cache", response_model=dict)
async def build_quote_cache(request: QuoteCacheRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ProfitOptimizationService()
        result = await service.build_quote_cache(product_keyword=request.product_keyword, max_suppliers=request.max_suppliers)
        add_audit_log("commercial.quote_cache", actor=current_user, target_type="supplier_quote_cache", result="success", detail={"product_keyword": request.product_keyword})
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"供应商报价缓存生成失败: {e}")


@router.post("/restock-plan", response_model=dict)
async def build_restock_plan(request: RestockPlanRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ProfitOptimizationService()
        result = await service.build_restock_plan(
            product_keyword=request.product_keyword,
            monthly_demand=request.monthly_demand,
            current_inventory_units=request.current_inventory_units,
            target_price=request.target_price,
            max_suppliers=request.max_suppliers,
            preferred_supplier_code=request.preferred_supplier_code,
            oms_api_endpoint=request.oms_api_endpoint,
            oms_api_key=request.oms_api_key,
            oms_inbound_path=request.oms_inbound_path,
            product_id=request.product_id,
        )
        add_audit_log("commercial.restock_plan", actor=current_user, target_type="restock_plan", result="success", detail={"product_keyword": request.product_keyword})
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"备货计划生成失败: {e}")


@router.post("/supplier-reliability", response_model=dict)
async def build_supplier_reliability(request: SupplierReliabilityRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ProfitOptimizationService()
        result = await service.build_supplier_reliability(
            product_keyword=request.product_keyword,
            scm_api_endpoint=request.scm_api_endpoint,
            scm_api_key=request.scm_api_key,
            scm_inbound_path=request.scm_inbound_path,
            preferred_supplier_code=request.preferred_supplier_code,
        )
        add_audit_log("commercial.supplier_reliability", actor=current_user, target_type="supplier_reliability", result="success", detail={"product_keyword": request.product_keyword})
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"供应商可靠性评估失败: {e}")


@router.post("/fms-cost-snapshot", response_model=dict)
async def build_fms_cost_snapshot(request: FmsCostSnapshotRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ProfitOptimizationService()
        result = await service.build_fms_cost_snapshot(
            product_id=request.product_id,
            fms_api_endpoint=request.fms_api_endpoint,
            fms_api_key=request.fms_api_key,
            fms_inbound_path=request.fms_inbound_path,
            ad_spending_path=request.ad_spending_path,
            currency=request.currency,
            exchange_rate=request.exchange_rate,
        )
        add_audit_log("commercial.fms_cost_snapshot", actor=current_user, target_type="fms_cost_snapshot", result="success", detail={"product_id": request.product_id})
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"FMS成本快照获取失败: {e}")


@router.post("/oms-price-elasticity", response_model=dict)
async def build_oms_price_elasticity_snapshot(request: OmsPriceElasticityRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ProfitOptimizationService()
        result = await service.build_oms_price_elasticity_snapshot(
            oms_api_endpoint=request.oms_api_endpoint,
            oms_api_key=request.oms_api_key,
            oms_inbound_path=request.oms_inbound_path,
            product_id=request.product_id,
            target_price=request.target_price,
        )
        add_audit_log("commercial.oms_price_elasticity", actor=current_user, target_type="oms_price_elasticity", result="success", detail={"product_id": request.product_id})
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"OMS价格弹性快照获取失败: {e}")
