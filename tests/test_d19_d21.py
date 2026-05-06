"""
D19-D21 单元测试: 产品规划Agent + Selection Master状态机
=========================================================

覆盖:
    - D19-T055: ProductPlannerAgent产品规划
    - D20-T056: 产品规格/供应链/成本/差异化
    - D21-T058/T059: Selection Master状态机
    - D22-T063: 状态流转与条件分支

执行:
    pytest tests/test_d19_d21.py -v
"""

import asyncio

import pytest


class TestProductPlannerAgent:
    """
    ProductPlannerAgent测试(D19-T055)。

    验证:
        - 产品规格生成(功能/参数/定位)
        - 供应链可行性评估
        - 成本结构与利润率分析
        - 差异化评分(四维度)
        - 多方案推荐与排序
        - 输入校验
        - 完整执行流程
    """

    def test_agent_creation(self):
        """ProductPlannerAgent应可正常创建。"""
        from src.agents.product_planner import ProductPlannerAgent

        agent = ProductPlannerAgent()

        assert agent.name == "product_planner"
        assert len(agent.get_tools()) >= 3

    def test_required_input_keys(self):
        """应定义必填字段query+category。"""
        from src.agents.product_planner import ProductPlannerAgent

        assert {"query", "category"} == ProductPlannerAgent.REQUIRED_INPUT_KEYS

    def test_missing_category_fails(self):
        """缺少category应导致失败。"""
        from src.agents.product_planner import ProductPlannerAgent

        agent = ProductPlannerAgent()
        result = asyncio.run(agent.run({"query": "设计产品"}))

        assert result.success is False
        assert "category" in result.error

    def test_full_execution(self):
        """完整执行应返回结构化规划结果。"""
        from src.agents.product_planner import ProductPlannerAgent

        agent = ProductPlannerAgent()
        result = asyncio.run(agent.run({
            "query": "设计一款无线蓝牙耳机",
            "category": "bluetooth_earbuds",
            "target_market": "US",
            "budget_range": [25, 65],
        }))

        assert result.success is True
        data = result.output["data"]

        assert "product_spec" in data
        assert "supply_chain" in data
        assert "cost_structure" in data
        assert "differentiation" in data
        assert "recommendations" in data

    def test_product_spec_structure(self):
        """产品规格应包含完整字段。"""
        from src.agents.product_planner import ProductPlannerAgent

        agent = ProductPlannerAgent()
        result = asyncio.run(agent.run({
            "query": "test product",
            "category": "electronics",
            "budget_range": [30, 80],
        }))

        spec = result.output["data"]["product_spec"]

        assert "name" in spec
        assert "target_price" in spec
        assert "core_features" in spec
        assert "positioning" in spec
        assert spec["positioning"] in {"budget", "mid-range", "premium"}

    def test_supply_chain_assessment(self):
        """供应链评估应包含风险等级。"""
        from src.agents.product_planner import ProductPlannerAgent

        agent = ProductPlannerAgent()
        result = asyncio.run(agent.run({
            "query": "supply chain test",
            "category": "cat",
            "budget_range": [10, 50],
        }))

        supply = result.output["data"]["supply_chain"]

        assert "risk_level" in supply
        assert supply["risk_level"] in {"low", "medium", "high"}
        assert "lead_time_days" in supply
        assert "moq" in supply

    def test_cost_structure_margins(self):
        """成本结构应包含毛利率和ROI。"""
        from src.agents.product_planner import ProductPlannerAgent

        agent = ProductPlannerAgent()
        result = asyncio.run(agent.run({
            "query": "cost analysis",
            "category": "cat",
            "budget_range": [20, 60],
        }))

        costs = result.output["data"]["cost_structure"]

        assert "gross_margin" in costs
        assert "roi_estimate" in costs
        assert "cost_breakdown" in costs

    def test_differentiation_score(self):
        """差异化评分应在合理范围内。"""
        from src.agents.product_planner import ProductPlannerAgent

        agent = ProductPlannerAgent()
        result = asyncio.run(agent.run({
            "query": "diff score test",
            "category": "cat",
            "budget_range": [15, 55],
        }))

        diff = result.output["data"]["differentiation"]

        overall = diff.get("overall_score", 0)
        assert 0 <= overall <= 100

    def test_recommendations_generated(self):
        """应生成多个推荐方案并排序。"""
        from src.agents.product_planner import ProductPlannerAgent

        agent = ProductPlannerAgent()
        result = asyncio.run(agent.run({
            "query": "rec test",
            "category": "cat",
            "budget_range": [20, 70],
        }))

        recs = result.output["data"]["recommendations"]

        assert isinstance(recs, list)
        assert len(recs) >= 2

        ranks = [r.get("rank") for r in recs]
        assert sorted(ranks) == ranks

    def test_output_has_summary(self):
        """输出应包含摘要。"""
        from src.agents.product_planner import ProductPlannerAgent

        agent = ProductPlannerAgent()
        result = asyncio.run(agent.run({
            "query": "summary test",
            "category": "cat",
            "budget_range": [10, 100],
        }))

        summary = result.output.get("summary")

        assert summary is not None
        assert len(summary) > 5


