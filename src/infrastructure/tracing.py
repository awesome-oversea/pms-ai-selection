"""
全链路追踪中间件
================

提供分布式追踪能力(D46):
    - Trace ID生成与传递
    - 请求耗时统计
    - 跨服务调用链追踪
    - 日志关联

使用方式:
    from src.infrastructure.tracing import TraceMiddleware, get_trace_id

    app = FastAPI()
    app.add_middleware(TraceMiddleware)
"""

from __future__ import annotations

import contextvars
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.logging import get_logger
from src.core.metrics import observe_api_request

logger = get_logger(__name__)

_trace_context: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar("trace_context", default=None)


@dataclass
class TraceContext:
    """
    追踪上下文。

    Attributes:
        trace_id: 全局唯一追踪ID
        request_id: 请求唯一ID
        span_id: 当前Span ID
        parent_span_id: 父Span ID
        start_time: 开始时间戳
        operation_name: 操作名称
        tags: 标签键值对
        logs: 日志事件列表
    """

    trace_id: str
    request_id: str = ""
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.monotonic)
    operation_name: str = ""
    tags: dict[str, Any] = field(default_factory=dict)
    logs: list[dict[str, Any]] = field(default_factory=list)

    def log(self, event: str, **kwargs) -> None:
        self.logs.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            **kwargs,
        })

    def set_tag(self, key: str, value: Any) -> None:
        self.tags[key] = value

    @property
    def duration_ms(self) -> float:
        return (time.monotonic() - self.start_time) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation": self.operation_name,
            "duration_ms": round(self.duration_ms, 2),
            "tags": self.tags,
            "log_count": len(self.logs),
        }


def generate_trace_id() -> str:
    """生成Trace ID。"""
    return f"tr-{uuid.uuid4().hex[:24]}"


def get_trace_context() -> TraceContext | None:
    """获取当前追踪上下文。"""
    return _trace_context.get()


def get_trace_id() -> str:
    """获取当前Trace ID。"""
    ctx = get_trace_context()
    return ctx.trace_id if ctx else "no-trace"


def get_request_id() -> str:
    """获取当前Request ID。"""
    ctx = get_trace_context()
    return ctx.request_id if ctx and ctx.request_id else "no-request"


def set_trace_context(ctx: TraceContext) -> None:
    """设置追踪上下文。"""
    _trace_context.set(ctx)


def bind_trace_tags(**tags: Any) -> dict[str, Any]:
    ctx = get_trace_context()
    if ctx is None:
        return {}
    for key, value in tags.items():
        ctx.set_tag(key, value)
    return ctx.tags


def trace_snapshot() -> dict[str, Any]:
    ctx = get_trace_context()
    return ctx.to_dict() if ctx is not None else {"trace_id": "no-trace", "request_id": "no-request"}


def start_span(
    operation_name: str,
    parent_ctx: TraceContext | None = None,
    tags: dict | None = None,
) -> TraceContext:
    """创建新的Span。"""
    parent = parent_ctx or get_trace_context()
    ctx = TraceContext(
        trace_id=parent.trace_id if parent else generate_trace_id(),
        parent_span_id=parent.span_id if parent else None,
        operation_name=operation_name,
        tags=tags or {},
    )
    set_trace_context(ctx)
    return ctx


def finish_span(ctx: TraceContext) -> dict[str, Any]:
    """结束Span并返回结果。"""
    result = ctx.to_dict()
    logger.debug(f"Span完成: {ctx.operation_name} ({ctx.duration_ms:.1f}ms)")
    return result


