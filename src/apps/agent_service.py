from __future__ import annotations

from fastapi import FastAPI

from src.config.settings import get_settings
from src.services.dify_workflow_service import DifyWorkflowService

app = FastAPI(title="pms-agent-service")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "service": "agent-service",
        "mode": get_settings().service_mode.agent_mode,
    }


@app.get("/status")
async def status() -> dict:
    settings = get_settings()
    service_mode = settings.service_mode
    dify_runtime = DifyWorkflowService(settings=settings.dify).build_runtime_status()
    return {
        "service": "agent-service",
        "mode": service_mode.agent_mode,
        "timeout_seconds": service_mode.agent_timeout_seconds,
        "fallback_enabled": service_mode.enable_fallback,
        "deployment": "k8s/agent-service.yml",
        "capabilities": [
            "agent-orchestration",
            "langgraph-compatible",
            "autogen-compatible",
            "crewai-compatible",
            "dify-compatible",
        ],
        "supported_frameworks": [
            "langgraph-compatible",
            "autogen-compatible",
            "langchain-compatible",
            "crewai-compatible",
            "ray-compatible",
            "dify-compatible",
        ],
        "dify": dify_runtime,
        "rollback": "set SERVICE_MODE_AGENT_MODE=in-process",
    }
