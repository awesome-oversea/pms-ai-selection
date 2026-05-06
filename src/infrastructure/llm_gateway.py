"""
LLM Gateway 智能路由服务
========================

提供多模型路由与负载均衡能力(D39-D40):
    - 按复杂度自动路由(Qwen2.5-1.5B / Phi-3-mini)
    - 四节点vLLM集群模拟
    - 超时降级机制(vLLM → Ollama)
    - 熔断器(错误率>50%触发)
    - Token计数与成本追踪

架构:
    Client Request
        ↓
    [LLM Gateway] ← 复杂度判断 + 敏感词过滤
        ├→ Node1: Qwen2.5-1.5B (复杂推理)
        ├→ Node2: Qwen2.5-1.5B (轻量查询)
        ├→ Node3: Qwen2.5-1.5B (高可用)
        └→ Node4: Phi-3-mini (敏感词/降级)

使用方式:
    from src.infrastructure.llm_gateway import LLMGateway, GatewayConfig

    gateway = LLMGateway(GatewayConfig())
    result = await gateway.route(prompt="分析蓝牙耳机市场")
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

import httpx

from src.core.logging import get_logger
from src.core.metrics import LLM_REQUEST_DURATION_SECONDS, LLM_REQUESTS_TOTAL, VLLM_TOKENS_PROCESSED
from src.infrastructure.ollama_client import OllamaClient

logger = get_logger(__name__)


class ModelTier(StrEnum):
    """模型层级。"""
    HEAVY = "heavy"
    LIGHT = "light"
    FILTER = "filter"
    FALLBACK = "fallback"


class CircuitState(StrEnum):
    """熔断器状态。"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ModelNode:
    """
    vLLM节点定义。

    Attributes:
        node_id: 节点标识
        model_name: 模型名称
        tier: 模型层级
        max_tokens: 最大Token数
        endpoint: API端点
        healthy: 健康状态
        request_count: 请求计数
        error_count: 错误计数
        avg_latency_ms: 平均延迟(ms)
    """

    node_id: str
    model_name: str
    tier: ModelTier
    max_tokens: int = 4096
    endpoint: str = ""
    healthy: bool = True
    request_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0
    last_request_time: datetime | None = None

    @property
    def error_rate(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.error_count / self.request_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "model_name": self.model_name,
            "tier": self.tier.value,
            "max_tokens": self.max_tokens,
            "healthy": self.healthy,
            "request_count": self.request_count,
            "error_rate": round(self.error_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


@dataclass
class CircuitBreaker:
    """
    熔断器(D40核心)。

    状态机:
        CLOSED → OPEN (错误率 > threshold)
        OPEN → HALF_OPEN (cooldown过期)
        HALF_OPEN → CLOSED (探测成功)
        HALF_OPEN → OPEN (探测失败)

    Attributes:
        failure_threshold: 触发熔断的错误率阈值(0-1)
        cooldown_seconds: 熔断冷却时间(秒)
        half_open_max_probes: 半开状态最大探测请求数
    """

    failure_threshold: float = 0.50
    cooldown_seconds: int = 30
    half_open_max_probes: int = 3
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    successes: int = 0
    total_requests: int = 0
    last_failure_time: datetime | None = None
    probe_count: int = 0

    def record_success(self) -> None:
        self.total_requests += 1
        self.successes += 1
        if self.state == CircuitState.HALF_OPEN:
            self.probe_count += 1
            if self.probe_count >= self.half_open_max_probes:
                self.state = CircuitState.CLOSED
                self.failures = 0
                self.probe_count = 0
                logger.info("熔断器恢复: CLOSED")

    def record_failure(self) -> None:
        self.total_requests += 1
        self.failures += 1
        self.last_failure_time = datetime.now(UTC)
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.probe_count = 0
            logger.warning("熔断器半开探测失败: → OPEN")
        elif self.total_requests > 10 and (self.failures / self.total_requests) > self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"熔断器触发: 错误率{self.failures}/{self.total_requests} > {self.failure_threshold}")

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self.last_failure_time:
                elapsed = (datetime.now(UTC) - self.last_failure_time).total_seconds()
                if elapsed > self.cooldown_seconds:
                    self.state = CircuitState.HALF_OPEN
                    self.probe_count = 0
                    logger.info("熔断器冷却完成: → HALF_OPEN")
                    return True
            return False
        return self.probe_count < self.half_open_max_probes

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "failure_threshold": self.failure_threshold,
            "total_requests": self.total_requests,
            "failures": self.failures,
            "successes": self.successes,
            "error_rate": round(self.failures / max(self.total_requests, 1), 4),
            "cooldown_remaining": max(0, self.cooldown_seconds - int((datetime.now(UTC) - (self.last_failure_time or datetime.now(UTC))).total_seconds())) if self.state == CircuitState.OPEN else 0,
        }


