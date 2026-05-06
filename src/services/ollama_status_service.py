from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config.settings import get_settings
from src.infrastructure.ollama_client import OllamaClient

_OLLAMA_BENCHMARK_ARTIFACT = Path("artifacts/llm/ollama_latency_benchmark.json")
_STATUS_PROMPT = "请只输出“本地模型在线”六个字，不要添加任何其他内容。"
_REASONING_PROMPT = "请只输出三行，每行不超过6个汉字：音质续航、佩戴舒适、供应稳定。不要解释。"


class OllamaStatusService:
    def __init__(self, artifact_path: Path | None = None) -> None:
        self.artifact_path = artifact_path or _OLLAMA_BENCHMARK_ARTIFACT

    @staticmethod
    def _ns_to_ms(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value) / 1_000_000, 3)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _preview(text: Any, limit: int = 120) -> str | None:
        if text is None:
            return None
        rendered = str(text).strip()
        if not rendered:
            return None
        return rendered[:limit]

    @staticmethod
    def _exception_reason(exc: Exception) -> str:
        message = str(exc).strip()
        return message or exc.__class__.__name__

    @classmethod
    def _generation_metrics(cls, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": payload.get("model"),
            "response_preview": cls._preview(payload.get("response")),
            "client_latency_ms": payload.get("latency_ms"),
            "total_duration_ms": cls._ns_to_ms(payload.get("total_duration")),
            "load_duration_ms": cls._ns_to_ms(payload.get("load_duration")),
            "prompt_eval_duration_ms": cls._ns_to_ms(payload.get("prompt_eval_duration")),
            "eval_duration_ms": cls._ns_to_ms(payload.get("eval_duration")),
            "prompt_eval_count": payload.get("prompt_eval_count"),
            "eval_count": payload.get("eval_count"),
        }

    def _load_benchmark_artifact(self) -> dict[str, Any] | None:
        if not self.artifact_path.exists():
            return None
        try:
            payload = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write_benchmark_artifact(self, payload: dict[str, Any]) -> str:
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(self.artifact_path).replace("\\", "/")

    @staticmethod
    def _pick_primary_model(runtime: dict[str, Any], fallback_model: str) -> str:
        models = runtime.get("models") or []
        normalized = [str(model) for model in models if model]
        if fallback_model in normalized:
            return fallback_model
        return normalized[0] if normalized else fallback_model

    def _build_model_strategy(self, runtime: dict[str, Any], fallback_model: str) -> dict[str, Any]:
        primary_model = self._pick_primary_model(runtime, fallback_model)
        return {
            "primary_local_model": primary_model,
            "lightweight_local": {
                "model": primary_model,
                "recommended_for": [
                    "短 prompt 冒烟验证",
                    "本地开发联调",
                    "vLLM 不可用时的轻量降级",
                ],
                "not_recommended_for": [
                    "长上下文深度推理",
                    "高精度报告生成",
                    "高并发主链路",
                ],
            },
            "higher_spec_path": {
                "preferred_provider": "vllm",
                "recommended_for": [
                    "复杂推理",
                    "多步骤规划",
                    "高质量结构化输出",
                ],
                "fallback_provider": "remote-service",
            },
            "selection_rule": "vLLM 优先承接高规格推理，Ollama 承接本地轻量与降级链路，remote-service 作为末级兜底。",
        }

    def _build_degrade_chain(self) -> dict[str, Any]:
        settings = get_settings()
        service_mode_settings = getattr(settings, "service_mode", None) or getattr(settings, "service_modes", None)
        fallback_enabled = bool(getattr(service_mode_settings, "enable_fallback", False))
        remote_service_mode = getattr(service_mode_settings, "llm_mode", None)
        remote_service_base_url = getattr(service_mode_settings, "llm_base_url", None)
        return {
            "path": ["vllm", "ollama", "remote-service"],
            "fallback_enabled": fallback_enabled,
            "remote_service_mode": remote_service_mode,
            "remote_service_base_url": remote_service_base_url,
            "steps": [
                {
                    "order": 1,
                    "provider": "vllm",
                    "role": "primary",
                    "usage": "高规格推理主链路",
                },
                {
                    "order": 2,
                    "provider": "ollama",
                    "role": "local-fallback",
                    "usage": "本地轻量模型降级",
                },
                {
                    "order": 3,
                    "provider": "remote-service",
                    "role": "last-mile-fallback",
                    "usage": "本地推理不可用时兜底",
                },
            ],
        }

    def _build_blocked_benchmark_payload(
        self,
        *,
        endpoint: str,
        model: str,
        runtime: dict[str, Any],
        reason: str,
        stage: str,
        timeout_seconds: float,
        partial_results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "provider": "ollama",
            "endpoint": endpoint,
            "model": model,
            "ready": False,
            "runtime": runtime,
            "measured_at": datetime.now(UTC).isoformat(),
            "blocked_reason": reason,
            "benchmark_stage": stage,
            "timeout_seconds": timeout_seconds,
        }
        if partial_results:
            payload["partial_results"] = partial_results
        payload["artifact_path"] = self._write_benchmark_artifact(payload)
        return payload

    async def run_latency_benchmark(self) -> dict[str, Any]:
        settings = get_settings().llm
        fallback_model = "qwen2.5:1.5b"
        benchmark_timeout_seconds = max(settings.request_timeout_seconds, 60.0)
        client = OllamaClient(endpoint=settings.ollama_endpoint, timeout_seconds=benchmark_timeout_seconds)
        runtime = await client.healthcheck()
        primary_model = self._pick_primary_model(runtime, fallback_model)

        if not runtime.get("reachable") or runtime.get("model_count", 0) <= 0:
            return self._build_blocked_benchmark_payload(
                endpoint=settings.ollama_endpoint,
                model=primary_model,
                runtime=runtime,
                reason=str(runtime.get("error") or "ollama runtime not reachable"),
                stage="healthcheck",
                timeout_seconds=benchmark_timeout_seconds,
            )

        partial_results: dict[str, Any] = {}
        try:
            cold_short = self._generation_metrics(await client.generate(_STATUS_PROMPT, model_name=primary_model))
            partial_results["short_prompt_cold"] = cold_short
            warm_short = self._generation_metrics(await client.generate(_STATUS_PROMPT, model_name=primary_model))
            partial_results["short_prompt_warm"] = warm_short
        except Exception as exc:
            return self._build_blocked_benchmark_payload(
                endpoint=settings.ollama_endpoint,
                model=primary_model,
                runtime=runtime,
                reason=self._exception_reason(exc),
                stage="short-prompt-generate",
                timeout_seconds=benchmark_timeout_seconds,
                partial_results=partial_results or None,
            )

        reasoning_short = None
        reasoning_warning = None
        try:
            reasoning_short = self._generation_metrics(await client.generate(_REASONING_PROMPT, model_name=primary_model))
            partial_results["reasoning_prompt"] = reasoning_short
        except Exception as exc:
            reasoning_warning = self._exception_reason(exc)

        cold_latency = cold_short.get("client_latency_ms") or 0.0
        warm_latency = warm_short.get("client_latency_ms") or 0.0
        reasoning_latency = reasoning_short.get("client_latency_ms") if isinstance(reasoning_short, dict) else None
        speedup_ratio = round(cold_latency / warm_latency, 3) if warm_latency else None

        payload = {
            "provider": "ollama",
            "endpoint": settings.ollama_endpoint,
            "model": primary_model,
            "ready": True,
            "runtime": runtime,
            "measured_at": datetime.now(UTC).isoformat(),
            "timeout_seconds": benchmark_timeout_seconds,
            "short_prompt_cold": cold_short,
            "short_prompt_warm": warm_short,
            "reasoning_prompt": reasoning_short,
            "benchmark_warning": reasoning_warning,
            "summary": {
                "cold_start_client_latency_ms": cold_latency,
                "cold_start_load_duration_ms": cold_short.get("load_duration_ms"),
                "warm_client_latency_ms": warm_latency,
                "warm_load_duration_ms": warm_short.get("load_duration_ms"),
                "reasoning_client_latency_ms": reasoning_latency,
                "reasoning_load_duration_ms": reasoning_short.get("load_duration_ms") if isinstance(reasoning_short, dict) else None,
                "repeat_speedup_ratio": speedup_ratio,
                "developer_ready": bool(warm_latency and warm_latency <= 15000),
            },
        }
        payload["artifact_path"] = self._write_benchmark_artifact(payload)
        return payload

    async def build_status(self) -> dict[str, Any]:
        settings = get_settings().llm
        fallback_model = "qwen2.5:1.5b"
        benchmark = self._load_benchmark_artifact()
        if benchmark:
            runtime = benchmark.get("runtime") or {}
            primary_model = self._pick_primary_model(runtime, fallback_model)
        else:
            client = OllamaClient(endpoint=settings.ollama_endpoint, timeout_seconds=min(settings.request_timeout_seconds, 15.0))
            runtime = await client.healthcheck()
            primary_model = self._pick_primary_model(runtime, fallback_model)

        sample_generation = None
        if benchmark and benchmark.get("model") == primary_model:
            warm_short = benchmark.get("short_prompt_warm") or benchmark.get("short_prompt_cold") or {}
            sample_generation = {
                "model": primary_model,
                "response_preview": warm_short.get("response_preview"),
                "latency_ms": warm_short.get("client_latency_ms"),
                "load_duration_ms": warm_short.get("load_duration_ms"),
                "source": "benchmark-artifact",
            }
        elif runtime.get("reachable") and runtime.get("model_count", 0) > 0:
            sample_generation = {
                "model": primary_model,
                "response_preview": None,
                "latency_ms": None,
                "load_duration_ms": None,
                "source": "runtime-healthcheck",
            }

        latency_profile = benchmark.get("summary") if isinstance(benchmark, dict) else None
        benchmark_artifact_path = str(self.artifact_path).replace("\\", "/") if self.artifact_path.exists() else None

        return {
            "endpoint": settings.ollama_endpoint,
            "timeout_seconds": min(settings.request_timeout_seconds, 15.0),
            "fallback_model": fallback_model,
            "primary_model": primary_model,
            "runtime": runtime,
            "sample_generation": sample_generation,
            "latency_profile": latency_profile,
            "benchmark_artifact_path": benchmark_artifact_path,
            "model_strategy": self._build_model_strategy(runtime, fallback_model),
            "degrade_chain": self._build_degrade_chain(),
            "ready": bool(runtime.get("reachable")),
            "provider": "ollama",
            "degraded": not bool(runtime.get("reachable")),
            "install_ready": bool(runtime.get("reachable")),
            "rollback": "set LLM_OLLAMA_ENABLED=false or keep provider_mode=mock",
            "blocked_reason": None if runtime.get("reachable") else (runtime.get("error") or "ollama runtime not reachable"),
        }
