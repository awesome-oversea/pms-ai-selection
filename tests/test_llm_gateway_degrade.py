from __future__ import annotations

import pytest
from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway


@pytest.mark.asyncio
async def test_llm_gateway_degrades_to_ollama_when_vllm_times_out(monkeypatch):
    gateway = LLMGateway(GatewayConfig(use_mock=False, provider_mode="real", vllm_endpoint="http://localhost:8000/v1", ollama_endpoint="http://localhost:11434"))

    async def _timeout(*args, **kwargs):
        return "", 0, True

    async def _fallback(prompt: str):
        return "fallback ok", 12

    monkeypatch.setattr(gateway, "_call_vllm", _timeout)
    monkeypatch.setattr(gateway, "_degrade_to_ollama", _fallback)

    result = await gateway.route("请分析蓝牙耳机市场")
    data = result.to_dict()
    assert data["degraded"] is True
    assert data["actual_provider"] == "ollama"
    assert data["primary_provider"] == "vllm"
    assert data["fallback_provider"] == "ollama"
    assert data["response"] == "fallback ok"


@pytest.mark.asyncio
async def test_llm_gateway_uses_primary_when_vllm_succeeds(monkeypatch):
    gateway = LLMGateway(GatewayConfig(use_mock=False, provider_mode="real", vllm_endpoint="http://localhost:8000/v1", ollama_endpoint="http://localhost:11434"))

    async def _success(*args, **kwargs):
        return "primary ok", 21, False

    monkeypatch.setattr(gateway, "_call_vllm", _success)

    result = await gateway.route("请分析蓝牙耳机市场")
    data = result.to_dict()
    assert data["degraded"] is False
    assert data["actual_provider"] == "vllm"
    assert data["response"] == "primary ok"


@pytest.mark.asyncio
async def test_llm_gateway_uses_ollama_as_primary_when_configured(monkeypatch):
    gateway = LLMGateway(
        GatewayConfig(
            use_mock=False,
            provider_mode="real",
            primary_provider="ollama",
            fallback_provider="vllm",
            vllm_endpoint="http://localhost:8000/v1",
            ollama_endpoint="http://localhost:11434",
        )
    )

    async def _ollama_primary(prompt: str):
        return "ollama primary ok", 10

    monkeypatch.setattr(gateway, "_degrade_to_ollama", _ollama_primary)

    result = await gateway.route("请总结蓝牙耳机卖点")
    data = result.to_dict()
    assert data["degraded"] is False
    assert data["primary_provider"] == "ollama"
    assert data["actual_provider"] == "ollama"
    assert data["selected_node"] == "ollama_primary"
    assert data["response"] == "ollama primary ok"


@pytest.mark.asyncio
async def test_llm_gateway_degrades_from_ollama_to_vllm_under_5_seconds(monkeypatch):
    gateway = LLMGateway(
        GatewayConfig(
            use_mock=False,
            provider_mode="real",
            primary_provider="ollama",
            fallback_provider="vllm",
            fallback_timeout_budget_seconds=5,
            vllm_endpoint="http://localhost:8000/v1",
            ollama_endpoint="http://localhost:11434",
        )
    )

    async def _ollama_failed(prompt: str):
        return "[System] 所有模型不可用，请稍后重试。", 0

    async def _vllm_fallback(node, prompt: str, timeout: float):
        assert timeout <= 5
        return "vllm fallback ok", 18, False

    monkeypatch.setattr(gateway, "_degrade_to_ollama", _ollama_failed)
    monkeypatch.setattr(gateway, "_call_vllm", _vllm_fallback)

    result = await gateway.route("请分析蓝牙耳机市场")
    data = result.to_dict()
    assert data["degraded"] is True
    assert data["primary_provider"] == "ollama"
    assert data["actual_provider"] == "vllm"
    assert data["fallback_provider"] == "vllm"
    assert data["latency_ms"] < 5000
    assert data["response"] == "vllm fallback ok"
