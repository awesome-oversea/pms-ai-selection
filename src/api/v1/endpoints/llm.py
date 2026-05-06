"""
LLM 代理 API 端点
=================

提供统一的大模型代理调用入口，屏蔽底层 Gateway 细节。
当前阶段提供：
- POST /api/v1/llm/route  路由一次请求
- GET  /api/v1/llm/status 获取网关集群状态
"""

from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from src.config.settings import get_settings
from src.core.auth import get_current_user
from src.core.exceptions import IPAllowlistDeniedError, LLMBudgetExceededError, PromptInjectionDetectedError
from src.core.metrics import (
    LLM_BUDGET_REJECTED_TOTAL,
    LLM_COST_USD_TOTAL,
    LLM_TOKENS_TOTAL,
    TENANT_LLM_COST_USD_TOTAL,
    TENANT_LLM_TOKENS_TOTAL,
)
from src.core.rate_limit import _get_client_ip
from src.core.security import add_audit_log
from src.infrastructure.database import get_async_session_factory
from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway, ModelTier
from src.repositories.tenant_quota_repository import TenantQuotaRepository
from src.services.audio_transcription_service import AudioTranscriptionService
from src.services.cpu_model_status_service import CPUModelStatusService
from src.services.cuda_tensorrt_status_service import CudaTensorRTStatusService
from src.services.embedding_benchmark_service import EmbeddingBenchmarkService
from src.services.gpu_resource_pool_service import GPUResourcePoolService
from src.services.inference_health_service import InferenceHealthService
from src.services.model_finetune_service import ModelFinetuneService
from src.services.multimodal_inference_service import MultimodalInferenceService
from src.services.ollama_status_service import OllamaStatusService
from src.services.prompt_guard_service import PromptGuardService
from src.services.prompt_policy_service import PromptPolicyService
from src.services.service_gateway import get_service_gateway
from src.services.triton_status_service import TritonStatusService
from src.services.vllm_status_service import VLLMStatusService
import contextlib

router = APIRouter(prefix="/llm", tags=["LLM代理"])


class LLMRouteRequest(BaseModel):
    prompt: str = Field("", description="用户输入")
    prompt_key: str | None = Field(None, description="可选 prompt 模板键")
    prompt_vars: dict[str, str] | None = Field(None, description="模板渲染变量")
    force_tier: str | None = Field(None, description="可选强制路由层级: heavy/light/filter")
    use_mock: bool | None = Field(None, description="是否使用 mock 模式；为空时按环境决定是否 real-first")
    primary_provider: str | None = Field(None, description="主用模型提供方: ollama/vllm")
    fallback_provider: str | None = Field(None, description="备用模型提供方: ollama/vllm")


class LLMRouteResponse(BaseModel):
    selected_node: str
    model_name: str
    tier: str
    response: str
    tokens_used: int
    latency_ms: float
    cost_usd: float
    degraded: bool
    provider_mode: str
    primary_provider: str
    actual_provider: str
    fallback_provider: str
    prompt_key: str | None = None
    prompt_version: int | None = None
    policy_version: int | None = None
    gray_hit: bool = False
    model_registry_version: int | None = None
    active_model_version: str | None = None
    output_filtered: bool = False
    output_filter_hits: list[str] = Field(default_factory=list)


