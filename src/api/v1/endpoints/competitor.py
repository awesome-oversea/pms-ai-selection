from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from src.core.auth import get_current_user
from src.services.competitor_analysis_service import CompetitorAnalysisService

router = APIRouter(prefix="/competitors", tags=["竞品分析"])


class CompetitorAnalyzeRequest(BaseModel):
    product_name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    target_market: str = Field(default="US")
    monitor_config: dict = Field(default_factory=dict)


@router.post("/analyze", response_model=dict)
async def analyze_competitors(request: CompetitorAnalyzeRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = CompetitorAnalysisService()
        return await service.analyze(
            product_name=request.product_name,
            category=request.category,
            target_market=request.target_market,
            monitor_config=request.monitor_config,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"竞品分析失败: {e}")


@router.post("/monitor/run", response_model=dict)
async def run_competitor_monitor_job(request: CompetitorAnalyzeRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = CompetitorAnalysisService()
        return await service.run_monitor_job(
            product_name=request.product_name,
            category=request.category,
            target_market=request.target_market,
            monitor_config=request.monitor_config,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"竞品监控任务执行失败: {e}")
