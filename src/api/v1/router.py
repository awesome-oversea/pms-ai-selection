"""
API router registration for v1 endpoints.
"""

from fastapi import APIRouter

from src.api.v1.endpoints import (
    agents,
    auth,
    bff,
    channels,
    commercial,
    competitor,
    erp,
    graph,
    health,
    integration,
    knowledge,
    llm,
    market,
    market_insight,
    product_planning,
    reports,
    selection,
    selection_scoring,
    system,
    triton,
)

api_router = APIRouter()

api_router.include_router(auth.router, tags=["Auth"])
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(system.router, tags=["System"])
api_router.include_router(selection.router, tags=["Selection"])
api_router.include_router(selection_scoring.router, tags=["Selection"])
api_router.include_router(agents.router, tags=["Agents"])
api_router.include_router(knowledge.router, tags=["Knowledge"])
api_router.include_router(llm.router, tags=["LLM"])
api_router.include_router(bff.router, tags=["BFF"])
api_router.include_router(integration.router, tags=["Integration"])
api_router.include_router(erp.router, tags=["ERP六域服务"])
api_router.include_router(market.router, tags=["Market"])
api_router.include_router(market_insight.router, tags=["Market Insight"])
api_router.include_router(competitor.router, tags=["Competitor"])
api_router.include_router(commercial.router, tags=["Commercial"])
api_router.include_router(product_planning.router, tags=["Product Planning"])
api_router.include_router(graph.router, tags=["GraphRAG"])
api_router.include_router(channels.router, tags=["Channels"])
api_router.include_router(triton.router, tags=["Triton"])
api_router.include_router(reports.router, tags=["Reports"])
