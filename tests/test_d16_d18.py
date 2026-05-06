"""
D16-D18 单元测试: Agent框架 + 市场洞察Agent + Demo API
========================================================

覆盖:
    - D16-T053: Agent基类与生命周期
    - D16-T053: MarketInsightAgent市场分析
    - D17-T054: Agent工具注册与调用
    - D18: Kong/ES配置验证

执行:
    pytest tests/test_d16_d18.py -v
"""

import asyncio

import pytest


class TestBaseAgent:
    """
    BaseAgent基类测试(D16-T053)。

    验证:
        - Agent创建与属性
        - 工具注册与管理
        - 生命周期(run/initialize/validate)
        - 步骤追踪
        - 状态转换
        - 输入校验
    """

    def test_agent_creation(self):
        """BaseAgent应可正常创建。"""
        from src.agents.base import BaseAgent

        agent = BaseAgent()

        assert agent.name == "base_agent"
        assert agent.status.value == "pending"
        assert agent.agent_id is not None

    def test_agent_has_uuid(self):
        """agent_id应为有效UUID格式。"""
        import uuid

        from src.agents.base import BaseAgent

        agent = BaseAgent()

        uuid.UUID(agent.agent_id)

    def test_register_tool(self):
        """工具应可正常注册到Agent。"""
        from src.agents.base import AgentTool, BaseAgent

        agent = BaseAgent()

        tool = AgentTool(
            name="test_tool",
            description="测试工具",
            func=lambda x: x * 2,
        )
        agent.register_tool(tool)

        assert "test_tool" in agent.get_tool_names()

    def test_get_tools_returns_list(self):
        """get_tools()应返回工具列表。"""
        from src.agents.base import AgentTool, BaseAgent

        agent = BaseAgent()
        agent.register_tool(AgentTool("t1", "desc1", lambda: None))
        agent.register_tool(AgentTool("t2", "desc2", lambda: None))

        tools = agent.get_tools()

        assert len(tools) == 2

    def test_run_success(self):
        """run()应返回成功结果。"""
        from src.agents.base import BaseAgent

        class SimpleAgent(BaseAgent):
            name = "simple"

            async def execute(self, input_data):
                return {"result": "ok"}

        agent = SimpleAgent()
        result = asyncio.run(agent.run({"query": "test"}))

        assert result.success is True
        assert result.output is not None

    def test_run_records_steps(self):
        """run()应记录执行步骤。"""
        from src.agents.base import BaseAgent

        class StepAgent(BaseAgent):
            name = "step_test"

            async def execute(self, input_data):
                return {"data": input_data}

        agent = StepAgent()
        result = asyncio.run(agent.run({"key": "value"}))

        assert len(result.steps) >= 1
        step_names = [s.step_name for s in result.steps]
        assert "execute" in step_names

    def test_validate_input_requires_dict(self):
        """非dict输入应抛出ValueError。"""
        from src.agents.base import BaseAgent

        agent = BaseAgent()

        with pytest.raises(ValueError, match="dict"):
            asyncio.run(agent.validate_input("not a dict"))

    def test_execute_not_implemented_raises(self):
        """未实现execute方法应抛出NotImplementedError。"""
        from src.agents.base import BaseAgent

        agent = BaseAgent()

        with pytest.raises(NotImplementedError):
            asyncio.run(agent.execute({}))

    def test_call_tool_success(self):
        """call_tool()应正确执行已注册的工具。"""
        from src.agents.base import AgentTool, BaseAgent

        agent = BaseAgent()
        agent.register_tool(AgentTool(
            name="double",
            description="翻倍",
            func=lambda x=5: x * 2,
        ))

        result = asyncio.run(agent.call_tool("double", x=10))

        assert result == 20

    def test_call_unknown_tool_raises(self):
        """调用未注册工具应抛出KeyError。"""
        from src.agents.base import BaseAgent

        agent = BaseAgent()

        with pytest.raises(KeyError, match="未注册"):
            asyncio.run(agent.call_tool("nonexistent"))

    def test_info_property(self):
        """info属性应返回Agent描述信息。"""
        from src.agents.base import BaseAgent

        agent = BaseAgent(config={"model": "gpt-4"})

        info = agent.info

        assert "name" in info
        assert "type" in info
        assert "version" in info
        assert info["status"] == "pending"

    def test_failed_execution_result(self):
        """执行失败应返回success=False的结果。"""
        from src.agents.base import BaseAgent

        class FailingAgent(BaseAgent):
            name = "failing"

            async def execute(self, input_data):
                raise RuntimeError("模拟错误")

        agent = FailingAgent()
        result = asyncio.run(agent.run({}))

        assert result.success is False
        assert result.error is not None


