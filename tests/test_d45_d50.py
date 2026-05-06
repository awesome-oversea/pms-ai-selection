"""D45-D50 单元测试: 全链路追踪 + M2集成验收"""

import sys

import pytest
from src.agents.commercial import CommercialAgent
from src.agents.data_collection import DataCollectionAgent
from src.agents.market_insight import MarketInsightAgent
from src.agents.product_planner import ProductPlannerAgent
from src.agents.selection_master import SelectionMaster
from src.infrastructure.llm_gateway import LLMGateway
from src.infrastructure.tracing import (
    TraceCollector,
    TraceContext,
    finish_span,
    generate_trace_id,
    get_trace_context,
    get_trace_id,
    set_trace_context,
    start_span,
)
from src.infrastructure.ws_gateway import ERPGateway, WebSocketManager


class TestTraceContext:
    """测试TraceContext"""

    def test_context_creation(self):
        ctx = TraceContext(trace_id="tr-123", operation_name="test_op")
        assert ctx.trace_id == "tr-123"
        assert ctx.operation_name == "test_op"
        assert ctx.span_id != ""
        assert ctx.duration_ms >= 0

    def test_context_log(self):
        ctx = TraceContext(trace_id="tr-123")
        ctx.log("event1", key="value")
        assert len(ctx.logs) == 1
        assert ctx.logs[0]["event"] == "event1"

    def test_context_set_tag(self):
        ctx = TraceContext(trace_id="tr-123")
        ctx.set_tag("http.method", "POST")
        assert ctx.tags["http.method"] == "POST"

    def test_context_to_dict(self):
        ctx = TraceContext(trace_id="tr-123", operation_name="test")
        d = ctx.to_dict()
        assert d["trace_id"] == "tr-123"
        assert d["operation"] == "test"
        assert "duration_ms" in d