class LLMMultimodalRouteRequest(BaseModel):
    task_type: str = Field(..., min_length=1, description="多模态任务类型：image_analysis/video_analysis/audio_transcription")
    prompt: str = Field("", description="辅助文本提示")
    image_url: str | None = Field(None, description="图片URL或base64")
    video_url: str | None = Field(None, description="视频URL")
    audio_url: str | None = Field(None, description="音频URL或本地路径")
    audio_base64: str | None = Field(None, description="音频base64")
    title: str | None = Field(None, description="标题")
    description: str | None = Field(None, description="描述")
    language: str | None = Field(None, description="语言提示，如 zh/en/ja")
    use_mock: bool | None = Field(None, description="是否使用 mock 模式")

    @model_validator(mode="after")
    def validate_payload(self):
        if self.task_type not in {"image_analysis", "video_analysis", "audio_transcription"}:
            raise ValueError("task_type 仅支持 image_analysis / video_analysis / audio_transcription")
        if self.task_type == "image_analysis" and not self.image_url:
            raise ValueError("image_analysis 必须提供 image_url")
        if self.task_type == "video_analysis" and not self.video_url:
            raise ValueError("video_analysis 必须提供 video_url")
        if self.task_type == "audio_transcription" and not (self.audio_url or self.audio_base64):
            raise ValueError("audio_transcription 必须提供 audio_url 或 audio_base64")
        return self


class LLMMultimodalRouteResponse(BaseModel):
    task_type: str
    model_name: str
    provider: str
    provider_mode: str
    route_target: str
    result: dict
    degraded: bool = False


class PromptPublishRequest(BaseModel):
    template: str = Field(..., min_length=1)
    description: str = ""


class LLMSafetyFilterRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待审查文本")
    use_mock: bool | None = Field(None, description="是否使用 mock 模式")


class LLMSafetyFilterResponse(BaseModel):
    model_name: str
    provider_mode: str
    reviewed: bool
    filtered_text: str
    matched_keywords: list[str] = Field(default_factory=list)
    blocked: bool = False


class RoutePolicyPublishRequest(BaseModel):
    default_force_tier: str | None = None
    force_tier: str | None = None
    default_use_mock: bool = True
    use_mock: bool = True
    default_api_model_name: str | None = None
    api_model_name: str | None = None
    gray_rollout_percent: int = Field(0, ge=0, le=100)
    gray_tenant_whitelist: list[str] = Field(default_factory=list)


class ModelRegistryPublishRequest(BaseModel):
    active_model_version: str = Field(..., min_length=1)
    active_api_model_name: str = Field(..., min_length=1)
    models: list[dict] = Field(default_factory=list)
    description: str = ""


class ModelFinetuneRequest(BaseModel):
    registry_key: str = Field(default="default", min_length=1)
    train_days: int = Field(default=7, ge=1, le=90)


class EmbeddingBenchmarkRequest(BaseModel):
    sample_count: int = Field(default=1000, ge=1, le=20000)
    batch_size: int = Field(default=256, ge=1, le=4096)
    text_prefix: str = Field(default="cross border product embedding benchmark", min_length=1)
    target_qps: float = Field(default=5000.0, gt=0)
    latency_target_ms: float = Field(default=50.0, gt=0)


def _detect_prompt_injection(prompt: str) -> dict[str, str] | None:
    analysis = PromptGuardService().analyze(prompt)
    if analysis.get("should_block"):
        return {
            "matched_keyword": str(analysis.get("matched_keyword") or analysis.get("risk_level") or "prompt_guard_policy"),
            "risk_level": str(analysis.get("risk_level") or "unknown"),
            "policy_version": str(analysis.get("policy_version") or "0"),
        }
    return None


def _filter_llm_output(text: str) -> tuple[str, list[str]]:
    security = get_settings().security
    filtered = text
    hits: list[str] = []
    for keyword in security.llm_output_guard_keywords:
        if not keyword:
            continue
        if re.search(re.escape(keyword), filtered, flags=re.IGNORECASE):
            hits.append(keyword)
        filtered = re.sub(re.escape(keyword), "[filtered]", filtered, flags=re.IGNORECASE)
    return filtered, hits