@dataclass
class GatewayConfig:
    """网关配置。"""
    vllm_timeout_seconds: float = 30.0
    ollama_timeout_seconds: float = 10.0
    complexity_token_threshold: int = 500
    enable_content_filter: bool = True
    circuit_breaker_threshold: float = 0.50
    cost_per_1k_tokens_heavy: float = 0.002
    cost_per_1k_tokens_light: float = 0.0004
    use_mock: bool = True
    vllm_endpoint: str = "http://localhost:8000/v1"
    ollama_endpoint: str = "http://localhost:11434"
    provider_mode: str = "mock"
    primary_provider: str = "vllm"
    fallback_provider: str = "ollama"
    fallback_timeout_budget_seconds: float = 5.0
    ollama_model_name: str = "qwen2.5:1.5b-instruct"
    api_key: str | None = None
    api_auth_header: str = "Authorization"
    api_auth_scheme: str = "Bearer"
    api_model_name: str | None = None
    retry_count: int = 1


@dataclass
class RouteResult:
    """路由结果。"""
    prompt: str
    selected_node: str
    model_name: str
    tier: str
    response: str
    tokens_used: int
    latency_ms: float
    cost_usd: float
    routed_at: str
    degraded: bool = False
    circuit_broken: bool = False
    provider_mode: str = "mock"
    primary_provider: str = "vllm"
    actual_provider: str = "vllm"
    fallback_provider: str = "ollama"

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_preview": self.prompt[:80] + "..." if len(self.prompt) > 80 else self.prompt,
            "selected_node": self.selected_node,
            "model_name": self.model_name,
            "tier": self.tier,
            "response": self.response,
            "tokens_used": self.tokens_used,
            "latency_ms": round(self.latency_ms, 1),
            "cost_usd": round(self.cost_usd, 6),
            "routed_at": self.routed_at,
            "degraded": self.degraded,
            "circuit_broken": self.circuit_broken,
            "provider_mode": self.provider_mode,
            "primary_provider": self.primary_provider,
            "actual_provider": self.actual_provider,
            "fallback_provider": self.fallback_provider,
        }


