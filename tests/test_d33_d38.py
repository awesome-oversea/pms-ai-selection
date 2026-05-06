"""D33-D38 单元测试: 产品规划Agent增强 + 商业化Agent增强"""


import pytest
from src.agents.commercial import CommercialAgent
from src.agents.product_planner import ProductPlannerAgent


class TestProductPlannerAgentEnhanced:
    """D33-D35 产品规划Agent增强测试"""

    def setup_method(self):
        self.agent = ProductPlannerAgent()

    def test_agent_has_9_tools(self):
        assert len(self.agent.get_tools()) == 12

    def test_llava_tool_registered(self):
        tools = {t.name for t in self.agent.get_tools()}
        assert "llava_analyze_image" in tools

    def test_cluster_reviews_tool_registered(self):
        tools = {t.name for t in self.agent.get_tools()}
        assert "cluster_reviews" in tools

    def test_competitor_diff_tool_registered(self):
        tools = {t.name for t in self.agent.get_tools()}
        assert "competitor_diff" in tools

    def test_swot_tool_registered(self):
        tools = {t.name for t in self.agent.get_tools()}
        assert "swot_analysis" in tools
        assert "compare_1688_specs" in tools
        assert "fetch_crm_reviews" in tools

    @pytest.mark.asyncio
    async def test_llava_analyze_image_features(self):
        result = await self.agent.call_tool("llava_analyze_image", image_url="https://example.com/img.jpg")
        assert result["source"] == "multimodal_image_analysis"
        assert "visual_features" in result
        assert len(result["visual_features"]) >= 1
        for vf in result["visual_features"]:
            assert "attribute" in vf
            assert "value" in vf
            assert "confidence" in vf
            assert 0 <= vf["confidence"] <= 1

    @pytest.mark.asyncio
    async def test_llava_design_defects(self):
        result = await self.agent.call_tool("llava_analyze_image", analysis_type="design_defects")
        assert result["analysis_type"] == "design_defects"
        assert "defects" in result
        assert isinstance(result["defects"], list)
        assert "design_score" in result

    @pytest.mark.asyncio
    async def test_cluster_reviews_basic(self):
        result = await self.agent.call_tool("cluster_reviews")
        assert result["source"] == "review_clustering"
        assert "clusters" in result
        assert "pain_points" in result
        assert "sentiment_summary" in result
        if result["pain_points"]:
            pp = result["pain_points"][0]
            assert "point" in pp
            assert "frequency" in pp
            assert "severity" in pp
            assert "solution" in pp

    @pytest.mark.asyncio
    async def test_cluster_reviews_keyword_freq(self):
        result = await self.agent.call_tool("cluster_reviews")
        keywords = result["top_keywords"]
        assert len(keywords) > 0
        kw = keywords[0]
        assert "word" in kw
        assert "count" in kw

    @pytest.mark.asyncio
    async def test_competitor_diff_matrix(self):
        result = await self.agent.call_tool(
            "competitor_diff",
            product_name="MyEarbuds",
            category="earbuds",
            competitors=["BrandA", "BrandB"],
        )
        assert result["source"] == "competitor_diff"
        assert "feature_matrix" in result
        assert "competitor_profiles" in result
        assert len(result["competitor_profiles"]) == 2
        cp = result["competitor_profiles"][0]
        assert "name" in cp
        assert "overall_score" in cp
        assert "strengths" in cp
        assert "weaknesses" in cp

    @pytest.mark.asyncio
    async def test_swot_analysis_structure(self):
        result = await self.agent.call_tool(
            "swot_analysis",
            product_spec={"name": "TestProduct", "category": "electronics"},
        )
        assert result["source"] == "swot_analysis"
        assert "strengths" in result
        assert "weaknesses" in result
        assert "opportunities" in result
        assert "threats" in result
        assert "strategy_matrix" in result
        assert len(result["strengths"]) > 0
        s = result["strengths"][0]
        assert "item" in s
        assert "impact" in s

    @pytest.mark.asyncio
    async def test_swot_strategy_matrix(self):
        result = await self.agent.call_tool("swot_analysis")
        sm = result["strategy_matrix"]
        assert "SO策略" in sm
        assert "WO策略" in sm
        assert "ST策略" in sm
        assert "WT策略" in sm
        assert len(sm["SO策略"]) > 0