class TraceMiddleware(BaseHTTPMiddleware):
    """
    全链路追踪中间件(D46核心)。

    功能:
        1. 自动生成/传递Trace ID
        2. 记录请求耗时
        3. 注入响应头
        4. 结构化日志
    """

    EXCLUDE_PATHS = {"/health", "/metrics", "/favicon.ico", "/docs", "/openapi.json"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.EXCLUDE_PATHS:
            return await call_next(request)

        trace_id = request.headers.get("X-Trace-ID") or generate_trace_id()
        request_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:24]}"
        ctx = TraceContext(
            trace_id=trace_id,
            request_id=request_id,
            operation_name=f"{request.method} {request.url.path}",
        )
        request.state.trace_id = trace_id
        request.state.request_id = request_id
        ctx.set_tag("http.method", request.method)
        ctx.set_tag("http.path", request.url.path)
        ctx.set_tag("http.query", str(request.query_params)[:200])
        ctx.set_tag("client.ip", self._get_client_ip(request))

        set_trace_context(ctx)
        ctx.log("request_started")

        try:
            response = await call_next(request)
            ctx.set_tag("http.status_code", response.status_code)
            ctx.log("request_completed", status=response.status_code)

            if response.status_code >= 400:
                ctx.set_tag("error", True)
                ctx.log("error_occurred", status_code=response.status_code)

            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time-Ms"] = f"{ctx.duration_ms:.1f}"

            self._log_request(ctx, response.status_code)

            return response

        except Exception as e:
            ctx.set_tag("error", True)
            ctx.set_tag("error.type", type(e).__name__)
            ctx.log("exception", error=str(e), error_type=type(e).__name__)
            logger.bind(trace_id=trace_id).opt(exception=e).error("请求异常: {} - {}", ctx.operation_name, e)
            raise

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _log_request(self, ctx: TraceContext, status_code: int) -> None:
        method = str(ctx.tags.get("http.method") or "UNKNOWN")
        path = str(ctx.tags.get("http.path") or "unknown")
        observe_api_request(path, method, status_code, ctx.duration_ms / 1000)
        level = "INFO" if status_code < 400 else "WARNING" if status_code < 500 else "ERROR"
        logger.log(
            20 if level == "INFO" else 30 if level == "WARNING" else 40,
            f"[{ctx.trace_id}] {ctx.operation_name} -> {status_code} ({ctx.duration_ms:.1f}ms)",
        )


class TraceCollector:
    """
    追踪收集器(用于聚合分析)。

    功能:
        1. 收集所有Span
        2. 计算统计指标
        3. 慢请求检测
        4. 错误聚合
    """

    SLOW_THRESHOLD_MS = 1000.0

    def __init__(self, max_spans: int = 10000):
        self._spans: list[dict[str, Any]] = []
        self._max_spans = max_spans
        self._slow_requests: list[dict[str, Any]] = []
        self._error_count = 0
        self._total_requests = 0

    def collect(self, ctx: TraceContext) -> None:
        span_data = ctx.to_dict()
        self._spans.append(span_data)
        self._total_requests += 1

        if ctx.duration_ms > self.SLOW_THRESHOLD_MS:
            self._slow_requests.append(span_data)
            logger.warning(f"慢请求: {ctx.operation_name} ({ctx.duration_ms:.1f}ms)")

        if ctx.tags.get("error"):
            self._error_count += 1

        if len(self._spans) > self._max_spans:
            self._spans = self._spans[-self._max_spans // 2]

    def get_stats(self) -> dict[str, Any]:
        if not self._spans:
            return {"total_requests": 0}

        durations = [s["duration_ms"] for s in self._spans]
        return {
            "total_requests": self._total_requests,
            "error_count": self._error_count,
            "error_rate": round(self._error_count / max(self._total_requests, 1), 4),
            "slow_requests": len(self._slow_requests),
            "avg_duration_ms": round(sum(durations) / len(durations), 2),
            "p50_duration_ms": round(sorted(durations)[int(len(durations) * 0.5)], 2),
            "p95_duration_ms": round(sorted(durations)[int(len(durations) * 0.95)], 2),
            "p99_duration_ms": round(sorted(durations)[int(len(durations) * 0.99)], 2),
            "recent_spans": self._spans[-10:],
        }

    def get_slow_requests(self, limit: int = 20) -> list[dict[str, Any]]:
        return sorted(self._slow_requests, key=lambda x: x["duration_ms"], reverse=True)[:limit]


trace_collector = TraceCollector()
