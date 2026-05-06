from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from src.config.settings import get_settings
from src.infrastructure.remote_llm_client import RemoteLLMClient
from src.infrastructure.remote_rag_client import RemoteRAGClient


class ServiceGateway:
    def __init__(self) -> None:
        self.settings = get_settings().service_mode
        self.remote_rag = RemoteRAGClient()
        self.remote_llm = RemoteLLMClient()

    async def route_rag_query(
        self,
        *,
        query: str,
        top_k: int,
        threshold: float,
        token: str | None,
        fallback: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        if self.settings.rag_mode != "remote-service":
            return await fallback()
        try:
            return await self.remote_rag.query(query=query, top_k=top_k, threshold=threshold, token=token)
        except Exception:
            if not self.settings.enable_fallback:
                raise
            return await fallback()

    async def route_llm_request(
        self,
        *,
        payload: dict[str, Any],
        token: str | None,
        fallback: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        if self.settings.llm_mode != "remote-service":
            return await fallback()
        try:
            return await self.remote_llm.route(payload=payload, token=token)
        except Exception:
            if not self.settings.enable_fallback:
                raise
            return await fallback()

    def build_status(self) -> dict[str, Any]:
        return {
            "rag": self.remote_rag.build_status(),
            "llm": self.remote_llm.build_status(),
            "enable_fallback": self.settings.enable_fallback,
            "strategy": {
                "compatibility_mode": "dual-path",
                "fallback_policy": "remote-service -> in-process",
                "gray_release": True,
                "rollback": "switch service_mode back to in-process",
            },
        }


_service_gateway_singleton: ServiceGateway | None = None


def get_service_gateway() -> ServiceGateway:
    global _service_gateway_singleton
    if _service_gateway_singleton is None:
        _service_gateway_singleton = ServiceGateway()
    return _service_gateway_singleton