class TestMarketInsightAgent:
    """
    MarketInsightAgent测试(D16-T053)。

    验证:
        - 市场规模估算(TAM/SAM/SOM)
        - 竞品格局分析(HHI集中度)
        - 趋势识别(方向/强度/置信度)
        - 机会评分(四维度加权)
        - 输入校验(query+category必填)
        - 完整执行流程
    """

    def test_agent_creation(self):
        """MarketInsightAgent应可正常创建。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()

        assert agent.name == "market_insight"
        assert len(agent.get_tools()) >= 3

    def test_required_input_keys(self):
        """应定义必填输入字段集合。"""
        from src.agents.market_insight import MarketInsightAgent

        assert {"query", "category"} == MarketInsightAgent.REQUIRED_INPUT_KEYS

    def test_missing_category_raises(self):
        """缺少category应导致执行失败。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()
        result = asyncio.run(agent.run({"query": "蓝牙耳机分析"}))

        assert result.success is False
        assert "category" in result.error

    def test_missing_query_raises(self):
        """缺少query应导致执行失败。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()
        result = asyncio.run(agent.run({"category": "electronics"}))

        assert result.success is False
        assert "query" in result.error

    def test_full_execution(self):
        """完整执行应返回结构化分析结果。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()
        result = asyncio.run(agent.run({
            "query": "无线蓝牙耳机市场分析",
            "category": "bluetooth_earbuds",
        }))

        assert result.success is True
        data = result.output["data"]

        assert "market_size" in data
        assert "competitor_landscape" in data
        assert "opportunity_score" in data
        assert "trends" in data

    def test_opportunity_score_range(self):
        """机会评分应在0-100范围内。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()
        result = asyncio.run(agent.run({
            "query": "test analysis",
            "category": "test_cat",
        }))

        score = result.output["data"]["opportunity_score"]["overall_score"]

        assert 0 <= score <= 100

    def test_recommendation_type(self):
        """推荐等级应为四种之一。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()
        result = asyncio.run(agent.run({
            "query": "analysis",
            "category": "cat",
        }))

        rec = result.output["recommendation"]
        valid_recs = {"strong_recommend", "recommend", "caution", "avoid"}

        assert rec in valid_recs

    def test_competitor_landscape_structure(self):
        """竞品格局应包含完整字段。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()
        result = asyncio.run(agent.run({
            "query": "test",
            "category": "cat",
        }))

        landscape = result.output["data"]["competitor_landscape"]

        assert "total_competitors" in landscape
        assert "HHI" in landscape
        assert "avg_price" in landscape
        assert "entry_barrier" in landscape
        assert "concentration_level" in landscape

    def test_trend_signal_structure(self):
        """趋势信号应包含方向/强度/置信度。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()
        result = asyncio.run(agent.run({
            "query": "test",
            "category": "cat",
        }))

        trends = result.output["data"]["trends"]

        assert trends["direction"] in {"up", "down", "stable", "volatile"}
        assert 0 <= trends["strength"] <= 100
        assert 0 <= trends["confidence"] <= 100

    def test_market_size_tam_sam_som(self):
        """市场规模应满足TAM>=SAM>=SOM。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()
        result = asyncio.run(agent.run({
            "query": "test",
            "category": "cat",
        }))

        market = result.output["data"]["market_size"]

        tam = market.get("tam", 0)
        sam = market.get("sam", 0)
        som = market.get("som", 0)

        assert tam >= sam >= som >= 0

    def test_output_has_summary(self):
        """输出应包含自然语言摘要。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()
        result = asyncio.run(agent.run({
            "query": "test query",
            "category": "test_category",
        }))

        summary = result.output.get("summary")

        assert summary is not None
        assert len(summary) > 10

    def test_execution_time_recorded(self):
        """结果应记录执行时间。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()
        result = asyncio.run(agent.run({
            "query": "timing test",
            "category": "timing",
        }))

        assert result.execution_time_ms > 0

    def test_builtin_tools_registered(self):
        """内置工具(search_products/analyze_pricing/estimate_market_size)应已注册。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()
        tool_names = agent.get_tool_names()

        assert "search_products" in tool_names
        assert "analyze_pricing" in tool_names
        assert "estimate_market_size" in tool_names