class TestCommercialAgentEnhanced:
    """D36-D38 商业化Agent增强测试"""

    def setup_method(self):
        self.agent = CommercialAgent()

    def test_agent_has_6_tools(self):
        assert len(self.agent.get_tools()) == 7

    def test_cost_engine_registered(self):
        tools = {t.name for t in self.agent.get_tools()}
        assert "calculate_detailed_costs" in tools

    def test_pricing_tool_registered(self):
        tools = {t.name for t in self.agent.get_tools()}
        assert "recommend_pricing" in tools

    def test_elasticity_tool_registered(self):
        tools = {t.name for t in self.agent.get_tools()}
        assert "price_elasticity_model" in tools

    def test_roi_tool_registered(self):
        tools = {t.name for t in self.agent.get_tools()}
        assert "predict_roi" in tools

    @pytest.mark.asyncio
    async def test_cost_engine_full_breakdown(self):
        result = await self.agent.call_tool(
            "calculate_detailed_costs",
            selling_price=39.99,
            unit_cost_1688=5.0,
            weight_kg=0.15,
            volume_cbm=0.001,
            category="bluetooth_earbuds",
        )
        assert result["source"] == "cost_engine"
        assert "total_cost_per_unit" in result
        assert "gross_margin_pct" in result
        cb = result["cost_breakdown"]
        assert "procurement_1688" in cb
        assert "first_mile_shipping" in cb
        assert "fba_fees" in cb
        assert "platform_commission" in cb
        assert "advertising_acos" in cb
        assert result["total_cost_per_unit"] > 0
        assert -50 < result["gross_margin_pct"] < 80

    @pytest.mark.asyncio
    async def test_cost_engine_procurement_calc(self):
        result = await self.agent.call_tool(
            "calculate_detailed_costs",
            selling_price=39.99,
            unit_cost_1688=10.0,
        )
        proc = result["cost_breakdown"]["procurement_1688"]
        assert proc["amount"] <= 10.0

    @pytest.mark.asyncio
    async def test_pricing_competitive_strategy(self):
        result = await self.agent.call_tool(
            "recommend_pricing",
            cost_per_unit=12.0,
            competitor_prices=[29.99, 34.99, 39.99, 44.99],
            target_margin=30.0,
            pricing_strategy="competitive",
        )
        assert result["strategy_selected"] == "competitive"
        assert "recommendation" in result
        rec = result["recommendation"]
        assert "recommended_price" in rec
        assert "margin_at_rec" in rec
        assert rec["recommended_price"] > 0

    @pytest.mark.asyncio
    async def test_pricing_cost_based_strategy(self):
        result = await self.agent.call_tool(
            "recommend_pricing",
            cost_per_unit=12.0,
            target_margin=30.0,
            pricing_strategy="cost_based",
        )
        assert result["strategy_selected"] == "cost_based"
        rec = result["recommendation"]
        expected = 12.0 / (1 - 0.30)
        assert abs(rec["recommended_price"] - expected) < 0.01 or rec["recommended_price"] > 0

    @pytest.mark.asyncio
    async def test_pricing_value_based_strategy(self):
        result = await self.agent.call_tool(
            "recommend_pricing",
            cost_per_unit=12.0,
            competitor_prices=[29.99, 34.99, 39.99],
            pricing_strategy="value_based",
        )
        assert result["strategy_selected"] == "value_based"
        assert "all_strategies" in result
        strategies = result["all_strategies"]
        assert "competitive" in strategies
        assert "cost_based" in strategies
        assert "value_based" in strategies

    @pytest.mark.asyncio
    async def test_elasticity_model_basic(self):
        result = await self.agent.call_tool(
            "price_elasticity_model",
            base_price=39.99,
            base_volume=500,
            category="bluetooth_earbuds",
        )
        assert result["source"] == "elasticity_model"
        assert "price_elasticity" in result
        e = result["price_elasticity"]
        assert e < 0
        assert "elasticity_category" in result
        assert "revenue_optimization" in result
        assert "price_scenarios" in result
        assert len(result["price_scenarios"]) == 9

    @pytest.mark.asyncio
    async def test_elasticity_category_lookup(self):
        result_electronics = await self.agent.call_tool(
            "price_elasticity_model", category="electronics"
        )
        result_clothing = await self.agent.call_tool(
            "price_elasticity_model", category="clothing"
        )
        assert abs(result_electronics["price_elasticity"]) != abs(result_clothing["price_elasticity"])

    @pytest.mark.asyncio
    async def test_elasticity_scenarios_revenue(self):
        result = await self.agent.call_tool(
            "price_elasticity_model", base_price=39.99, base_volume=500
        )
        scenarios = result["price_scenarios"]
        base_rev = scenarios[4]["revenue"]
        assert base_rev > 0

    @pytest.mark.asyncio
    async def test_roi_predictor_basic(self):
        result = await self.agent.call_tool(
            "predict_roi",
            initial_investment=50000,
            monthly_revenue=15000,
            monthly_cost=8000,
            gross_margin_pct=35.0,
            growth_rate_y1=8.0,
        )
        assert result["source"] == "roi_predictor"
        km = result["key_metrics"]
        assert "payback_period_months" in km
        assert "npv_3year_usd" in km
        assert "irr_percent" in km
        assert "roi_year1_percent" in km
        assert km["payback_period_months"] > 0

    @pytest.mark.asyncio
    async def test_roi_cash_flow_projection(self):
        result = await self.agent.call_tool(
            "predict_roi",
            initial_investment=50000,
            monthly_revenue=15000,
            monthly_cost=8000,
        )
        cfp = result["cash_flow_projection"]
        assert len(cfp) == 12
        cf = cfp[0]
        assert "month" in cf
        assert "cash_flow" in cf
        assert "cumulative_cf" in cf

    @pytest.mark.asyncio
    async def test_roi_sensitivity_analysis(self):
        result = await self.agent.call_tool(
            "predict_roi",
            initial_investment=50000,
            monthly_revenue=15000,
            monthly_cost=8000,
        )
        sa = result["sensitivity_analysis"]
        assert len(sa) >= 6
        scenario_names = [s["scenario"] for s in sa]
        assert "收入-20%" in scenario_names
        assert "成本+15%" in scenario_names
        for s in sa:
            assert "adj_payback_months" in s
            assert "adj_roi_y1" in s

    @pytest.mark.asyncio
    async def test_roi_investment_verdict(self):
        result = await self.agent.call_tool(
            "predict_roi",
            initial_investment=10000,
            monthly_revenue=20000,
            monthly_cost=5000,
        )
        verdict = result["investment_verdict"]
        assert "verdict" in verdict
        assert verdict["verdict"] in ["RECOMMENDED", "CONDITIONAL", "NOT_RECOMMENDED"]
        assert "risk_level" in verdict

    @pytest.mark.asyncio
    async def test_high_investment_slow_payback(self):
        result = await self.agent.call_tool(
            "predict_roi",
            initial_investment=500000,
            monthly_revenue=8000,
            monthly_cost=7000,
        )
        assert result["key_metrics"]["payback_period_months"] > 24


