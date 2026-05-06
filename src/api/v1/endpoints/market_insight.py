from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.auth import get_current_user
from src.core.security import add_audit_log
from src.services.market_insight_service import MarketInsightService

router = APIRouter(prefix="/market-insight", tags=["Market Insight"])


class MarketInsightRequest(BaseModel):
    query: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    target_market: str = Field(default="US")


@router.post("/predict", response_model=dict)
async def predict_market_insight(request: MarketInsightRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = MarketInsightService()
        result = await service.predict(
            query=request.query,
            category=request.category,
            target_market=request.target_market,
        )
        add_audit_log(
            "market.insight.predict",
            actor=current_user,
            target_type="market_insight",
            result="success",
            detail={"query": request.query, "category": request.category},
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"market insight predict failed: {e}")


@router.post("/aggregate", response_model=dict)
async def get_market_insight_aggregate(request: MarketInsightRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = MarketInsightService()
        return await service.get_google_trends_aggregate(
            query=request.query,
            category=request.category,
            target_market=request.target_market,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"market insight aggregate failed: {e}")


@router.post("/demand-supply-ratio", response_model=dict)
async def get_market_insight_demand_supply_ratio(request: MarketInsightRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = MarketInsightService()
        return await service.get_bsr_demand_supply_ratio(
            query=request.query,
            category=request.category,
            target_market=request.target_market,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"market insight demand supply ratio failed: {e}")
