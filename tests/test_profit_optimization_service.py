from __future__ import annotations

import pytest
from src.services.profit_optimization_service import ProfitOptimizationService


@pytest.mark.asyncio
async def test_profit_optimization_service_returns_pricing_and_roi():
    class _FakeCommercialAgent:
        async def _calculate_detailed_costs(self, **kwargs):
            return {"total_cost_per_unit": 18.0, "gross_margin_pct": 32.0, "optimization_suggestions": ["优化广告成本"]}

        async def _recommend_pricing(self, **kwargs):
            cost_per_unit = kwargs.get("cost_per_unit", 18.0)
            return {
                "strategy_selected": kwargs.get("pricing_strategy", "competitive"),
                "final_recommendation": {"price": round(cost_per_unit * 2.2, 2), "expected_margin": 28.5},
            }

        async def _predict_roi(self, **kwargs):
            monthly_revenue = kwargs.get("monthly_revenue", 0)
            monthly_cost = kwargs.get("monthly_cost", 1)
            roi_value = round(max(0.0, (monthly_revenue - monthly_cost) / max(monthly_cost, 1) * 100), 1)
            return {
                "key_metrics": {"roi_year1_percent": roi_value, "payback_period_months": 11.5},
                "investment_verdict": {"verdict": "RECOMMENDED"},
            }

        async def _price_elasticity_model(self, **kwargs):
            return {"price_elasticity": -1.6, "pricing_advice": "建议控制价格波动"}

    service = ProfitOptimizationService()
    service.agent = _FakeCommercialAgent()

    result = await service.optimize(
        category="electronics",
        target_price=39.99,
        monthly_volume_est=500,
        unit_cost_1688=5.0,
        competitor_prices=[29.99, 34.99, 39.99],
        logistics_cost_per_unit=2.5,
        platform_fee_rate=0.12,
        marketing_cost_per_unit=3.0,
    )
    assert result["explicit_cost_inputs"]["procurement_cost_per_unit"] == 5.0
    assert result["explicit_cost_inputs"]["logistics_cost_per_unit"] == 2.5
    assert result["explicit_cost_inputs"]["marketing_cost_per_unit"] == 3.0
    assert len(result["scenario_analysis"]) == 3
    assert {item["scenario"] for item in result["scenario_analysis"]} == {"conservative", "base", "aggressive"}
    assert result["final_recommendation"]["recommended_price"] > 0
    assert result["decision_ready_summary"]["pricing"]["recommended_price"] == result["final_recommendation"]["recommended_price"]
    assert result["roi_projection"]["investment_verdict"]["verdict"] == "RECOMMENDED"


@pytest.mark.asyncio
async def test_profit_optimization_service_prefers_fms_cost_snapshot(monkeypatch):
    class _FakeCommercialAgent:
        async def _calculate_detailed_costs(self, **kwargs):
            return {"total_cost_per_unit": 18.0, "gross_margin_pct": 32.0, "optimization_suggestions": ["优化广告成本"]}

        async def _recommend_pricing(self, **kwargs):
            cost_per_unit = kwargs.get("cost_per_unit", 18.0)
            return {
                "strategy_selected": kwargs.get("pricing_strategy", "competitive"),
                "final_recommendation": {"price": round(cost_per_unit * 2.2, 2), "expected_margin": 28.5},
            }

        async def _predict_roi(self, **kwargs):
            return {
                "key_metrics": {"roi_year1_percent": 88.8, "payback_period_months": 8.5},
                "investment_verdict": {"verdict": "RECOMMENDED"},
            }

        async def _price_elasticity_model(self, **kwargs):
            return {"price_elasticity": -1.6, "pricing_advice": "建议控制价格波动"}

    class _FakeFMSClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def fetch_finance_metrics(self):
            return [{
                "product_id": "prod-001",
                "currency": "USD",
                "procurement_cost_per_unit": 8.0,
                "logistics_cost_per_unit": 3.0,
                "marketing_cost_per_unit": 4.0,
                "tax_cost_per_unit": 1.5,
                "platform_fee_rate": 0.15,
                "gross_profit": 120.0,
            }]

        async def fetch_ad_spending(self):
            return [{
                "product_id": "prod-001",
                "ad_spending": 40.0,
                "ad_sales": 200.0,
            }]

    monkeypatch.setattr("src.services.profit_optimization_service.FMSClient", _FakeFMSClient)

    service = ProfitOptimizationService()
    service.agent = _FakeCommercialAgent()

    result = await service.optimize(
        category="electronics",
        target_price=39.99,
        monthly_volume_est=500,
        unit_cost_1688=5.0,
        competitor_prices=[29.99, 34.99, 39.99],
        logistics_cost_per_unit=1.0,
        platform_fee_rate=0.1,
        marketing_cost_per_unit=1.0,
        product_id="prod-001",
        fms_api_endpoint="http://fake-fms.local",
        fms_api_key="demo-key",
        currency="USD",
        exchange_rate=1.0,
        tax_cost_per_unit=0.5,
    )

    assert result["fms_cost_snapshot"]["found"] is True
    assert result["explicit_cost_inputs"]["procurement_cost_per_unit"] == 8.0
    assert result["explicit_cost_inputs"]["logistics_cost_per_unit"] == 3.0
    assert result["explicit_cost_inputs"]["marketing_cost_per_unit"] == 4.0
    assert result["explicit_cost_inputs"]["tax_cost_per_unit"] == 1.5
    assert result["explicit_cost_inputs"]["platform_fee_rate"] == 0.15
    assert result["cost_trace"]["procurement_cost_per_unit"] == "fms"
    assert result["cost_trace"]["tax_cost_per_unit"] == "fms"
    assert result["fms_cost_snapshot"]["ad_spending_summary"]["found"] is True
    assert result["fms_cost_snapshot"]["ad_spending_summary"]["acos"] == 0.2