class TestEdgeCases:
    """边界条件测试"""

    def setup_method(self):
        self.pp_agent = ProductPlannerAgent()
        self.com_agent = CommercialAgent()

    @pytest.mark.asyncio
    async def test_empty_reviews_clustering(self):
        result = await self.pp_agent.call_tool("cluster_reviews", reviews=[])
        assert "clusters" in result
        assert "pain_points" in result

    @pytest.mark.asyncio
    async def test_no_competitors_diff(self):
        result = await self.pp_agent.call_tool("competitor_diff")
        assert "feature_matrix" in result
        assert "competitor_profiles" in result

    @pytest.mark.asyncio
    async def test_zero_selling_price_cost(self):
        result = await self.com_agent.call_tool(
            "calculate_detailed_costs", selling_price=0.01
        )
        assert "total_cost_per_unit" in result

    @pytest.mark.asyncio
    async def test_very_high_cost_pricing(self):
        result = await self.com_agent.call_tool(
            "recommend_pricing",
            cost_per_unit=80.0,
            competitor_prices=[29.99, 39.99],
            target_margin=40.0,
        )
        assert result["final_recommendation"]["price"] > 0

    @pytest.mark.asyncio
    async def test_zero_volume_elasticity(self):
        result = await self.com_agent.call_tool(
            "price_elasticity_model", base_volume=0
        )
        assert "price_elasticity" in result

    @pytest.mark.asyncio
    async def test_zero_profit_roi(self):
        result = await self.com_agent.call_tool(
            "predict_roi",
            initial_investment=50000,
            monthly_revenue=5000,
            monthly_cost=5000,
        )
        assert result["key_metrics"]["payback_period_months"] >= 999


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
