"""
Agent 单元测试
=============

覆盖:
1. BaseAgent 生命周期 (PENDING → RUNNING → COMPLETED)
2. BaseAgent 工具注册与调用
3. SelectionMaster 完整流程 (mock 模式)
4. SelectionMaster 条件分支 (重试 / 终止 / 修订)
5. SelectionState 错误日志与时间戳

不依赖外部服务 (DB / Redis / LLM)。
"""

from typing import Any

import pytest
from src.agents import langgraph_compatible as langgraph_module
from src.agents.base import AgentStatus, AgentTool, AgentType, BaseAgent
from src.agents.langgraph_compatible import LangGraphCompatibleRunner
from src.agents.selection_master import (
    SelectionMaster,
    SelectionPhase,
    SelectionState,
    SelectionStatus,
    TransitionResult,
)

# ---------------------------------------------------------------------------
# 辅助 fixtures / helpers
# ---------------------------------------------------------------------------


class DummyAgent(BaseAgent):
    """用于测试的简易 Agent，不调用任何外部服务。"""

    name = "dummy"
    agent_type = AgentType.DATA_COLLECTOR

    async def execute(self, input_data: dict) -> dict:
        return {"echo": input_data.get("query", ""), "status": "ok"}


class FailingAgent(BaseAgent):
    """执行时必然抛异常的 Agent。"""

    name = "failing"
    agent_type = AgentType.DATA_COLLECTOR

    async def execute(self, input_data: dict) -> dict:
        raise RuntimeError("模拟执行失败")


# ---------------------------------------------------------------------------
# 1. BaseAgent 生命周期
# ---------------------------------------------------------------------------


class _FakeAgentResult:
    def __init__(self, data: dict[str, Any]):
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return {"success": True, "output": {"data": self._data}}


@pytest.mark.asyncio
async def test_agent_lifecycle_pending_to_completed():
    """测试 Agent 正常执行: PENDING → RUNNING → COMPLETED。"""
    agent = DummyAgent()
    assert agent.status == AgentStatus.PENDING

    result = await agent.run({"query": "test"})

    assert agent.status == AgentStatus.COMPLETED
    assert result.success is True
    assert result.output is not None
    assert result.execution_time_ms >= 0


@pytest.mark.asyncio
async def test_agent_lifecycle_pending_to_failed():
    """测试 Agent 执行失败: PENDING → RUNNING → FAILED。"""
    agent = FailingAgent()
    assert agent.status == AgentStatus.PENDING

    result = await agent.run({"query": "test"})

    assert agent.status == AgentStatus.FAILED
    assert result.success is False
    assert "模拟执行失败" in (result.error or "")


@pytest.mark.asyncio
async def test_agent_invalid_input():
    """测试输入校验: 非 dict 输入 → FAILED。"""
    agent = DummyAgent()
    result = await agent.run("not a dict")  # type: ignore[arg-type]

    assert result.success is False
    assert "dict" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# 2. 工具注册与调用
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_registration_and_listing():
    """测试工具注册后可通过 get_tools / get_tool_names 获取。"""
    agent = DummyAgent()

    tool = AgentTool(
        name="my_tool",
        description="a test tool",
        func=lambda x=1: x * 2,
        parameters={"x": {"type": "number"}},
    )
    agent.register_tool(tool)

    assert "my_tool" in agent.get_tool_names()
    assert len(agent.get_tools()) == 1


@pytest.mark.asyncio
async def test_call_registered_tool():
    """测试通过 call_tool 调用已注册的工具。"""
    agent = DummyAgent()

    async def add_async(a: int = 0, b: int = 0):
        return a + b

    agent.register_tool(AgentTool(name="add", description="add two numbers", func=add_async))

    result = await agent.call_tool("add", a=3, b=7)
    assert result == 10


@pytest.mark.asyncio
async def test_call_unregistered_tool_raises():
    """测试调用未注册工具 → KeyError。"""
    agent = DummyAgent()
    with pytest.raises(KeyError, match="not_exist"):
        await agent.call_tool("not_exist")


# ---------------------------------------------------------------------------
# 3. SelectionMaster 完整流程 (使用 mock handler)
# ---------------------------------------------------------------------------


