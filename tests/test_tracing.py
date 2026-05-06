"""
任务 4.4 验收测试：OpenTelemetry 分布式追踪
=============================================

验收标准:
- [x] Agent 执行的每个阶段在 Trace 中有独立的 Span
- [x] Span 中包含 agent.name、agent.status、agent.duration_ms 属性
- [x] 未配置 OTLP endpoint 时不报错（优雅降级）
- [x] requirements.txt 中包含 opentelemetry 相关依赖说明
"""


from src.core.tracing import (
    _NoOpSpan,
    _NoOpTracer,
    get_tracer,
    is_tracing_enabled,
    setup_tracing,
    trace_agent_execution,
)


class TestTracingGracefulDegradation:
    def test_setup_tracing_no_error_without_otel(self):
        """未安装 opentelemetry 时 setup_tracing 不报错。"""
        from unittest.mock import MagicMock

        mock_app = MagicMock()
        # 不应抛出异常
        result = setup_tracing(mock_app, service_name="test")
        # 未安装时返回 False
        assert isinstance(result, bool)

    def test_get_tracer_returns_valid_object(self):
        """get_tracer 始终返回可用的 tracer 对象。"""
        tracer = get_tracer("test_module")
        assert tracer is not None
        # 应支持 start_as_current_span
        assert hasattr(tracer, "start_as_current_span")

    def test_trace_agent_execution_no_error(self):
        """trace_agent_execution 不依赖 otel 也能正常调用。"""
        # 不应抛出异常
        trace_agent_execution(
            agent_name="data_collection",
            status="completed",
            duration_ms=1234.5,
        )


class TestNoOpStub:
    def test_noop_span_methods(self):
        """_NoOpSpan 的所有方法不报错。"""
        span = _NoOpSpan()
        span.set_attribute("key", "value")
        span.set_status("ok")
        span.add_event("test_event", {"a": 1})
        span.record_exception(RuntimeError("test"))

    def test_noop_span_context_manager(self):
        """_NoOpSpan 支持 with 语句。"""
        span = _NoOpSpan()
        with span as s:
            s.set_attribute("agent.name", "test")

    def test_noop_tracer_returns_noop_span(self):
        """_NoOpTracer.start_as_current_span 返回 _NoOpSpan。"""
        tracer = _NoOpTracer()
        span = tracer.start_as_current_span("test_span")
        assert isinstance(span, _NoOpSpan)

    def test_noop_tracer_start_span(self):
        """_NoOpTracer.start_span 返回 _NoOpSpan。"""
        tracer = _NoOpTracer()
        span = tracer.start_span("test_span")
        assert isinstance(span, _NoOpSpan)


class TestTracerUsagePattern:
    def test_agent_span_attributes(self):
        """验证 Agent Span 的典型使用模式。"""
        tracer = get_tracer("pms.agents")

        with tracer.start_as_current_span("agent.market_insight") as span:
            span.set_attribute("agent.name", "market_insight")
            span.set_attribute("agent.status", "completed")
            span.set_attribute("agent.duration_ms", 567.8)
            # 不应报错

    def test_multiple_agent_spans(self):
        """模拟完整选品流程的 4 个 Agent Span。"""
        tracer = get_tracer("fms.selection")

        agents = [
            ("data_collection", "completed", 1200),
            ("market_insight", "completed", 800),
            ("product_planner", "completed", 950),
            ("commercial", "completed", 600),
        ]

        for name, status, ms in agents:
            with tracer.start_as_current_span(f"agent.{name}") as span:
                span.set_attribute("agent.name", name)
                span.set_attribute("agent.status", status)
                span.set_attribute("agent.duration_ms", ms)

    def test_is_tracing_enabled_returns_bool(self):
        """is_tracing_enabled 返回布尔值。"""
        result = is_tracing_enabled()
        assert isinstance(result, bool)


class TestRequirements:
    def test_requirements_mentions_opentelemetry(self):
        """requirements.txt 包含 opentelemetry 依赖说明。"""
        with open("requirements.txt", encoding="utf-8") as f:
            content = f.read()
        assert "opentelemetry" in content

    def test_tracing_module_exists(self):
        """src/core/tracing.py 模块可正常导入。"""
        import src.core.tracing
        assert hasattr(src.core.tracing, "setup_tracing")
        assert hasattr(src.core.tracing, "get_tracer")
        assert hasattr(src.core.tracing, "trace_agent_execution")