class TestDataModels:
    """
    数据模型测试(D16数据结构)。

    验证各数据类的to_dict()序列化能力。
    """

    def test_market_size_estimate_to_dict(self):
        """MarketSizeEstimate.to_dict()应返回完整字典。"""
        from src.agents.market_insight import MarketSizeEstimate

        m = MarketSizeEstimate(
            tam_usd=1e9,
            sam_usd=2e8,
            som_usd=5e7,
            cagr=15.5,
        )

        d = m.to_dict()

        assert "TAM" in d
        assert "$" in d["TAM"]
        assert "CAGR" in d
        assert "%" in d["CAGR"]

    def test_competitor_landscape_to_dict(self):
        """CompetitorLandscape.to_dict()应包含集中度等级。"""
        from src.agents.market_insight import CompetitorLandscape

        c = CompetitorLandscape(
            total_competitors=50,
            market_concentration=1200.0,
            avg_price=45.99,
            price_range=(9.99, 199.99),
        )

        d = c.to_dict()

        assert d["concentration_level"] == "competitive"

    def test_high_concentration(self):
        """高HHI应标记为highly_concentrated。"""
        from src.agents.market_insight import CompetitorLandscape

        c = CompetitorLandscape(market_concentration=3000.0)

        assert c._get_concentration_level() == "highly_concentrated"

    def test_trend_signal_to_dict(self):
        """TrendSignal.to_dict()应包含所有字段。"""
        from src.agents.market_insight import TrendSignal

        t = TrendSignal(
            direction="up",
            strength=80,
            confidence=70,
            description="市场需求增长",
            key_drivers=["消费升级", "技术成熟"],
        )

        d = t.to_dict()

        assert d["direction"] == "up"
        assert len(d["key_drivers"]) == 2

    def test_opportunity_score_to_dict(self):
        """OpportunityScore.to_dict()应包含推荐等级。"""
        from src.agents.market_insight import OpportunityScore

        o = OpportunityScore(
            overall=78.5,
            recommendation="recommend",
            risk_factors=["竞争激烈"],
        )

        d = o.to_dict()

        assert d["overall_score"] == 78.5
        assert d["recommendation"] == "recommend"

    def test_hhi_calculation_basic(self):
        """HHI计算应基于review_count分布。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()

        products = [
            {"review_count": 50000},
            {"review_count": 30000},
            {"review_count": 15000},
            {"review_count": 5000},
        ]

        hhi = agent._calculate_hhi(products)

        assert hhi > 2000

    def test_hhi_uniform_distribution(self):
        """均匀分布的HHI应较低。"""
        from src.agents.market_insight import MarketInsightAgent

        agent = MarketInsightAgent()

        products = [{"review_count": 2500} for _ in range(40)]

        hhi = agent._calculate_hhi(products)

        assert hhi < 500


class TestAgentModuleImports:
    """
    模块导入测试。
    """

    def test_agents_package_importable(self):
        """agents包应导出所有核心组件。"""
        from src.agents import (
            BaseAgent,
            MarketInsightAgent,
            create_market_insight_agent,
        )

        assert BaseAgent is not None
        assert MarketInsightAgent is not None
        assert callable(create_market_insight_agent)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