class LLMGateway:
    """
    LLM智能网关(D39-D40核心)。

    功能:
        1. 复杂度判断: 基于Token数/关键词/上下文长度选择模型
        2. 敏感词过滤: Phi-3-mini预处理
        3. 负载均衡: 加权轮询+健康检查
        4. 超时降级: vLLM超时→Ollama轻量模型
        5. 熔断保护: 错误率>50%自动熔断
    """

    def __init__(self, config: GatewayConfig | None = None):
        self.config = config or GatewayConfig()
        if self.config.provider_mode == "mock" and not self.config.use_mock:
            self.config.provider_mode = "real"
        elif self.config.provider_mode == "mock" and self.config.use_mock:
            self.config.provider_mode = "mock"
        self._nodes: list[ModelNode] = []
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._route_history: list[RouteResult] = []
        self._init_cluster()

    def _init_cluster(self) -> None:
        """初始化四节点vLLM集群。"""
        cluster_config = [
            {"node_id": "node_1", "model_name": "Qwen2.5-1.5B-Instruct", "tier": ModelTier.HEAVY, "max_tokens": 8192},
            {"node_id": "node_2", "model_name": "Qwen2.5-1.5B-Instruct", "tier": ModelTier.LIGHT, "max_tokens": 4096},
            {"node_id": "node_3", "model_name": "Qwen2.5-1.5B-Instruct", "tier": ModelTier.HEAVY, "max_tokens": 8192},
            {"node_id": "node_4", "model_name": "Phi-3-mini-128K-instruct", "tier": ModelTier.FILTER, "max_tokens": 4096},
        ]
        for cfg in cluster_config:
            node = ModelNode(
                node_id=cfg["node_id"],
                model_name=cfg["model_name"],
                tier=cfg["tier"],
                max_tokens=cfg["max_tokens"],
                endpoint=f"http://vllm-cluster.internal:8000/{cfg['node_id']}",
            )
            self._nodes.append(node)
            self._circuit_breakers[cfg["node_id"]] = CircuitBreaker(
                failure_threshold=self.config.circuit_breaker_threshold,
            )
        logger.info(f"LLM Gateway初始化完成: {len(self._nodes)}节点集群")

    def _estimate_complexity(self, prompt: str) -> tuple[ModelTier, int]:
        """
        估算查询复杂度。

        判断规则:
            - Token数 > threshold → HEAVY
            - 含分析/预测/评估等关键词 → HEAVY
            - 简单问答/翻译 → LIGHT
            - 含敏感词检测需求 → FILTER
        """
        estimated_tokens = len(prompt) // 3

        heavy_keywords = ["分析", "评估", "预测", "规划", "策略", "对比", "推荐", "计算", "报告"]
        light_keywords = ["什么是", "如何", "列表", "翻译", "总结", "简介"]
        filter_keywords = ["敏感词", "过滤", "审查", "合规"]

        prompt_lower = prompt.lower()
        has_heavy = any(kw in prompt_lower for kw in heavy_keywords)
        has_light = any(kw in prompt_lower for kw in light_keywords)
        has_filter = any(kw in prompt_lower for kw in filter_keywords)

        if has_filter and self.config.enable_content_filter:
            return ModelTier.FILTER, estimated_tokens
        if estimated_tokens > self.config.complexity_token_threshold or has_heavy:
            return ModelTier.HEAVY, estimated_tokens
        if has_light:
            return ModelTier.LIGHT, estimated_tokens
        return ModelTier.LIGHT, estimated_tokens

    def _select_node(self, tier: ModelTier) -> ModelNode | None:
        """
        选择目标节点(负载均衡+熔断检查)。

        策略:
            1. 过滤已熔断节点
            2. 匹配tier的候选节点
            3. 选择请求最少的节点(加权最少连接)
        """
        candidates = []
        for node in self._nodes:
            if node.tier != tier:
                continue
            cb = self._circuit_breakers.get(node.node_id)
            if cb and not cb.allow_request():
                continue
            candidates.append(node)

        if not candidates:
            fallback_tier = ModelTier.FALLBACK if tier != ModelTier.FALLBACK else ModelTier.LIGHT
            for node in self._nodes:
                if node.tier == fallback_tier and node.healthy:
                    cb = self._circuit_breakers.get(node.node_id)
                    if cb and cb.allow_request():
                        return node
            return None

        return min(candidates, key=lambda n: n.request_count)

    async def _call_vllm(self, node: ModelNode, prompt: str, timeout: float) -> tuple[str, int, bool]:
        """调用vLLM节点（支持真实HTTP和Mock模式）。"""
        if self.config.use_mock:
            return await self._call_vllm_mock(node, prompt, timeout)
        return await self._call_vllm_real(node, prompt, timeout)

    async def _call_vllm_real(self, node: ModelNode, prompt: str, timeout: float) -> tuple[str, int, bool]:
        """真实HTTP调用vLLM节点（OpenAI兼容API）。"""
        attempts = max(1, self.config.retry_count + 1)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            start = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
                    headers = {"Content-Type": "application/json"}
                    if self.config.api_key:
                        auth_value = self.config.api_key
                        if self.config.api_auth_scheme:
                            auth_value = f"{self.config.api_auth_scheme} {auth_value}"
                        headers[self.config.api_auth_header] = auth_value

                    response = await client.post(
                        f"{self.config.vllm_endpoint}/chat/completions",
                        json={
                            "model": self.config.api_model_name or node.model_name,
                            "messages": [
                                {"role": "system", "content": "你是一个跨境电商AI选品助手，请用中文回答。"},
                                {"role": "user", "content": prompt},
                            ],
                            "max_tokens": node.max_tokens,
                            "temperature": 0.7,
                        },
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()

                latency = (time.monotonic() - start) * 1000
                content = data["choices"][0]["message"]["content"]
                tokens = data.get("usage", {}).get("total_tokens", len(content) // 2 + len(prompt) // 3)

                node.request_count += 1
                node.avg_latency_ms = (node.avg_latency_ms * (node.request_count - 1) + latency) / node.request_count
                node.last_request_time = datetime.now(UTC)

                cb = self._circuit_breakers.get(node.node_id)
                if cb:
                    cb.record_success()

                return content, tokens, False

            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError, KeyError) as e:
                last_error = e
                if attempt < attempts:
                    logger.warning(f"节点{node.node_id}真实调用失败，准备重试({attempt}/{attempts - 1}): {type(e).__name__}: {e}")
                    continue

                latency = (time.monotonic() - start) * 1000
                node.error_count += 1
                node.request_count += 1
                cb = self._circuit_breakers.get(node.node_id)
                if cb:
                    cb.record_failure()
                logger.warning(f"节点{node.node_id}真实调用失败({type(e).__name__}): {e}")
                return "", 0, True

        logger.warning(f"节点{node.node_id}真实调用失败，未拿到有效响应: {last_error}")
        return "", 0, True

    async def _call_vllm_mock(self, node: ModelNode, prompt: str, timeout: float) -> tuple[str, int, bool]:
        """Mock模式调用vLLM节点。"""
        start = time.monotonic()
        try:
            await asyncio.wait_for(
                asyncio.sleep(random.uniform(0.05, 0.3)),
                timeout=timeout,
            )

            latency = (time.monotonic() - start) * 1000
            simulated_error = random.random() < 0.03
            if simulated_error:
                raise TimeoutError("vLLM推理超时")

            response_templates = {
                ModelTier.HEAVY: f"[{node.model_name}] 深度分析结果: 基于{len(prompt)}字符输入，经过多轮推理得出结论。市场趋势显示增长潜力约{random.uniform(15,45):.1f}%，建议采取差异化策略进入市场。",
                ModelTier.LIGHT: f"[{node.model_name}] 快速响应: {prompt[:50]}... 的简明回答已完成处理。",
                ModelTier.FILTER: f"[{node.model_name}] 内容安全检查通过，未发现违规内容。",
                ModelTier.FALLBACK: "[Ollama Fallback] 降级模式响应: 服务暂时受限，返回基础答案。",
            }
            response = response_templates.get(node.tier, "OK")
            tokens = len(response) // 2 + len(prompt) // 3

            node.request_count += 1
            node.avg_latency_ms = (node.avg_latency_ms * (node.request_count - 1) + latency) / node.request_count
            node.last_request_time = datetime.now(UTC)

            cb = self._circuit_breakers.get(node.node_id)
            if cb:
                cb.record_success()

            return response, tokens, False

        except TimeoutError:
            latency = (time.monotonic() - start) * 1000
            node.error_count += 1
            node.request_count += 1
            cb = self._circuit_breakers.get(node.node_id)
            if cb:
                cb.record_failure()
            logger.warning(f"节点{node.node_id}调用失败(超时{timeout}s)")
            return "", 0, True

    async def _degrade_to_ollama(self, prompt: str) -> tuple[str, int]:
        """降级到Ollama轻量模型（支持真实HTTP和Mock模式）。"""
        if self.config.use_mock:
            return await self._degrade_to_ollama_mock(prompt)
        return await self._degrade_to_ollama_real(prompt)

    async def _degrade_to_ollama_real(self, prompt: str) -> tuple[str, int]:
        """真实HTTP调用Ollama API。"""
        try:
            client = OllamaClient(
                endpoint=self.config.ollama_endpoint,
                timeout_seconds=self.config.ollama_timeout_seconds,
                model_name=self.config.ollama_model_name,
            )
            data = await client.generate(prompt)
            content = str(data.get("response", ""))
            tokens = int(data.get("eval_count", len(content) // 2))
            return content, tokens
        except Exception as e:
            logger.error(f"Ollama降级也失败: {e}")
            return "[System] 所有模型不可用，请稍后重试。", 0

    async def _degrade_to_ollama_mock(self, prompt: str) -> tuple[str, int]:
        """Mock模式降级到Ollama。"""
        try:
            await asyncio.wait_for(
                asyncio.sleep(random.uniform(0.02, 0.08)),
                timeout=self.config.ollama_timeout_seconds,
            )
            response = f"[Ollama-{self.config.ollama_model_name}] 降级响应: {prompt[:30]}... 的简化处理完成。"
            return response, len(response) // 2
        except Exception as e:
            logger.error(f"Ollama降级也失败: {e}")
            return "[System] 所有模型不可用，请稍后重试。", 0

    async def route(self, prompt: str, force_tier: ModelTier | None = None) -> RouteResult:
        """
        核心路由方法(D39核心)。

        流程:
            1. 复杂度判断(或使用强制tier)
            2. 节点选择(负载均衡+熔断)
            3. vLLM调用(带超时)
            4. 失败时降级到Ollama
            5. 记录路由历史+成本统计
        """
        route_start = time.monotonic()
        tier = force_tier or self._estimate_complexity(prompt)[0]
        node = self._select_node(tier)
        is_degraded = False
        is_circuit_broken = False

        primary_provider = self.config.primary_provider.lower()
        fallback_provider = self.config.fallback_provider.lower()
        actual_provider = primary_provider
        response = ""
        tokens = 0
        if primary_provider == "ollama":
            response, tokens = await self._degrade_to_ollama(prompt)
            if not response or response.startswith("[System]"):
                is_degraded = True
                actual_provider = fallback_provider
                if node is None:
                    is_circuit_broken = True
                    response = "[System] 所有模型不可用，请稍后重试。"
                    tokens = 0
                else:
                    response, tokens, timed_out = await self._call_vllm(node, prompt, min(self.config.vllm_timeout_seconds, self.config.fallback_timeout_budget_seconds))
                    if timed_out or not response:
                        response = "[System] 所有模型不可用，请稍后重试。"
                        tokens = 0
        else:
            actual_provider = "vllm"
            if node is None:
                is_circuit_broken = True
                logger.warning("所有匹配节点均不可用，执行降级")
                response, tokens = await self._degrade_to_ollama(prompt)
                is_degraded = True
                actual_provider = fallback_provider
            else:
                response, tokens, timed_out = await self._call_vllm(node, prompt, self.config.vllm_timeout_seconds)
                if timed_out or not response:
                    logger.info(f"节点{node.node_id}超时/空响应，降级到Ollama")
                    response, tokens = await self._degrade_to_ollama(prompt)
                    is_degraded = True
                    actual_provider = fallback_provider

        total_latency = (time.monotonic() - route_start) * 1000

        cost_per_1k = (
            self.config.cost_per_1k_tokens_heavy
            if tier in (ModelTier.HEAVY,)
            else self.config.cost_per_1k_tokens_light
        )
        cost = (tokens / 1000) * cost_per_1k

        result = RouteResult(
            prompt=prompt,
            selected_node=(node.node_id if actual_provider == "vllm" and node else "ollama_primary" if actual_provider == "ollama" and primary_provider == "ollama" else "ollama_fallback"),
            model_name=(node.model_name if actual_provider == "vllm" and node else self.config.ollama_model_name),
            tier=tier.value,
            response=response,
            tokens_used=tokens,
            latency_ms=total_latency,
            cost_usd=cost,
            routed_at=datetime.now(UTC).isoformat(),
            degraded=is_degraded,
            circuit_broken=is_circuit_broken,
            provider_mode=self.config.provider_mode,
            primary_provider=primary_provider,
            actual_provider=actual_provider,
            fallback_provider=self.config.fallback_provider,
        )

        provider_label = actual_provider or "unknown"
        model_label = result.model_name or "unknown"
        status_label = "degraded" if is_degraded else "success"
        LLM_REQUESTS_TOTAL.labels(model=model_label, status=status_label).inc()
        LLM_REQUEST_DURATION_SECONDS.labels(model=model_label).observe(max(total_latency / 1000, 0.0))
        VLLM_TOKENS_PROCESSED.labels(
            tier=result.tier,
            provider=provider_label,
            model=model_label,
        ).inc(max(tokens, 0))

        self._route_history.append(result)
        if len(self._route_history) > 1000:
            self._route_history = self._route_history[-500:]

        return result

    def get_cluster_status(self) -> dict[str, Any]:
        """获取集群状态。"""
        return {
            "gateway_version": "1.0.0",
            "total_nodes": len(self._nodes),
            "healthy_nodes": sum(1 for n in self._nodes if n.healthy),
            "nodes": [n.to_dict() for n in self._nodes],
            "circuit_breakers": {nid: cb.to_dict() for nid, cb in self._circuit_breakers.items()},
            "total_routes": len(self._route_history),
            "recent_degradation_rate": (
                round(sum(1 for r in self._route_history[-50:] if r.degraded) / min(len(self._route_history), 50), 3)
                if self._route_history else 0.0
            ),
        }

    def get_route_stats(self) -> dict[str, Any]:
        """获取路由统计。"""
        if not self._route_history:
            return {"total_routes": 0, "message": "暂无路由记录"}

        recent = self._route_history[-100:]
        tier_counts: dict[str, int] = {}
        node_counts: dict[str, int] = {}
        total_latency = 0.0
        total_cost = 0.0
        total_tokens = 0
        degraded_count = 0

        for r in recent:
            tier_counts[r.tier] = tier_counts.get(r.tier, 0) + 1
            node_counts[r.selected_node] = node_counts.get(r.selected_node, 0) + 1
            total_latency += r.latency_ms
            total_cost += r.cost_usd
            total_tokens += r.tokens_used
            if r.degraded:
                degraded_count += 1

        return {
            "sample_size": len(recent),
            "tier_distribution": tier_counts,
            "node_distribution": node_counts,
            "avg_latency_ms": round(total_latency / len(recent), 1),
            "total_cost_usd": round(total_cost, 6),
            "total_tokens": total_tokens,
            "degradation_rate": round(degraded_count / len(recent), 3),
            "p95_latency_ms": round(sorted([r.latency_ms for r in recent])[int(len(recent) * 0.95)], 1) if len(recent) > 10 else 0,
        }


def create_llm_gateway(config: GatewayConfig | None = None) -> LLMGateway:
    """创建LLMGateway工厂函数。"""
    return LLMGateway(config=config)
