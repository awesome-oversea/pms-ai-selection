from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.auth import get_current_user
from src.core.security import add_audit_log
from src.services.product_planning_service import ProductPlanningService

router = APIRouter(prefix="/product-planning", tags=["Product Planning"])


class ProductPlanningRequest(BaseModel):
    query: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    target_market: str = Field(default="US")
    budget_range: list[float] = Field(default_factory=list)
    extra_params: dict[str, Any] = Field(default_factory=dict)
    external_results: list[dict[str, Any]] = Field(default_factory=list)


class ReviewClusterRequest(BaseModel):
    reviews: list[str] = Field(default_factory=list)
    review_clusters: int = Field(default=4, ge=1, le=20)


class SupplierSpecComparisonRequest(BaseModel):
    reviews: list[str] = Field(default_factory=list)
    review_clusters: int = Field(default=4, ge=1, le=20)
    max_suppliers: int = Field(default=10, ge=1, le=50)


class CRMReviewInsightsRequest(BaseModel):
    crm_api_endpoint: str | None = None
    crm_api_key: str | None = None
    crm_inbound_path: str = Field(default="/customer-feedback")
    product_id: str | None = None
    asin: str | None = None


class MultimodalPlanningRequest(BaseModel):
    review_images: list[dict[str, Any]] = Field(default_factory=list)
    tiktok_videos: list[dict[str, Any]] = Field(default_factory=list)
    social_images: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/analyze", response_model=dict)
async def analyze_product_planning(request: ProductPlanningRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ProductPlanningService()
        result = await service.analyze(
            query=request.query,
            category=request.category,
            target_market=request.target_market,
            budget_range=request.budget_range,
            extra_params=request.extra_params,
            external_results=request.external_results,
        )
        add_audit_log(
            "product.planning.analyze",
            actor=current_user,
            target_type="product_planning",
            result="success",
            detail={"query": request.query, "category": request.category},
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"product planning analyze failed: {e}")


@router.post("/review-clusters", response_model=dict)
async def cluster_product_reviews(request: ReviewClusterRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ProductPlanningService()
        return await service.cluster_reviews(reviews=request.reviews, review_clusters=request.review_clusters)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"product review clustering failed: {e}")


@router.post("/supplier-spec-comparison", response_model=dict)
async def compare_product_supplier_specs(request: SupplierSpecComparisonRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ProductPlanningService()
        return await service.compare_supplier_specs(
            reviews=request.reviews,
            review_clusters=request.review_clusters,
            max_suppliers=request.max_suppliers,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"supplier spec comparison failed: {e}")


@router.post("/crm-review-insights", response_model=dict)
async def get_product_crm_review_insights(request: CRMReviewInsightsRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ProductPlanningService()
        return await service.fetch_crm_review_insights(
            crm_api_endpoint=request.crm_api_endpoint,
            crm_api_key=request.crm_api_key,
            crm_inbound_path=request.crm_inbound_path,
            product_id=request.product_id,
            asin=request.asin,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"crm review insights failed: {e}")


@router.post("/multimodal-insights", response_model=dict)
async def analyze_product_multimodal_assets(request: MultimodalPlanningRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ProductPlanningService()
        return await service.analyze_multimodal_assets(
            review_images=request.review_images,
            tiktok_videos=request.tiktok_videos,
            social_images=request.social_images,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"multimodal product planning failed: {e}")
