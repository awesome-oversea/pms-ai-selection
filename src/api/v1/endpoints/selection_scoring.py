from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.auth import get_current_user
from src.core.security import add_audit_log
from src.services.selection_scoring_service import SelectionScoringService

router = APIRouter(prefix="/selection", tags=["Selection"])


class SelectionScoringRequest(BaseModel):
    query: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    target_market: str = Field(default="US")
    session_id: str | None = None
    data_collection_result: dict[str, Any] = Field(default_factory=dict)
    market_analysis_result: dict[str, Any] = Field(default_factory=dict)
    product_planning_result: dict[str, Any] = Field(default_factory=dict)
    commercial_evaluation_result: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_log: list[dict[str, Any]] = Field(default_factory=list)
    execution_log: list[dict[str, Any]] = Field(default_factory=list)
    current_phase: str = Field(default="commercial_evaluation")
    retry_count: int = Field(default=0, ge=0)


@router.post("/recommendations/score", response_model=dict)
async def score_selection_recommendations(
    request: SelectionScoringRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        service = SelectionScoringService()
        result = service.score_selection(
            session_id=request.session_id,
            query=request.query,
            category=request.category,
            target_market=request.target_market,
            data_collection_result=request.data_collection_result,
            market_analysis_result=request.market_analysis_result,
            product_planning_result=request.product_planning_result,
            commercial_evaluation_result=request.commercial_evaluation_result,
            metadata=request.metadata,
            error_log=request.error_log,
            execution_log=request.execution_log,
            current_phase=request.current_phase,
            retry_count=request.retry_count,
        )
        add_audit_log(
            "selection.recommendation.score",
            actor=current_user,
            target_type="selection_recommendation",
            result="success",
            detail={
                "query": request.query,
                "category": request.category,
                "target_market": request.target_market,
            },
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"selection recommendation scoring failed: {e}")