class TestDataModelsProductPlanner:
    """
    产品规划数据模型测试。
    """

    def test_product_spec_to_dict(self):
        """ProductSpec.to_dict()应返回完整字典。"""
        from src.agents.product_planner import ProductSpec

        spec = ProductSpec(
            name="Test Earbuds Pro",
            category="audio",
            target_price=(29.99, 59.99),
            core_features=["ANC", "Bluetooth 5.3"],
            positioning="mid-range",
        )

        d = spec.to_dict()

        assert d["name"] == "Test Earbuds Pro"
        assert "$" in d["target_price"]

    def test_supply_chain_to_dict(self):
        """SupplyChainAssessment.to_dict()应包含风险等级。"""
        from src.agents.product_planner import SupplyChainAssessment

        s = SupplyChainAssessment(
            risk_level="low",
            lead_time_days=21,
            moq=300,
        )

        d = s.to_dict()

        assert d["risk_level"] == "low"

    def test_cost_structure_to_dict(self):
        """CostStructure.to_dict()应格式化金额。"""
        from src.agents.product_planner import CostStructure

        c = CostStructure(
            unit_cost_usd=12.50,
            fob_price=13.50,
            landed_cost=16.00,
            gross_margin=35.0,
            roi_estimate=52.5,
        )

        d = c.to_dict()

        assert "$" in d["unit_cost"]
        assert "%" in d["gross_margin"]

    def test_differentiation_score_to_dict(self):
        """DifferentiationScore.to_dict()应包含四维度得分。"""
        from src.agents.product_planner import DifferentiationScore

        d = DifferentiationScore(
            overall=72.5,
            feature_uniqueness=18,
            quality_perception=20,
            price_competitiveness=17,
            brand_potential=17.5,
        )

        result = d.to_dict()

        assert result["overall_score"] == 72.5
        assert len(result) >= 7

    def test_product_recommendation_to_dict(self):
        """ProductRecommendation.to_dict()应包含完整字段。"""
        from src.agents.product_planner import ProductRecommendation

        r = ProductRecommendation(
            rank=1,
            product_name="Premium Earbuds",
            confidence=85.5,
            expected_roi=45.0,
            time_to_market=10,
            risk_rating=2,
            pros=["高利润"],
            cons=["竞争激烈"],
        )

        d = r.to_dict()

        assert d["rank"] == 1
        assert "⭐" in d["risk_rating"]


