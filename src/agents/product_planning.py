from __future__ import annotations

from src.agents.product_planner import (
    CostStructure,
    DifferentiationScore,
    ProductPlannerAgent,
    ProductRecommendation,
    ProductSpec,
    SupplyChainAssessment,
    create_product_planner_agent,
)

ProductPlanningAgent = ProductPlannerAgent
create_product_planning_agent = create_product_planner_agent

__all__ = [
    "CostStructure",
    "DifferentiationScore",
    "ProductPlanningAgent",
    "ProductPlannerAgent",
    "ProductRecommendation",
    "ProductSpec",
    "SupplyChainAssessment",
    "create_product_planning_agent",
    "create_product_planner_agent",
]
