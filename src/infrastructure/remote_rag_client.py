from __future__ import annotations

from typing import Any

import httpx

from src.config.settings import get_settings
from src.infrastructure.tracing import get_request_id, get_trace_id


class RemoteRAGClient:
    async def query(self, *, query: str, top_k: int, threshold: float, token: str | None = None) -> dict[str, Any]:
        settings = get_settings().service_mode
        headers = {
            "X-Trace-ID": get_trace_id(),
            "X-Request-ID": get_request_id(),
        }
        if token:
            headers["Authorization"] = token
        async with httpx.AsyncClient(timeout=settings.rag_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.rag_base_url.rstrip('/')}/knowledge/query",
                headers=headers,
                json={"query": query, "top_k": top_k, "threshold": threshold},
            )
            resp.raise_for_status()
            payload = resp.json()
        return payload.get("data", payload)

    async def healthcheck(self) -> dict[str, Any]:
        settings = get_settings().service_mode
        async with httpx.AsyncClient(timeout=settings.rag_timeout_seconds) as client:
            resp = await client.get(f"{settings.rag_base_url.rstrip('/')}/health")
            resp.raise_for_status()
            payload = resp.json()
        return payload

    def build_status(self) -> dict[str, Any]:
        settings = get_settings().service_mode
        base_url = settings.rag_base_url.rstrip('/')
        return {
            "mode": settings.rag_mode,
            "base_url": settings.rag_base_url,
            "timeout_seconds": settings.rag_timeout_seconds,
            "fallback_enabled": settings.enable_fallback,
            "health_endpoint": f"{base_url}/health",
            "status_endpoint": f"{base_url}/status",
            "deployment": "k8s/rag-service.yml",
        }
