from __future__ import annotations

from typing import Any

import httpx

from src.config.settings import get_settings
from src.infrastructure.tracing import get_request_id, get_trace_id


class RemoteLLMClient:
    async def route(self, *, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
        settings = get_settings().service_mode
        headers = {
            "X-Trace-ID": get_trace_id(),
            "X-Request-ID": get_request_id(),
        }
        if token:
            headers["Authorization"] = token
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/llm/route",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("data", data)

    async def healthcheck(self) -> dict[str, Any]:
        settings = get_settings().service_mode
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            resp = await client.get(f"{settings.llm_base_url.rstrip('/')}/health")
            resp.raise_for_status()
            payload = resp.json()
        return payload

    def build_status(self) -> dict[str, Any]:
        settings = get_settings().service_mode
        base_url = settings.llm_base_url.rstrip('/')
        return {
            "mode": settings.llm_mode,
            "base_url": settings.llm_base_url,
            "timeout_seconds": settings.llm_timeout_seconds,
            "fallback_enabled": settings.enable_fallback,
            "health_endpoint": f"{base_url}/health",
            "status_endpoint": f"{base_url}/status",
            "route_endpoint": f"{base_url}/llm/route",
            "deployment": "k8s/llm-service.yml",
        }