def _build_mock_master() -> SelectionMaster:
    """构建纯 mock handler 的 SelectionMaster，不依赖真实 Agent。"""
    master = SelectionMaster.__new__(SelectionMaster)
    master.config = {"force_legacy": True}
    master._phase_handlers = {}
    master._condition_checkers = {}
    master.MAX_RETRIES = 3

    async def h_data(state):
        state.current_phase = SelectionPhase.DATA_COLLECTION
        return TransitionResult(
            success=True,
            next_phase=SelectionPhase.MARKET_ANALYSIS,
            output={
                "quality_score": 0.85,
                "products_collected": 50,
                "quality_report": {"validity_rate": 0.85, "is_acceptable": True, "sources_checked": ["amazon"]},
                "amazon_data": {
                    "items": 50,
                    "mode": "real",
                    "signal_context": {"provider": "external_signal_service", "source_name": "amazon", "source_channel": "public_web_signal"},
                    "signal_readiness": {"local_business_ready": True, "enterprise_ready": False, "readiness_tier": "local_business_ready"},
                },
                "external_signal_summary": {
                    "has_external_signal_fallbacks": True,
                    "fallback_tool_count": 1,
                    "fallback_business_sources": ["amazon"],
                    "local_validation_only_sources": ["amazon"],
                },
            },
        )

    async def h_market(state):
        state.current_phase = SelectionPhase.MARKET_ANALYSIS
        return TransitionResult(
            success=True,
            next_phase=SelectionPhase.PRODUCT_PLANNING,
            output={
                "opportunity_score": {"overall_score": 72.0, "recommendation": "recommend", "risk_factors": ["价格竞争"]},
                "trends": {"direction": "up", "strength": 82, "confidence": 76, "description": "趋势上行"},
            },
        )

    async def h_product(state):
        state.current_phase = SelectionPhase.PRODUCT_PLANNING
        return TransitionResult(
            success=True,
            next_phase=SelectionPhase.COMMERCIAL_EVALUATION,
            output={
                "differentiation_score": 68.0,
                "product_name": "Smart Pro",
                "product_spec": {
                    "name": "Smart Pro",
                    "target_price": "$29.99 - $39.99",
                    "positioning": "mid-range",
                    "core_features": ["ANC", "长续航"],
                    "selling_points": ["轻量化", "高性价比"],
                },
                "supply_chain": {"supplier_count": 3, "lead_time_days": 20, "risk_level": "medium"},
                "top_recommendation": {"product_name": "Smart Pro", "confidence": 83.0, "expected_roi": "45.2%", "pros": ["市场有增长", "利润健康"]},
            },
        )

    async def h_commercial(state):
        state.current_phase = SelectionPhase.COMMERCIAL_EVALUATION
        return TransitionResult(
            success=True,
            next_phase=SelectionPhase.COMPLETED,
            output={
                "go_no_go": {"decision": "GO", "confidence": 88.0, "score": 81.0, "recommendation": "建议推进"},
                "financial_projection": {"gross_margin": "35.0%", "net_margin": "18.0%", "ltv_cac_ratio": 2.4},
                "risk_assessment": {"top_risks": [{"name": "价格竞争", "category": "market", "score": 45}]},
                "pricing_suggestion": {"recommended_price": 34.99, "pricing_strategy": "competitive"},
            },
        )

    master.register_phase_handler(SelectionPhase.DATA_COLLECTION, h_data)
    master.register_phase_handler(SelectionPhase.MARKET_ANALYSIS, h_market)
    master.register_phase_handler(SelectionPhase.PRODUCT_PLANNING, h_product)
    master.register_phase_handler(SelectionPhase.COMMERCIAL_EVALUATION, h_commercial)
    return master


@pytest.mark.asyncio
async def test_selection_master_full_flow():
    """测试 SelectionMaster 4 阶段顺序执行到 COMPLETED。"""
    master = _build_mock_master()
    result = await master.run({"query": "蓝牙耳机", "category": "bluetooth_earbuds"})

    assert result["status"] == "proceed"
    assert result["final_phase"] == "completed"
    assert result["results"]["data_collection"]["quality_score"] == 0.85
    assert result["results"]["commercial_evaluation"]["go_no_go"]["decision"] == "GO"
    assert result["go_no_go"]["decision"] == "GO"
    assert result["decision_output"]["decision"]["decision"] == "GO"
    assert result["decision_output"]["evidence_sources"]
    assert result["decision_output"]["data_source_governance"]["governance_status"] == "local_validation_only"
    assert result["decision_output"]["data_source_governance"]["source_readiness"]["amazon"]["business_interpretation"] == "local_validation_only"
    assert result["decision_output"]["quality_summary"]["signal_governance_status"] == "local_validation_only"
    assert result["decision_output"]["pricing"]["target_price_range"] == [29.99, 39.99]
    assert "信号治理:" in result["summary"]
    assert "本地验证来源:" in result["summary"]


