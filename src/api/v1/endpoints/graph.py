from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from src.core.auth import get_current_user
from src.services.graph_rag_service import GraphRAGService

router = APIRouter(prefix="/graph", tags=["GraphRAG"])


class GraphBuildRequest(BaseModel):
    text: str = Field(..., min_length=1)
    doc_id: str | None = None


class GraphQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_hops: int = Field(default=2, ge=1, le=3)
    top_k: int = Field(default=10, ge=1, le=20)


@router.post("/build", response_model=dict)
async def build_graph(request: GraphBuildRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = GraphRAGService()
        return await service.build_graph_from_text(text=request.text, doc_id=request.doc_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"图谱构建失败: {e}")


@router.post("/query", response_model=dict)
async def query_graph(request: GraphQueryRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = GraphRAGService()
        return await service.query_graph(query=request.query, max_hops=request.max_hops, top_k=request.top_k)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"图谱查询失败: {e}")


@router.get("/competitors", response_model=dict)
async def get_competitor_graph(brand_name: str = Query(..., min_length=1), current_user: dict = Depends(get_current_user)):
    try:
        service = GraphRAGService()
        return await service.get_competitor_graph(brand_name=brand_name)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"竞品图谱查询失败: {e}")


@router.get("/product", response_model=dict)
async def get_product_graph(product_name: str = Query(..., min_length=1), max_hops: int = Query(2, ge=1, le=3), current_user: dict = Depends(get_current_user)):
    try:
        service = GraphRAGService()
        return await service.get_product_graph(product_name=product_name, max_hops=max_hops)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"产品图谱查询失败: {e}")


@router.get("/status", response_model=dict)
async def get_graph_status(current_user: dict = Depends(get_current_user)):
    service = GraphRAGService()
    return service.get_status()
