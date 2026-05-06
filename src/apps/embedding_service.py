from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.config.settings import get_settings
from src.services.embedding import EmbeddingService
from src.services.embedding_benchmark_service import EmbeddingBenchmarkService

app = FastAPI(title="pms-embedding-service")


class EmbedRequest(BaseModel):
    texts: list[str] = Field(default_factory=list)
    batch_size: int = Field(default=256, ge=1, le=4096)


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "embedding", "mode": get_settings().service_mode.embedding_mode}


@app.get("/status")
async def status() -> dict:
    settings = get_settings().service_mode
    service = EmbeddingService()
    return {
        "service": "embedding",
        "mode": settings.embedding_mode,
        "timeout_seconds": settings.embedding_timeout_seconds,
        "fallback_enabled": settings.enable_fallback,
        "provider_mode": service.provider_mode,
        "dimension": service.dimension,
        "rollback": "set SERVICE_MODE_EMBEDDING_MODE=in-process",
    }


@app.post("/embed")
async def embed(request: EmbedRequest) -> dict:
    service = EmbeddingService()
    vectors = service.encode(request.texts, batch_size=request.batch_size)
    return {"vector_count": len(vectors), "dimension": len(vectors[0]) if vectors else 0, "vectors": vectors}


@app.post("/benchmark")
async def benchmark(request: EmbedRequest) -> dict:
    return EmbeddingBenchmarkService().run_benchmark(sample_count=max(len(request.texts), 1), batch_size=request.batch_size)