# ---------------------------------------------------------------------------
# 4. 条件分支: 重试 / 终止 / 修订
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_selection_master_retry_data():
    """数据不足时重试, 最多 3 次后终止。"""
    master = SelectionMaster.__new__(SelectionMaster)
    master.config = {"force_legacy": True}
    master._phase_handlers = {}
    master._condition_checkers = {}
    master.MAX_RETRIES = 3

    call_count = 0

    async def h_data_fail(state):
        nonlocal call_count
        call_count += 1
        state.current_phase = SelectionPhase.DATA_COLLECTION
        return TransitionResult(
            success=False,
            status=SelectionStatus.RETRY_DATA,
            error_message="数据不足",
        )

    master.register_phase_handler(SelectionPhase.DATA_COLLECTION, h_data_fail)

    result = await master.run({"query": "test", "category": "test"})

    assert call_count >= 3
    assert result["status"] == "terminate"


@pytest.mark.asyncio
async def test_selection_master_abort_market():
    """市场不良时终止流程, 状态为 abort_market。"""
    master = _build_mock_master()

    async def h_market_bad(state):
        state.current_phase = SelectionPhase.MARKET_ANALYSIS
        return TransitionResult(
            success=True,
            status=SelectionStatus.ABORT_MARKET,
            should_terminate=True,
            error_message="市场机会评分过低",
        )

    master.register_phase_handler(SelectionPhase.MARKET_ANALYSIS, h_market_bad)

    result = await master.run({"query": "test", "category": "test"})

    assert result["status"] == "abort_market"
    assert result["final_phase"] != "completed"


@pytest.mark.asyncio
async def test_selection_master_revise_product():
    """产品差异化不足时, 回到产品规划阶段修订, 最终可完成。"""
    master = _build_mock_master()
    revise_count = 0

    async def h_product_revise(state):
        nonlocal revise_count
        state.current_phase = SelectionPhase.PRODUCT_PLANNING
        revise_count += 1
        if revise_count <= 1:
            return TransitionResult(
                success=True,
                status=SelectionStatus.REVISE_PRODUCT,
                next_phase=SelectionPhase.PRODUCT_PLANNING,
                error_message="差异化不足",
            )
        return TransitionResult(
            success=True,
            next_phase=SelectionPhase.COMMERCIAL_EVALUATION,
            output={"differentiation_score": 75, "product_name": "Revised Pro"},
        )

    master.register_phase_handler(SelectionPhase.PRODUCT_PLANNING, h_product_revise)

    result = await master.run({"query": "test", "category": "test"})

    assert revise_count == 2
    assert result["results"]["product_planning"]["differentiation_score"] == 75