def _enforce_llm_security(request: Request, prompt: str, current_user: dict) -> None:
    security = get_settings().security
    client_ip = _get_client_ip(request)
    if security.llm_ip_allowlist and client_ip not in set(security.llm_ip_allowlist):
        add_audit_log(
            action="llm.route",
            actor=current_user,
            target_type="llm_request",
            result="denied",
            detail={
                "reason": "ip_not_allowed",
                "client_ip": client_ip,
            },
        )
        raise IPAllowlistDeniedError(client_ip=client_ip)

    injection_hit = _detect_prompt_injection(prompt)
    if injection_hit:
        matched_keyword = injection_hit["matched_keyword"]
        add_audit_log(
            action="llm.route",
            actor=current_user,
            target_type="llm_request",
            result="denied",
            detail={
                "reason": "prompt_injection_detected",
                "matched_keyword": matched_keyword,
                "risk_level": injection_hit["risk_level"],
                "policy_version": injection_hit["policy_version"],
                "client_ip": client_ip,
            },
        )
        raise PromptInjectionDetectedError(matched_keyword=matched_keyword)


def _build_gateway_config(use_mock: bool | None = None, *, primary_provider: str | None = None, fallback_provider: str | None = None) -> GatewayConfig:
    settings = get_settings()
    environment = (settings.app.environment or "development").lower()
    real_first_envs = {"test", "staging", "preprod"}
    local_runtime_mode = os.getenv("LOCAL_RUNTIME_SCENARIO_MODE", "").strip().lower()
    resolved_use_mock = use_mock
    if resolved_use_mock is None:
        resolved_use_mock = not (environment in real_first_envs or local_runtime_mode == "local-real")

    if resolved_use_mock:
        return GatewayConfig(
            use_mock=True,
            provider_mode="mock",
            primary_provider=primary_provider or "vllm",
            fallback_provider=fallback_provider or "ollama",
            ollama_model_name=settings.llm.primary_model,
        )

    return GatewayConfig(
        use_mock=False,
        provider_mode="real",
        primary_provider=primary_provider or "vllm",
        fallback_provider=fallback_provider or "ollama",
        vllm_endpoint=settings.llm.vllm_endpoint,
        ollama_endpoint=settings.llm.ollama_endpoint,
        ollama_model_name=settings.llm.primary_model,
        vllm_timeout_seconds=settings.llm.request_timeout_seconds,
        ollama_timeout_seconds=min(settings.llm.request_timeout_seconds, 15.0),
        api_key=settings.llm.api_key,
        api_auth_header=settings.llm.api_auth_header,
        api_auth_scheme=settings.llm.api_auth_scheme,
        api_model_name=settings.llm.api_model_name,
        retry_count=settings.llm.request_retry_count,
    )


async def _safe_commit(session) -> None:
    try:
        await session.commit()
    except Exception:
        with contextlib.suppress(Exception):
            await session.rollback()


