from __future__ import annotations

from fastapi import FastAPI

from src.config.settings import get_settings
from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway

app = FastAPI(title="pms-llm-service")


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "llm", "mode": get_settings().service_mode.llm_mode}


@app.get("/status")
async def status() -> dict:
    settings = get_settings().service_mode
    gateway = LLMGateway(GatewayConfig(use_mock=True, provider_mode="mock"))
    return {
        "service": "llm",
        "mode": settings.llm_mode,
        "timeout_seconds": settings.llm_timeout_seconds,
        "fallback_enabled": settings.enable_fallback,
        "gateway": gateway.build_status(),
        "rollback": "set SERVICE_MODE_LLM_MODE=in-process",
    }