# ---------------------------------------------------------------------------
# 5. LangGraphCompatibleRunner business gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_langgraph_runner_aborts_low_market_opportunity(monkeypatch):
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeKnowledgeService:
        async def query_selection_cases(self, query: str, top_k: int, threshold: float) -> dict[str, Any]:
            return {
                "query": query,
                "case_type": "selection_history_case",
                "total_found": 1,
                "processing_time_ms": 1.0,
                "results": [
                    {
                        "source": "selection_case_demo.md",
                        "score": 0.91,
                        "content": "historical selection case",
                        "metadata": {"source": "selection_case_demo.md"},
                    }
                ],
            }

        async def query_review_cases(self, query: str, top_k: int, threshold: float) -> dict[str, Any]:
            return {
                "query": query,
                "case_type": "crm_review_case",
                "total_found": 1,
                "processing_time_ms": 1.0,
                "results": [
                    {
                        "source": "crm_review_demo.md",
                        "score": 0.78,
                        "content": "customer complaint pattern",
                        "metadata": {"source": "crm_review_demo.md"},
                    }
                ],
            }

    def build_agent(name: str, payload: dict[str, Any]):
        class _Agent:
            async def run(self, input_data: dict[str, Any]):
                calls.append((name, input_data))
                return _FakeAgentResult(payload)

        return _Agent

    def unexpected_agent(name: str):
        class _Agent:
            def __init__(self, config: dict[str, Any] | None = None):
                self.config = config or {}

            async def run(self, input_data: dict[str, Any]):
                raise AssertionError(f"{name} should not run for low market opportunity")

        return _Agent

    monkeypatch.setattr(langgraph_module, "LocalKnowledgeService", FakeKnowledgeService)
    monkeypatch.setattr(
        langgraph_module,
        "DataCollectionAgent",
        build_agent("data_collection", {"quality_report": {"validity_rate": 0.9}}),
    )
    monkeypatch.setattr(
        langgraph_module,
        "MarketInsightAgent",
        build_agent(
            "market_analysis",
            {
                "opportunity_score": {"overall_score": 12.0, "recommendation": "abort"},
                "trends": {"direction": "down"},
            },
        ),
    )
    monkeypatch.setattr(langgraph_module, "ProductPlannerAgent", unexpected_agent("product_planning"))
    monkeypatch.setattr(langgraph_module, "CommercialAgent", unexpected_agent("commercial_evaluation"))
    monkeypatch.setattr(langgraph_module, "RiskAssessorAgent", unexpected_agent("risk_assessment"))
    monkeypatch.setattr(langgraph_module, "ReportGeneratorAgent", unexpected_agent("report_generation"))

    runner = LangGraphCompatibleRunner()
    result = await runner.invoke(
        input_data={"query": "test product", "category": "electronics", "target_market": "US"},
        breakpoints=[],
        single_step=False,
    )

    payload = result["selection_master_output"]
    assert [name for name, _ in calls] == ["data_collection", "market_analysis"]
    assert payload["status"] == "abort_market"
    assert payload["final_phase"] == "market_analysis"
    assert payload["results"]["product_planning"] == {}
    assert payload["historical_context"]["similar_history_cases"]["total_found"] == 1
    assert payload["decision_output"]["historical_case_summary"]["similar_history_case_count"] == 1
    assert payload["decision_output"]["historical_case_summary"]["review_case_count"] == 1
    assert payload["langgraph_execution"]["preloaded_case_evidence_count"] == 2