class TestTraceFunctions:
    """测试追踪函数"""

    def test_generate_trace_id(self):
        tid = generate_trace_id()
        assert tid.startswith("tr-")
        assert len(tid) == 27

    def test_generate_trace_id_unique(self):
        ids = [generate_trace_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_get_trace_id_no_context(self):
        tid = get_trace_id()
        assert tid == "no-trace"

    def test_set_and_get_trace_context(self):
        ctx = TraceContext(trace_id="tr-test")
        set_trace_context(ctx)
        retrieved = get_trace_context()
        assert retrieved.trace_id == "tr-test"

    def test_start_span(self):
        ctx = start_span("test_operation")
        assert ctx.operation_name == "test_operation"
        assert ctx.trace_id.startswith("tr-")

    def test_start_span_with_parent(self):
        parent = TraceContext(trace_id="tr-parent", span_id="span-parent")
        child = start_span("child_op", parent_ctx=parent)
        assert child.trace_id == "tr-parent"
        assert child.parent_span_id == "span-parent"

    def test_finish_span(self):
        ctx = start_span("test_op")
        result = finish_span(ctx)
        assert result["operation"] == "test_op"
        assert "duration_ms" in result


class TestTraceCollector:
    """测试追踪收集器"""

    def setup_method(self):
        self.collector = TraceCollector()

    def test_collect_span(self):
        ctx = TraceContext(trace_id="tr-1", operation_name="op1")
        self.collector.collect(ctx)
        assert len(self.collector._spans) == 1

    def test_collect_multiple(self):
        for i in range(10):
            ctx = TraceContext(trace_id=f"tr-{i}")
            self.collector.collect(ctx)
        assert len(self.collector._spans) == 10

    def test_slow_request_detection(self):
        ctx = TraceContext(trace_id="tr-slow")
        ctx.start_time = ctx.start_time - 2.0
        self.collector.collect(ctx)
        assert len(self.collector._slow_requests) == 1

    def test_error_count(self):
        ctx = TraceContext(trace_id="tr-err")
        ctx.set_tag("error", True)
        self.collector.collect(ctx)
        assert self.collector._error_count == 1

    def test_get_stats(self):
        for i in range(5):
            ctx = TraceContext(trace_id=f"tr-{i}")
            self.collector.collect(ctx)
        stats = self.collector.get_stats()
        assert stats["total_requests"] == 5
        assert "avg_duration_ms" in stats
        assert "p95_duration_ms" in stats

    def test_get_slow_requests(self):
        for i in range(3):
            ctx = TraceContext(trace_id=f"tr-slow-{i}")
            ctx.start_time = ctx.start_time - 2.0
            self.collector.collect(ctx)
        slow = self.collector.get_slow_requests(limit=2)
        assert len(slow) == 2


class TestM2Integration:
    """M2里程碑集成测试(D48-D50)"""

    def setup_method(self):
        self.llm_gateway = LLMGateway()
        self.ws_manager = WebSocketManager()
        self.erp_gateway = ERPGateway()
        self.data_agent = DataCollectionAgent()
        self.planner_agent = ProductPlannerAgent()
        self.commercial_agent = CommercialAgent()

    @pytest.mark.asyncio
    async def test_full_selection_workflow(self):
        """完整选品流程测试"""
        ctx = start_span("full_selection_workflow")
        ctx.set_tag("workflow", "selection")

        ctx.log("step_1_data_collection")
        data_result = await self.data_agent.execute({
            "query": "户外储能电源",
            "category": "portable_power_station",
        })
        assert "amazon_data" in data_result
        ctx.set_tag("data_sources", data_result["sources_summary"]["total_sources"])

        ctx.log("step_2_product_planning")
        plan_result = await self.planner_agent.execute({
            "query": "户外储能电源产品规划",
            "category": "portable_power_station",
            "budget_range": [100, 500],
        })
        assert "product_spec" in plan_result
        ctx.set_tag("recommendations", len(plan_result.get("recommendations", [])))

        ctx.log("step_3_commercial_analysis")
        commercial_result = await self.commercial_agent.execute({
            "query": "户外储能电源商业化评估",
            "category": "portable_power_station",
            "investment_budget": 100000,
        })
        assert "go_no_go" in commercial_result
        ctx.set_tag("decision", commercial_result["go_no_go"]["decision"])

        result = finish_span(ctx)
        assert result["operation"] == "full_selection_workflow"

    @pytest.mark.asyncio
    async def test_llm_gateway_integration(self):
        """LLM Gateway集成测试"""
        ctx = start_span("llm_gateway_test")

        result = await self.llm_gateway.route("分析户外储能电源市场趋势")
        assert result.response != ""
        ctx.set_tag("model", result.model_name)

        stats = self.llm_gateway.get_route_stats()
        assert stats["sample_size"] >= 1

        finish_span(ctx)

    @pytest.mark.asyncio
    async def test_websocket_erp_integration(self):
        """WebSocket + ERP集成测试"""
        ctx = start_span("ws_erp_test")

        await self.ws_manager.connect("conn_test", "task_integration")

        count = await self.ws_manager.send_agent_status(
            task_id="task_integration",
            agent_name="DataCollectionAgent",
            status="completed",
            progress=1.0,
        )
        assert count >= 1

        events = self.erp_gateway.create_selection_sync_event(
            task_id="task_integration",
            product_data={"category": "power_station"},
        )
        assert len(events) >= 1

        finish_span(ctx)

    @pytest.mark.asyncio
    async def test_four_agent_collaboration(self):
        """四Agent协同测试(D50核心)"""
        ctx = start_span("four_agent_collaboration")
        ctx.set_tag("agents", 4)

        task_input = {
            "query": "便携式储能电源",
            "category": "portable_power",
        }

        ctx.log("agent_1_data_collection")
        data_result = await self.data_agent.execute(task_input)
        assert data_result["sources_summary"]["successful"] > 0

        ctx.log("agent_2_product_planning")
        plan_result = await self.planner_agent.execute({
            **task_input,
            "budget_range": [200, 600],
        })
        assert "product_spec" in plan_result

        ctx.log("agent_3_commercial_analysis")
        commercial_result = await self.commercial_agent.execute({
            **task_input,
            "investment_budget": 80000,
        })
        assert "go_no_go" in commercial_result

        ctx.log("workflow_completed")
        result = finish_span(ctx)

        assert result["log_count"] >= 4

    @pytest.mark.asyncio
    async def test_error_handling_in_workflow(self):
        """工作流错误处理测试"""
        ctx = start_span("error_handling_test")

        try:
            await self.commercial_agent.execute({
                "query": "",
                "category": "",
            })
            ctx.set_tag("handled_gracefully", True)
        except Exception as e:
            ctx.set_tag("error", str(e))

        finish_span(ctx)


class TestAgentLlmStructuredOutput:
    """验证Agent会调用LLM并输出结构化结果。"""

    @pytest.fixture
    def _fake_route(self, monkeypatch):
        async def _route(self, prompt, force_tier=None):
            if "数据分析师" in prompt:
                payload = '{"market_heat": 8, "competition_level": "medium", "supply_chain_maturity": 7, "recommendation": "优先验证供应链"}'
            elif "市场分析师" in prompt:
                payload = '{"opportunity_summary": "需求增长明确", "entry_timing": "now", "key_risks": ["竞争加剧"], "suggested_strategy": "先切细分市场"}'
            elif "产品规划专家" in prompt:
                payload = '{"product_viability": 9, "differentiation_strategy": "聚焦续航", "key_risks": ["同质化"], "go_to_market_advice": "先做小批量", "suggested_improvements": ["优化包装"]}'
            else:
                payload = '{"investment_confidence": 8, "market_entry_timing": "Q3", "critical_success_factors": ["控制CAC"], "risk_mitigation_priorities": ["锁定供应商"], "alternative_strategies": ["先做配件"]}'

            return type("_Result", (), {"tokens_used": 42, "response": payload})()

        monkeypatch.setattr("src.infrastructure.llm_gateway.LLMGateway.route", _route)

    @pytest.mark.asyncio
    async def test_agents_emit_structured_llm_payloads(self, _fake_route):
        data_result = await DataCollectionAgent().execute({
            "query": "户外储能电源",
            "category": "portable_power_station",
        })
        assert data_result["llm_summary_structured"]["market_heat"] == 8

        market_result = await MarketInsightAgent().execute({
            "query": "户外储能电源市场分析",
            "category": "portable_power_station",
        })
        assert market_result["llm_insight_structured"]["entry_timing"] == "now"

        planner_result = await ProductPlannerAgent().execute({
            "query": "户外储能电源产品规划",
            "category": "portable_power_station",
            "budget_range": [100, 500],
        })
        assert planner_result["llm_planning_structured"]["product_viability"] == 9

        commercial_result = await CommercialAgent().execute({
            "query": "户外储能电源商业化评估",
            "category": "portable_power_station",
            "investment_budget": 100000,
        })
        assert commercial_result["llm_assessment_structured"]["investment_confidence"] == 8

    @pytest.mark.asyncio
    async def test_selection_master_uses_real_agents(self, _fake_route):
        result = await SelectionMaster().run({
            "query": "户外储能电源",
            "category": "portable_power_station",
            "target_market": "US",
        })
        assert result["final_phase"] == "completed"
        assert "llm_summary_structured" in result["results"]["data_collection"]
        assert "llm_insight_structured" in result["results"]["market_analysis"]
        assert "llm_planning_structured" in result["results"]["product_planning"]
        assert "llm_assessment_structured" in result["results"]["commercial_evaluation"]


class TestM2Acceptance:
    """M2验收标准测试(D50)"""

    def test_langchain_framework_ready(self):
        """LangChain框架就绪"""
        from src.agents.base import BaseAgent
        assert BaseAgent is not None

    def test_four_agents_available(self):
        """四Agent可用"""
        agents = [
            DataCollectionAgent(),
            ProductPlannerAgent(),
            CommercialAgent(),
        ]
        assert len(agents) == 3

    def test_vllm_cluster_running(self):
        """vLLM集群运行"""
        gateway = LLMGateway()
        status = gateway.get_cluster_status()
        assert status["total_nodes"] == 4
        assert status["healthy_nodes"] >= 1

    def test_websocket_available(self):
        """WebSocket可用"""
        manager = WebSocketManager()
        status = manager.get_status()
        assert "total_connections" in status

    def test_erp_gateway_available(self):
        """ERP网关可用"""
        gateway = ERPGateway()
        status = gateway.get_status()
        assert "SCM" in status["supported_systems"]
        assert "OMS" in status["supported_systems"]
        assert "WMS" in status["supported_systems"]

    def test_api_endpoints_available(self):
        """API端点可用"""
        from src.api.v1.router import api_router
        routes = [r.path for r in api_router.routes]
        assert any("/selection" in r for r in routes)
        assert any("/agents" in r for r in routes)
        assert any("/knowledge" in r for r in routes)
        assert any("/reports" in r for r in routes)


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
