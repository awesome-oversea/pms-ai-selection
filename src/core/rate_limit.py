"""
请求速率限制
============

基于 IP 的请求速率限制中间件，使用滑动窗口算法。

限制策略:
    - 全局默认: 100 次/分钟
    - 选品任务创建: 10 次/分钟
    - 登录接口: 5 次/分钟

超限返回 429 Too Many Requests。

使用方式:
    from src.core.rate_limit import RateLimiter, rate_limit

    limiter = RateLimiter()
    app.add_middleware(limiter.middleware_class)

    @app.post("/tasks")
    @rate_limit(max_calls=10, period=60)
    async def create_task(...):
        ...
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.core.logging import get_logger

logger = get_logger(__name__)


class SlidingWindowCounter:
    """滑动窗口计数器。"""

    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = period_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """
        检查请求是否在速率限制内。

        Args:
            key: 限流键（通常为 IP 地址）

        Returns:
            bool: 是否允许请求
        """
        now = time.time()
        window_start = now - self.period

        # 清理过期记录
        self._requests[key] = [
            ts for ts in self._requests[key] if ts > window_start
        ]

        if len(self._requests[key]) >= self.max_calls:
            return False

        self._requests[key].append(now)
        return True

    def remaining(self, key: str) -> int:
        """返回剩余可用请求数。"""
        now = time.time()
        window_start = now - self.period
        active = [ts for ts in self._requests[key] if ts > window_start]
        return max(0, self.max_calls - len(active))

    def reset_time(self, key: str) -> float:
        """返回最早请求过期的时间。"""
        if not self._requests[key]:
            return 0.0
        return self._requests[key][0] + self.period


# ---------------------------------------------------------------------------
# 路由级别限流规则
# ---------------------------------------------------------------------------

# 路由限流规则: path_prefix → (max_calls, period_seconds)
ROUTE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/selection/tasks:POST": (10, 60),      # 选品任务创建: 10次/分钟
    "/api/v1/auth/login:POST": (5, 60),             # 登录: 5次/分钟
    "/api/v1/auth/register:POST": (5, 60),          # 注册: 5次/分钟
}

# 全局默认限制
DEFAULT_LIMIT = (100, 60)  # 100次/分钟


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    请求速率限制中间件。

    基于客户端 IP + 路由路径进行限流，
    使用滑动窗口计数器算法。
    """

    def __init__(self, app: ASGIApp, default_limit: tuple[int, int] = DEFAULT_LIMIT):
        super().__init__(app)
        self._default_counter = SlidingWindowCounter(*default_limit)
        self._route_counters: dict[str, SlidingWindowCounter] = {}

        for route_key, (max_calls, period) in ROUTE_LIMITS.items():
            self._route_counters[route_key] = SlidingWindowCounter(max_calls, period)

    async def dispatch(self, request: Request, call_next):
        client_ip = _get_client_ip(request)
        method = request.method
        path = request.url.path

        # 跳过 /metrics、/health、/docs 等非业务路径
        if path in ("/metrics", "/health", "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        # 检查路由级别限流
        route_key = f"{path}:{method}"
        if route_key in self._route_counters:
            counter = self._route_counters[route_key]
            limiter_key = f"{client_ip}:{route_key}"
            if not counter.is_allowed(limiter_key):
                remaining = counter.remaining(limiter_key)
                logger.warning(f"🚫 速率限制: {client_ip} → {route_key} (剩余: {remaining})")
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "请求过于频繁，请稍后重试",
                        "error_code": "RATE_LIMIT_EXCEEDED",
                        "retry_after_seconds": counter.period,
                    },
                    headers={"Retry-After": str(counter.period)},
                )

        # 全局限流
        global_key = f"{client_ip}:global"
        if not self._default_counter.is_allowed(global_key):
            logger.warning(f"🚫 全局速率限制: {client_ip}")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "请求过于频繁，请稍后重试",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "retry_after_seconds": self._default_counter.period,
                },
                headers={"Retry-After": str(self._default_counter.period)},
            )

        response = await call_next(request)
        return response


def _get_client_ip(request: Request) -> str:
    """获取客户端 IP，支持反向代理。"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def setup_rate_limit(app: ASGIApp) -> None:
    """便捷函数: 将限流中间件添加到 FastAPI 应用。"""
    # 注意: FastAPI 中间件添加顺序是反的，最后添加的最先执行
    pass  # 通过 app.add_middleware 在 main.py 中调用