class TestSelectionMaster:
    """
    Selection Master状态机测试(D21-T058/T059)。

    验证:
        - SelectionState创建与管理
        - 完整流程执行(4阶段)
        - 条件边路由(abort/retry/revise)
        - 重试机制(max_retries限制)
        - 执行日志记录
        - Go/No-Go决策输出
    """

    def test_selection_master_creation(self):
        """SelectionMaster应可正常创建。"""
        from src.agents.selection_master import SelectionMaster

        master = SelectionMaster()

        assert master is not None
        assert len(master._phase_handlers) >= 4

    def test_selection_state_creation(self):
        """SelectionState应自动生成session_id和时间戳。"""
        from src.agents.selection_master import SelectionState

        state = SelectionState(query="test query", category="test_cat")

        assert state.session_id != ""
        assert state.created_at != ""
        assert state.current_phase.value == "start"

    def test_state_to_dict(self):
        """SelectionState.to_dict()应返回结构化字典。"""
        from src.agents.selection_master import SelectionState

        state = SelectionState(query="test", category="cat")

        d = state.to_dict()

        assert "session_id" in d
        assert "current_phase" in d
        assert "status" in d
        assert "retry_count" in d

    def test_state_log_error(self):
        """log_error()应正确记录错误。"""
        from src.agents.selection_master import SelectionState

        state = SelectionState()
        state.log_error("test_phase", "模拟错误", {"code": 500})

        assert len(state.error_log) == 1
        assert state.error_log[0]["phase"] == "test_phase"
        assert state.error_log[0]["message"] == "模拟错误"

    def test_full_flow_execution(self):
        """完整4阶段流程应成功完成。"""
        from src.agents.selection_master import SelectionMaster

        master = SelectionMaster()
        result = asyncio.run(master.run({
            "query": "蓝牙耳机选品分析",
            "category": "bluetooth_earbuds",
            "target_market": "US",
            "budget_range": [20, 60],
        }))

        assert result["status"] == "proceed"
        assert result["final_phase"] == "completed"
        assert len(result["execution_log"]) >= 4

    def test_results_populated(self):
        """各阶段结果应被填充到results字典中。"""
        from src.agents.selection_master import SelectionMaster

        master = SelectionMaster()
        result = asyncio.run(master.run({
            "query": "flow test",
            "category": "cat",
        }))

        results = result["results"]

        assert "data_collection" in results
        assert "market_analysis" in results
        assert "product_planning" in results
        assert "commercial_evaluation" in results

    def test_go_no_go_decision(self):
        """最终应输出Go/No-Go决策。"""
        from src.agents.selection_master import SelectionMaster

        master = SelectionMaster()
        result = asyncio.run(master.run({
            "query": "go no go test",
            "category": "cat",
        }))

        assert "go_no_go_decision" in result
        valid_decisions = {"GO", "CONDITIONAL_GO", "NO_GO"}
        assert result["go_no_go_decision"] in valid_decisions

    def test_summary_generated(self):
        """应生成自然语言摘要。"""
        from src.agents.selection_master import SelectionMaster

        master = SelectionMaster()
        result = asyncio.run(master.run({
            "query": "summary test",
            "category": "cat",
        }))

        summary = result.get("summary")

        assert summary is not None
        assert len(summary) > 20
        assert "选品流程报告" in summary

    def test_session_id_persisted(self):
        """session_id应在整个流程中保持一致。"""
        from src.agents.selection_master import SelectionMaster

        master = SelectionMaster()
        result = asyncio.run(master.run({
            "query": "session test",
            "category": "cat",
        }))

        assert result["session_id"] == result["state_summary"]["session_id"]

    def test_phase_enums(self):
        """SelectionPhase枚举应包含所有必要阶段。"""
        from src.agents.selection_master import SelectionPhase

        phases = [p.value for p in SelectionPhase]

        assert "start" in phases
        assert "data_collection" in phases
        assert "market_analysis" in phases
        assert "product_planning" in phases
        assert "commercial_evaluation" in phases
        assert "completed" in phases
        assert "failed" in phases

    def test_status_enums(self):
        """SelectionStatus枚举应包含所有流转状态。"""
        from src.agents.selection_master import SelectionStatus

        statuses = [s.value for s in SelectionStatus]

        assert "proceed" in statuses
        assert "retry_data" in statuses
        assert "abort_market" in statuses
        assert "revise_product" in statuses
        assert "terminate" in statuses

    def test_transition_result_creation(self):
        """TransitionResult应可正常创建。"""
        from src.agents.selection_master import SelectionPhase, SelectionStatus, TransitionResult

        tr = TransitionResult(
            success=True,
            next_phase=SelectionPhase.PRODUCT_PLANNING,
            status=SelectionStatus.PROCEED,
            output={"key": "value"},
        )

        assert tr.success is True
        assert tr.should_terminate is False


class TestModuleImportsD19D21:
    """
    模块导入测试(D19-D21)。
    """

    def test_product_planner_importable(self):
        """ProductPlannerAgent及其数据模型应可导入。"""
        from src.agents import (
            ProductPlannerAgent,
            create_product_planner_agent,
        )

        assert ProductPlannerAgent is not None
        assert callable(create_product_planner_agent)

    def test_selection_master_importable(self):
        """SelectionMaster及其组件应可导入。"""
        from src.agents import (
            SelectionMaster,
            create_selection_master,
        )

        assert SelectionMaster is not None
        assert callable(create_selection_master)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
