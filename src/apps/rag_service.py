from __future__ import annotations

from fastapi import FastAPI

from src.config.settings import get_settings
from src.services.llamaindex_rag_service import LlamaIndexRAGService

app = FastAPI(title="pms-rag-service")


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "rag", "mode": get_settings().service_mode.rag_mode}


@app.get("/status")
async def status() -> dict:
    settings = get_settings().service_mode
    return {
        "service": "rag",
        "mode": settings.rag_mode,
        "timeout_seconds": settings.rag_timeout_seconds,
        "fallback_enabled": settings.enable_fallback,
        "llamaindex": LlamaIndexRAGService().build_status(),
        "rollback": "set SERVICE_MODE_RAG_MODE=in-process",
    }
