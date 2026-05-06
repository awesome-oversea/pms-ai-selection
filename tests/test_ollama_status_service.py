from __future__ import annotations

import os
from types import SimpleNamespace

import httpx
import pytest
from src.services.ollama_status_service import OllamaStatusService

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")


class _FakeClient:
    def __init__(self, endpoint: str, timeout_seconds: float, model_name: str = "qwen2.5:1.5b") -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.model_name = model_name
        self._responses = [
            {
                "model": model_name,
                "response": "本地模型冷启动响应",
                "latency_ms": 18250.0,
                "total_duration": 17_900_000_000,
                "load_duration": 7_100_000_000,
                "prompt_eval_duration": 4_200_000_000,
                "eval_duration": 4_800_000_000,
                "prompt_eval_count": 32,
                "eval_count": 40,
            },
            {
                "model": model_name,
                "response": "本地模型热启动响应",
                "latency_ms": 6350.0,
                "total_duration": 6_100_000_000,
                "load_duration": 0,
                "prompt_eval_duration": 2_000_000_000,
                "eval_duration": 3_600_000_000,
                "prompt_eval_count": 32,
                "eval_count": 38,
            },
            {
                "model": model_name,
                "response": "1. 看趋势 2. 看利润 3. 看风险",
                "latency_ms": 7425.0,
                "total_duration": 7_000_000_000,
                "load_duration": 0,
                "prompt_eval_duration": 2_200_000_000,
                "eval_duration": 4_100_000_000,
                "prompt_eval_count": 36,
                "eval_count": 44,
            },
        ]

    async def healthcheck(self) -> dict[str, object]:
        return {
            "reachable": True,
            "endpoint": self.endpoint,
            "model_count": 1,
            "models": [self.model_name],
        }

    async def generate(self, prompt: str, model_name: str | None = None) -> dict[str, object]:
        return dict(self._responses.pop(0))


class _TimeoutClient:
    def __init__(self, endpoint: str, timeout_seconds: float, model_name: str = "qwen2.5:1.5b") -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.model_name = model_name

    async def healthcheck(self) -> dict[str, object]:
        return {
            "reachable": True,
            "endpoint": self.endpoint,
            "model_count": 1,
            "models": [self.model_name],
        }

    async def generate(self, prompt: str, model_name: str | None = None) -> dict[str, object]:
        raise httpx.ReadTimeout("benchmark generate timed out")


class _ReasoningTimeoutClient(_FakeClient):
    async def generate(self, prompt: str, model_name: str | None = None) -> dict[str, object]:
        if len(self._responses) == 1:
            raise httpx.ReadTimeout("reasoning benchmark timed out")
        return await super().generate(prompt, model_name=model_name)


@pytest.mark.asyncio
async def test_ollama_status_service_benchmark_and_status(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.services.ollama_status_service.get_settings",
        lambda: SimpleNamespace(
            llm=SimpleNamespace(ollama_endpoint="http://localhost:11434", request_timeout_seconds=20.0),
            service_modes=SimpleNamespace(enable_fallback=True, llm_mode="remote-service", llm_base_url="http://localhost:8000/api/v1"),
        ),
    )
    monkeypatch.setattr("src.services.ollama_status_service.OllamaClient", _FakeClient)

    artifact_path = tmp_path / "ollama_latency_benchmark.json"
    service = OllamaStatusService(artifact_path=artifact_path)

    benchmark = await service.run_latency_benchmark()
    assert benchmark["ready"] is True
    assert benchmark["model"] == "qwen2.5:1.5b"
    assert benchmark["summary"]["cold_start_load_duration_ms"] == 7100.0
    assert benchmark["summary"]["warm_client_latency_ms"] == 6350.0
    assert benchmark["summary"]["developer_ready"] is True
    assert benchmark["artifact_path"].endswith("ollama_latency_benchmark.json")
    assert artifact_path.exists()

    status = await service.build_status()
    assert status["provider"] == "ollama"
    assert status["ready"] is True
    assert status["latency_profile"]["warm_client_latency_ms"] == 6350.0
    assert status["sample_generation"]["source"] == "benchmark-artifact"
    assert status["model_strategy"]["primary_local_model"] == "qwen2.5:1.5b"
    assert status["degrade_chain"]["path"] == ["vllm", "ollama", "remote-service"]
    assert status["benchmark_artifact_path"].endswith("ollama_latency_benchmark.json")


@pytest.mark.asyncio
async def test_ollama_status_service_benchmark_returns_blocked_payload_on_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.services.ollama_status_service.get_settings",
        lambda: SimpleNamespace(
            llm=SimpleNamespace(ollama_endpoint="http://localhost:11434", request_timeout_seconds=20.0),
            service_mode=SimpleNamespace(enable_fallback=True, llm_mode="remote-service", llm_base_url="http://localhost:8000/api/v1"),
        ),
    )
    monkeypatch.setattr("src.services.ollama_status_service.OllamaClient", _TimeoutClient)

    artifact_path = tmp_path / "ollama_latency_benchmark.json"
    service = OllamaStatusService(artifact_path=artifact_path)

    benchmark = await service.run_latency_benchmark()
    assert benchmark["ready"] is False
    assert benchmark["benchmark_stage"] == "short-prompt-generate"
    assert "timed out" in benchmark["blocked_reason"]
    assert benchmark["timeout_seconds"] == 60.0
    assert benchmark["artifact_path"].endswith("ollama_latency_benchmark.json")
    assert artifact_path.exists()


@pytest.mark.asyncio
async def test_ollama_status_service_benchmark_keeps_short_prompt_metrics_when_reasoning_times_out(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.services.ollama_status_service.get_settings",
        lambda: SimpleNamespace(
            llm=SimpleNamespace(ollama_endpoint="http://localhost:11434", request_timeout_seconds=20.0),
            service_mode=SimpleNamespace(enable_fallback=True, llm_mode="remote-service", llm_base_url="http://localhost:8000/api/v1"),
        ),
    )
    monkeypatch.setattr("src.services.ollama_status_service.OllamaClient", _ReasoningTimeoutClient)

    artifact_path = tmp_path / "ollama_latency_benchmark.json"
    service = OllamaStatusService(artifact_path=artifact_path)

    benchmark = await service.run_latency_benchmark()
    assert benchmark["ready"] is True
    assert benchmark["summary"]["warm_client_latency_ms"] == 6350.0
    assert benchmark["summary"]["reasoning_client_latency_ms"] is None
    assert benchmark["benchmark_warning"] == "reasoning benchmark timed out"
    assert benchmark["artifact_path"].endswith("ollama_latency_benchmark.json")
    assert artifact_path.exists()