async def _route_llm_in_process(request: LLMRouteRequest, current_user: dict) -> dict:
    tenant_id = current_user.get("tenant_id")
    quota_type = "llm_cost_usd"
    settings = get_settings()
    environment = (settings.app.environment or "development").lower()
    real_first_runtime = environment in {"test", "staging", "preprod"} or os.getenv(
        "LOCAL_RUNTIME_SCENARIO_MODE", ""
    ).strip().lower() == "local-real"

    session = get_async_session_factory()()
    try:
        policy_service = PromptPolicyService(session, tenant_id=tenant_id)
        final_prompt = request.prompt
        prompt_version = None

        if request.prompt_key:
            resolved_prompt = await policy_service.resolve_prompt(request.prompt_key, request.prompt_vars)
            if resolved_prompt is None:
                raise HTTPException(status_code=404, detail=f"Prompt 不存在: {request.prompt_key}")
            final_prompt = resolved_prompt["rendered_prompt"]
            prompt_version = resolved_prompt["version"]

        if not final_prompt:
            raise HTTPException(status_code=400, detail="prompt 不能为空")

        resolved_policy = await policy_service.resolve_route_policy(final_prompt)
        force_tier_raw = request.force_tier or resolved_policy.get("force_tier")
        if request.use_mock is not None:
            use_mock = request.use_mock
        elif resolved_policy.get("use_mock") is not None:
            use_mock = bool(resolved_policy.get("use_mock"))
            # local-real / real-first runtime should not be silently flipped back to mock
            # by a persisted default route policy. Explicit gray/mock policies and request
            # level overrides still keep higher priority.
            if use_mock and real_first_runtime and not resolved_policy.get("gray_hit", False):
                use_mock = None
        else:
            use_mock = None

        prompt_tokens_estimate = max(1, len(final_prompt) // 3)
        estimated_cost = (prompt_tokens_estimate / 1000) * 0.002
        quota_repo = TenantQuotaRepository(session)
        try:
            allowed, _quota, remaining = await quota_repo.check_quota(
                tenant_id=tenant_id,
                quota_type=quota_type,
                amount=estimated_cost,
                default_limit=100,
            )
        except Exception:
            allowed, _quota, remaining = True, None, 100.0

        if not allowed:
            LLM_BUDGET_REJECTED_TOTAL.labels(tenant_id=tenant_id, quota_type=quota_type).inc()
            add_audit_log(
                action="llm.route",
                actor=current_user,
                target_type="llm_request",
                result="denied",
                detail={
                    "reason": "quota_exceeded",
                    "quota_type": quota_type,
                    "requested": estimated_cost,
                    "remaining": remaining,
                    "prompt_key": request.prompt_key,
                    "prompt_version": prompt_version,
                    "policy_version": resolved_policy.get("version", 0),
                    "gray_hit": resolved_policy.get("gray_hit", False),
                },
            )
            raise LLMBudgetExceededError(tenant_id, quota_type, estimated_cost, remaining)

        config = _build_gateway_config(use_mock=use_mock, primary_provider=request.primary_provider, fallback_provider=request.fallback_provider)
        if resolved_policy.get("api_model_name"):
            config.api_model_name = resolved_policy["api_model_name"]
        gateway = LLMGateway(config)
        force_tier = ModelTier(force_tier_raw) if force_tier_raw else None

        try:
            result = await gateway.route(final_prompt, force_tier=force_tier)
            data = result.to_dict()
        except Exception:
            if not use_mock:
                raise
            data = {
                "selected_node": "mock-fallback",
                "model_name": config.api_model_name or "mock-model",
                "tier": force_tier.value if force_tier else "light",
                "response": f"[mock] {final_prompt[:50]}",
                "tokens_used": max(1, len(final_prompt) // 3),
                "latency_ms": 1.0,
                "cost_usd": round(max(1, len(final_prompt) // 3) / 1000 * 0.0004, 6),
                "degraded": True,
                "provider_mode": "mock",
                "primary_provider": "vllm",
                "actual_provider": "ollama",
                "fallback_provider": "ollama",
            }

        filtered_response, output_filter_hits = _filter_llm_output(str(data.get("response", "")))
        data["response"] = filtered_response
        data["output_filtered"] = bool(output_filter_hits)
        data["output_filter_hits"] = output_filter_hits

        with contextlib.suppress(Exception):
            await quota_repo.consume_quota(
                tenant_id=tenant_id,
                quota_type=quota_type,
                amount=float(data["cost_usd"]),
                default_limit=100,
            )
        await _safe_commit(session)

        LLM_COST_USD_TOTAL.labels(
            tenant_id=tenant_id,
            provider=data["actual_provider"],
            model=data["model_name"],
        ).inc(float(data["cost_usd"]))
        LLM_TOKENS_TOTAL.labels(model=data["model_name"], type="total").inc(int(data["tokens_used"]))
        TENANT_LLM_COST_USD_TOTAL.labels(tenant_id=tenant_id).inc(float(data["cost_usd"]))
        TENANT_LLM_TOKENS_TOTAL.labels(tenant_id=tenant_id).inc(int(data["tokens_used"]))
        add_audit_log(
            action="llm.route",
            actor=current_user,
            target_type="llm_request",
            result="success",
            detail={
                "model_name": data["model_name"],
                "provider": data["actual_provider"],
                "tokens_used": data["tokens_used"],
                "cost_usd": data["cost_usd"],
                "quota_type": quota_type,
                "prompt_key": request.prompt_key,
                "prompt_version": prompt_version,
                "policy_version": resolved_policy.get("version", 0),
                "gray_hit": resolved_policy.get("gray_hit", False),
                "prompt_preview": final_prompt[:200],
                "prompt_length": len(final_prompt),
                "response_preview": str(data.get("response") or "")[:200],
                "response_length": len(str(data.get("response") or "")),
                "output_filtered": data.get("output_filtered", False),
                "output_filter_hits": data.get("output_filter_hits", []),
            },
        )
        return {
            **data,
            "prompt_key": request.prompt_key,
            "prompt_version": prompt_version,
            "policy_version": resolved_policy.get("version", 0),
            "gray_hit": resolved_policy.get("gray_hit", False),
            "model_registry_version": resolved_policy.get("model_registry_version", 0),
            "active_model_version": resolved_policy.get("active_model_version"),
            "output_filtered": data.get("output_filtered", False),
            "output_filter_hits": data.get("output_filter_hits", []),
        }
    finally:
        await session.close()


@router.get("/ollama/status", response_model=dict)
async def get_ollama_status(current_user: dict = Depends(get_current_user)):
    service = OllamaStatusService()
    return await service.build_status()


@router.post("/ollama/benchmark", response_model=dict)
async def run_ollama_benchmark(current_user: dict = Depends(get_current_user)):
    service = OllamaStatusService()
    result = await service.run_latency_benchmark()
    add_audit_log(
        action="llm.ollama.benchmark",
        actor=current_user,
        target_type="ollama_runtime",
        result="success" if result.get("ready") else "warning",
        detail={
            "model": result.get("model"),
            "warm_client_latency_ms": ((result.get("summary") or {}).get("warm_client_latency_ms")),
            "artifact_path": result.get("artifact_path"),
        },
    )
    return result


@router.post("/embedding/benchmark", response_model=dict)
async def run_embedding_benchmark(request: EmbeddingBenchmarkRequest, current_user: dict = Depends(get_current_user)):
    service = EmbeddingBenchmarkService()
    result = service.run_benchmark(
        sample_count=request.sample_count,
        batch_size=request.batch_size,
        text_prefix=request.text_prefix,
        target_qps=request.target_qps,
        latency_target_ms=request.latency_target_ms,
    )
    add_audit_log(
        action="llm.embedding.benchmark",
        actor=current_user,
        target_type="embedding_service",
        result="success" if result.get("passed") else "warning",
        detail={"qps": result.get("qps"), "single_p95_ms": result.get("single_p95_ms"), "provider_mode": result.get("provider_mode")},
    )
    return result


@router.post("/route", response_model=LLMRouteResponse)
async def route_llm(request: LLMRouteRequest, http_request: Request, current_user: dict = Depends(get_current_user)):
    effective_prompt = request.prompt
    if request.prompt_key and request.prompt_vars:
        effective_prompt = effective_prompt or " ".join(str(value) for value in request.prompt_vars.values())
    _enforce_llm_security(http_request, effective_prompt, current_user)

    gateway = get_service_gateway()
    try:
        data = await gateway.route_llm_request(
            payload=request.model_dump(),
            token=current_user.get("authorization"),
            fallback=lambda: _route_llm_in_process(request, current_user),
        )
        if data.get("provider_mode") == "remote-service":
            add_audit_log(
                action="llm.route",
                actor=current_user,
                target_type="llm_request",
                result="success",
                detail={
                    "model_name": data.get("model_name"),
                    "provider": data.get("actual_provider"),
                    "tokens_used": data.get("tokens_used"),
                    "cost_usd": data.get("cost_usd"),
                    "prompt_key": request.prompt_key,
                    "prompt_version": data.get("prompt_version"),
                    "policy_version": data.get("policy_version", 0),
                    "gray_hit": data.get("gray_hit", False),
                    "prompt_preview": effective_prompt[:200],
                    "prompt_length": len(effective_prompt),
                    "response_preview": str(data.get("response") or "")[:200],
                    "response_length": len(str(data.get("response") or "")),
                    "output_filtered": data.get("output_filtered", False),
                    "output_filter_hits": data.get("output_filter_hits", []),
                },
            )
        return LLMRouteResponse(**data)
    except HTTPException:
        raise
    except LLMBudgetExceededError as e:
        raise HTTPException(status_code=e.http_status, detail=e.message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        try:
            data = await _route_llm_in_process(request, current_user)
            return LLMRouteResponse(**data)
        except HTTPException:
            raise
        except LLMBudgetExceededError as inner:
            raise HTTPException(status_code=inner.http_status, detail=inner.message)
        except ValueError as inner:
            raise HTTPException(status_code=400, detail=str(inner))
        except Exception:
            raise HTTPException(status_code=503, detail=f"LLM代理调用失败: {e}")


@router.post("/prompts/{prompt_key}/publish", response_model=dict)
async def publish_prompt(prompt_key: str, request: PromptPublishRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    try:
        service = PromptPolicyService(session, tenant_id=current_user.get("tenant_id"))
        current = await service.publish_prompt(prompt_key, request.template, request.description)
        await _safe_commit(session)
        add_audit_log(
            action="llm.prompt.publish",
            actor=current_user,
            target_type="prompt",
            target_id=prompt_key,
            result="success",
            detail={"version": current.get("version")},
        )
        return current
    finally:
        await session.close()


@router.post("/prompts/{prompt_key}/rollback", response_model=dict)
async def rollback_prompt(prompt_key: str, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    try:
        service = PromptPolicyService(session, tenant_id=current_user.get("tenant_id"))
        current = await service.rollback_prompt(prompt_key)
        if current is None:
            raise HTTPException(status_code=404, detail=f"Prompt 无历史版本可回滚: {prompt_key}")
        await _safe_commit(session)
        add_audit_log(
            action="llm.prompt.rollback",
            actor=current_user,
            target_type="prompt",
            target_id=prompt_key,
            result="success",
            detail={"version": current.get("version")},
        )
        return current
    finally:
        await session.close()


@router.post("/route-policy/publish", response_model=dict)
async def publish_route_policy(request: RoutePolicyPublishRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    try:
        service = PromptPolicyService(session, tenant_id=current_user.get("tenant_id"))
        current = await service.publish_route_policy(request.model_dump())
        await _safe_commit(session)
        add_audit_log(
            action="llm.route_policy.publish",
            actor=current_user,
            target_type="route_policy",
            result="success",
            detail={"version": current.get("version")},
        )
        return current
    finally:
        await session.close()


@router.post("/model-registry/{registry_key}/publish", response_model=dict)
async def publish_model_registry(registry_key: str, request: ModelRegistryPublishRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    try:
        service = PromptPolicyService(session, tenant_id=current_user.get("tenant_id"))
        current = await service.publish_model_registry(registry_key, request.model_dump())
        await _safe_commit(session)
        add_audit_log(
            action="llm.model_registry.publish",
            actor=current_user,
            target_type="model_registry",
            target_id=registry_key,
            result="success",
            detail={"version": current.get("version"), "active_model_version": current.get("active_model_version")},
        )
        return current
    finally:
        await session.close()


@router.post("/model-registry/{registry_key}/rollback", response_model=dict)
async def rollback_model_registry(registry_key: str, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    try:
        service = PromptPolicyService(session, tenant_id=current_user.get("tenant_id"))
        current = await service.rollback_model_registry(registry_key)
        if current is None:
            raise HTTPException(status_code=404, detail=f"模型注册中心无历史版本可回滚: {registry_key}")
        await _safe_commit(session)
        add_audit_log(
            action="llm.model_registry.rollback",
            actor=current_user,
            target_type="model_registry",
            target_id=registry_key,
            result="success",
            detail={"version": current.get("version"), "active_model_version": current.get("active_model_version")},
        )
        return current
    finally:
        await session.close()


@router.post("/model-finetune/run", response_model=dict)
async def run_model_finetune(request: ModelFinetuneRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    try:
        service = ModelFinetuneService(session, tenant_id=current_user.get("tenant_id"))
        result = await service.run_weekly_finetune(registry_key=request.registry_key, train_days=request.train_days)
        await _safe_commit(session)
        add_audit_log(
            action="llm.model_finetune.run",
            actor=current_user,
            target_type="model_registry",
            target_id=request.registry_key,
            result="success",
            detail={"new_model_version": result.get("new_model_version")},
        )
        return result
    finally:
        await session.close()


@router.get("/model-registry/{registry_key}", response_model=dict)
async def get_model_registry(registry_key: str, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    try:
        service = PromptPolicyService(session, tenant_id=current_user.get("tenant_id"))
        current = await service.get_model_registry(registry_key)
        if current is None:
            raise HTTPException(status_code=404, detail=f"模型注册中心不存在: {registry_key}")
        return current
    finally:
        await session.close()


@router.get("/model-registry/{registry_key}/status", response_model=dict)
async def get_model_registry_status(registry_key: str, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    try:
        service = PromptPolicyService(session, tenant_id=current_user.get("tenant_id"))
        current = await service.get_model_registry(registry_key)
        if current is None:
            raise HTTPException(status_code=404, detail=f"模型注册中心不存在: {registry_key}")
        models = current.get("models") or []
        active_model_version = current.get("active_model_version")
        active_record = next((item for item in models if item.get("model_version") == active_model_version), None)
        return {
            "registry_key": registry_key,
            "version": current.get("version", 0),
            "active_model_version": active_model_version,
            "active_api_model_name": current.get("active_api_model_name"),
            "model_count": len(models),
            "active_model": active_record,
            "gray_release_ready": bool(active_model_version and current.get("active_api_model_name")),
            "rollback_ready": current.get("version", 0) > 1,
            "models": models,
        }
    finally:
        await session.close()


@router.post("/safety/filter", response_model=LLMSafetyFilterResponse)
async def filter_llm_output(request: LLMSafetyFilterRequest, current_user: dict = Depends(get_current_user)):
    filtered_text, matched_keywords = _filter_llm_output(request.text)
    return LLMSafetyFilterResponse(
        model_name="Phi-3-mini",
        provider_mode="mock" if request.use_mock is not False else "real",
        reviewed=True,
        filtered_text=filtered_text,
        matched_keywords=matched_keywords,
        blocked=bool(matched_keywords),
    )


@router.post("/multimodal/route", response_model=LLMMultimodalRouteResponse)
async def route_multimodal(request: LLMMultimodalRouteRequest, current_user: dict = Depends(get_current_user)):
    service = MultimodalInferenceService()
    speech_model = getattr(get_settings().llm, "speech_model", "whisper-tiny")
    if request.task_type == "image_analysis":
        result = await service.analyze_image(
            image_url=str(request.image_url or ""),
            prompt=request.prompt,
            analysis_type="features",
            use_mock=request.use_mock,
        )
        return LLMMultimodalRouteResponse(
            task_type=request.task_type,
            model_name=str(result.get("model_name") or service.model_name),
            provider=str(result.get("provider") or "mock-qwen35"),
            provider_mode=str(result.get("provider_mode") or "mock"),
            route_target="multimodal_image_analysis",
            result=result,
            degraded=bool(result.get("degraded", True)),
        )

    if request.task_type == "audio_transcription":
        result = await AudioTranscriptionService().transcribe_audio(
            audio_url=str(request.audio_url or ""),
            audio_base64=request.audio_base64,
            language=request.language,
            prompt=request.prompt,
            title=request.title,
            description=request.description,
            use_mock=request.use_mock,
        )
        return LLMMultimodalRouteResponse(
            task_type=request.task_type,
            model_name=str(result.get("model_name") or speech_model),
            provider=str(result.get("provider") or "mock-whisper"),
            provider_mode=str(result.get("provider_mode") or "mock"),
            route_target="whisper_audio_transcription",
            result=result,
            degraded=bool(result.get("degraded", True)),
        )

    result = await service.analyze_video(
        video_url=str(request.video_url or ""),
        video_title=str(request.title or ""),
        video_description=str(request.description or ""),
        prompt=request.prompt,
        use_mock=request.use_mock,
    )
    return LLMMultimodalRouteResponse(
        task_type=request.task_type,
        model_name=str(result.get("model_name") or service.model_name),
        provider=str(result.get("provider") or "mock-qwen35"),
        provider_mode=str(result.get("provider_mode") or "mock"),
        route_target="multimodal_video_analysis",
        result=result,
        degraded=bool(result.get("degraded", True)),
    )


@router.get("/status", response_model=dict)
async def llm_status(current_user: dict = Depends(get_current_user)):
    config = _build_gateway_config(use_mock=None)
    gateway = LLMGateway(config)
    service_gateway = get_service_gateway()
    vllm_status = VLLMStatusService().build_status()
    gpu_status = GPUResourcePoolService().build_status()
    cuda_tensorrt_status = CudaTensorRTStatusService().build_status()
    triton_status = TritonStatusService().build_status()
    ollama_status = await OllamaStatusService().build_status()
    multimodal_status = MultimodalInferenceService().build_status()
    cpu_model_status = CPUModelStatusService().build_status()
    inference_health = await InferenceHealthService().build_status()
    return {
        **gateway.get_cluster_status(),
        "effective_provider_mode": config.provider_mode,
        "effective_use_mock": config.use_mock,
        "service_mode": service_gateway.build_status()["llm"],
        "fallback_enabled": service_gateway.build_status()["enable_fallback"],
        "vllm": vllm_status,
        "gpu": gpu_status,
        "cuda_tensorrt": cuda_tensorrt_status,
        "triton": triton_status,
        "ollama": ollama_status,
        "multimodal": multimodal_status,
        "cpu_model": cpu_model_status,
        "inference_health": inference_health,
    }


@router.get("/vllm/status", response_model=dict)
async def get_vllm_status(current_user: dict = Depends(get_current_user)):
    return VLLMStatusService().build_status()


@router.get("/gpu/status", response_model=dict)
async def get_gpu_status(current_user: dict = Depends(get_current_user)):
    return GPUResourcePoolService().build_status()


@router.get("/cuda-tensorrt/status", response_model=dict)
async def get_cuda_tensorrt_status(current_user: dict = Depends(get_current_user)):
    return CudaTensorRTStatusService().build_status()


@router.get("/ollama/status", response_model=dict)
async def get_ollama_status(current_user: dict = Depends(get_current_user)):
    return await OllamaStatusService().build_status()


@router.get("/multimodal/status", response_model=dict)
async def get_multimodal_status(current_user: dict = Depends(get_current_user)):
    return MultimodalInferenceService().build_status()


@router.get("/cpu-model/status", response_model=dict)
async def get_cpu_model_status(current_user: dict = Depends(get_current_user)):
    return CPUModelStatusService().build_status()


@router.get("/inference/health", response_model=dict)
async def get_inference_health_status(current_user: dict = Depends(get_current_user)):
    return await InferenceHealthService().build_status()