@pytest.mark.asyncio
async def test_langgraph_runner_revises_product_and_preloads_history(monkeypatch):
    calls: list[tuple[str, dict[str, Any]]] = []
    product_scores = [20.0, 58.0]

    class FakeKnowledgeService:
        async def query_selection_cases(self, query: str, top_k: int, threshold: float) -> dict[str, Any]:
            return {
                "query": query,
                "case_type": "selection_history_case",
                "total_found": 1,
                "processing_time_ms": 1.0,
                "results": [
                    {
                        "source": "selection_case_demo.md",
                        "score": 0.88,
                        "content": "winning bundle design",
                        "metadata": {"source": "selection_case_demo.md"},
                    }
                ],
            }

        async def query_review_cases(self, query: str, top_k: int, threshold: float) -> dict[str, Any]:
            return {
                "query": query,
                "case_type": "crm_review_case",
                "total_found": 1,
                "processing_time_ms": 1.0,
                "results": [
                    {
                        "source": "crm_review_demo.md",
                        "score": 0.81,
                        "content": "customers dislike weak battery life",
                        "metadata": {"source": "crm_review_demo.md"},
                    }
                ],
            }

    class DataAgent:
        async def run(self, input_data: dict[str, Any]):
            calls.append(("data_collection", input_data))
            return _FakeAgentResult({"quality_report": {"validity_rate": 0.93}, "amazon_data": {"items": 20}})

    class MarketAgent:
        async def run(self, input_data: dict[str, Any]):
            calls.append(("market_analysis", input_data))
            assert input_data["similar_history_cases"]["total_found"] == 1
            assert input_data["preloaded_case_evidence"]
            return _FakeAgentResult(
                {
                    "opportunity_score": {"overall_score": 68.0, "recommendation": "proceed"},
                    "trends": {"direction": "up"},
                }
            )

    class ProductAgent:
        async def run(self, input_data: dict[str, Any]):
            calls.append(("product_planning", input_data))
            score = product_scores.pop(0)
            assert input_data["market_analysis_result"]["opportunity_score"]["overall_score"] == 68.0
            assert input_data["similar_history_cases"]["total_found"] == 1
            return _FakeAgentResult({"differentiation_score": score, "product_name": f"plan-{score}"})

    class CommercialAgent:
        def __init__(self, config: dict[str, Any] | None = None):
            self.config = config or {}

        async def run(self, input_data: dict[str, Any]):
            calls.append(("commercial_evaluation", input_data))
            assert input_data["product_planning_result"]["differentiation_score"] == 58.0
            assert input_data["review_cases"]["total_found"] == 1
            return _FakeAgentResult(
                {
                    "go_no_go": {"decision": "GO", "confidence": 82.0, "score": 79.0},
                    "financial_projection": {"gross_margin": "35.0%", "net_margin": "18.0%"},
                }
            )

    class RiskAgent:
        async def run(self, input_data: dict[str, Any]):
            calls.append(("risk_assessment", input_data))
            return _FakeAgentResult({"overall_risk_score": 42.0, "risk_level": "medium"})

    class ReportAgent:
        async def run(self, input_data: dict[str, Any]):
            calls.append(("report_generation", input_data))
            assert input_data["agent_results"]["commercial"]["go_no_go"]["decision"] == "GO"
            return _FakeAgentResult({"report_id": "RPT-1", "executive_summary": "ok"})

    monkeypatch.setattr(langgraph_module, "LocalKnowledgeService", FakeKnowledgeService)
    monkeypatch.setattr(langgraph_module, "DataCollectionAgent", DataAgent)
    monkeypatch.setattr(langgraph_module, "MarketInsightAgent", MarketAgent)
    monkeypatch.setattr(langgraph_module, "ProductPlannerAgent", ProductAgent)
    monkeypatch.setattr(langgraph_module, "CommercialAgent", CommercialAgent)
    monkeypatch.setattr(langgraph_module, "RiskAssessorAgent", RiskAgent)
    monkeypatch.setattr(langgraph_module, "ReportGeneratorAgent", ReportAgent)

    runner = LangGraphCompatibleRunner()
    result = await runner.invoke(
        input_data={"query": "smart bottle", "category": "home", "target_market": "US"},
        breakpoints=[],
        single_step=False,
    )

    payload = result["selection_master_output"]
    product_calls = [item for item in calls if item[0] == "product_planning"]
    assert len(product_calls) == 2
    assert payload["status"] == "proceed"
    assert payload["final_phase"] == "completed"
    assert payload["results"]["product_planning"]["differentiation_score"] == 58.0
    assert payload["state_summary"]["product_revision_count"] == 1
    assert any(entry["status"] == "revise_product" for entry in payload["execution_log"])
    assert payload["decision_output"]["historical_case_summary"]["similar_history_case_count"] == 1
    assert payload["decision_output"]["historical_case_summary"]["review_case_count"] == 1
    assert payload["langgraph_execution"]["historical_context_loaded"] is True
    assert payload["langgraph_execution"]["preloaded_case_evidence_count"] == 2


# ---------------------------------------------------------------------------
# 5. SelectionState 错误日志与时间戳
# ---------------------------------------------------------------------------


def test_selection_state_error_logging():
    """测试 SelectionState.log_error 正确记录错误。"""
    state = SelectionState(query="test", category="test")

    state.log_error("data_collection", "采集失败", {"source": "amazon"})
    state.log_error("market_analysis", "评分异常")

    assert len(state.error_log) == 2
    assert state.error_log[0]["phase"] == "data_collection"
    assert state.error_log[0]["details"]["source"] == "amazon"
    assert state.error_log[1]["message"] == "评分异常"


def test_selection_state_timestamps():
    """测试 SelectionState 的 session_id / created_at / updated_at 自动初始化。"""
    state = SelectionState(query="test", category="test")

    assert state.session_id != ""
    assert state.created_at != ""
    assert state.updated_at != ""

    old_updated = state.updated_at
    state._touch()
    assert state.updated_at >= old_updated


def test_selection_state_to_dict():
    """测试 SelectionState.to_dict() 包含关键字段。"""
    state = SelectionState(query="test", category="earbuds", target_market="US")
    d = state.to_dict()

    assert d["query"] == "test"
    assert d["category"] == "earbuds"
    assert d["target_market"] == "US"
    assert "session_id" in d
    assert "current_phase" in d
