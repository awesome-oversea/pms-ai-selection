"""
OpenTelemetry 分布式追踪
========================

初始化 TracerProvider 并集成到 FastAPI 应用。
未配置 OTLP endpoint 时优雅降级（不报错）。
opentelemetry 未安装时使用 no-op stub。

使用方式:
    from src.core.tracing import setup_tracing, get_tracer

    setup_tracing(app, service_name="pms-ai-selection")
    tracer = get_tracer(__name__)

    with tracer.start_as_current_span("agent.data_collection") as span:
        span.set_attribute("agent.name", "data_collection")
        ...

Span 属性:
    - agent.name: Agent 名称
    - agent.status: Agent 执行状态
    - agent.duration_ms: Agent 执行耗时（毫秒）
"""

from __future__ import annotations

from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# OpenTelemetry 可用性检测
# ---------------------------------------------------------------------------

_OTEL_AVAILABLE = False

try:
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )

    _OTEL_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# No-op Stub（opentelemetry 未安装时的降级实现）
# ---------------------------------------------------------------------------

class _NoOpSpan:
    """No-op Span，用于 opentelemetry 不可用时。"""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, *args, **kwargs) -> None:
        pass

    def add_event(self, name: str, attributes: dict | None = None) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _NoOpTracer:
    """No-op Tracer，用于 opentelemetry 不可用时。"""

    def start_as_current_span(self, name: str, **kwargs) -> _NoOpSpan:
        return _NoOpSpan()

    def start_span(self, name: str, **kwargs) -> _NoOpSpan:
        return _NoOpSpan()


_tracer_cache: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def setup_tracing(
    app: Any,
    service_name: str = "pms-ai-selection",
    environment: str = "development",
    otlp_endpoint: str | None = None,
) -> bool:
    """
    初始化 OpenTelemetry 追踪并集成到 FastAPI 应用。

    Args:
        app: FastAPI 应用实例
        service_name: 服务名称（显示在 Trace 中）
        environment: 运行环境标签
        otlp_endpoint: OTLP exporter 端点（如 http://jaeger:4317）

    Returns:
        bool: 是否成功初始化
    """
    if not _OTEL_AVAILABLE:
        logger.info("ℹ️ OpenTelemetry 未安装，追踪功能已禁用（no-op 模式）")
        return False

    try:
        resource = Resource.create({
            SERVICE_NAME: service_name,
            "deployment.environment": environment,
            "service.version": "0.1.0",
        })

        provider = TracerProvider(resource=resource)

        # 配置 exporter
        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )
                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                logger.info(f"📡 OTLP exporter 已配置: {otlp_endpoint}")
            except ImportError:
                logger.warning("⚠️ OTLP exporter 未安装，使用 ConsoleSpanExporter")
                provider.add_span_processor(
                    BatchSpanProcessor(ConsoleSpanExporter())
                )
        else:
            # 未配置 endpoint 时，开发环境使用 Console exporter
            if environment != "production":
                provider.add_span_processor(
                    BatchSpanProcessor(ConsoleSpanExporter())
                )

        trace.set_tracer_provider(provider)

        # 自动 instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)

        logger.info(f"✅ OpenTelemetry 追踪已初始化 (service={service_name}, env={environment})")
        return True

    except Exception as e:
        logger.warning(f"⚠️ OpenTelemetry 初始化失败: {e}")
        return False


def get_tracer(name: str = __name__) -> Any:
    """
    获取 Tracer 实例。

    opentelemetry 可用时返回真实 Tracer，
    不可用时返回 _NoOpTracer（无副作用）。

    Args:
        name: Tracer 名称（通常为 __name__）

    Returns:
        Tracer 或 _NoOpTracer 实例
    """
    if name in _tracer_cache:
        return _tracer_cache[name]

    tracer = trace.get_tracer(name) if _OTEL_AVAILABLE else _NoOpTracer()

    _tracer_cache[name] = tracer
    return tracer


def trace_agent_execution(agent_name: str, status: str, duration_ms: float) -> None:
    """
    为 Agent 执行记录一个追踪 Span。

    Args:
        agent_name: Agent 名称
        status: 执行状态 (completed/failed)
        duration_ms: 执行耗时（毫秒）
    """
    tracer = get_tracer("pms.agents")
    with tracer.start_as_current_span(f"agent.{agent_name}") as span:
        span.set_attribute("agent.name", agent_name)
        span.set_attribute("agent.status", status)
        span.set_attribute("agent.duration_ms", duration_ms)


def is_tracing_enabled() -> bool:
    """检查 OpenTelemetry 是否可用。"""
    return _OTEL_AVAILABLE
