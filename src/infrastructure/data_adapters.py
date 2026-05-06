from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.services.external_signal_service import ExternalSignalService


class BaseDataAdapter(ABC):
    adapter_key: str

    @abstractmethod
    async def collect(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        raise NotImplementedError


class RSSNewsAdapter(BaseDataAdapter):
    adapter_key = "media_rss"

    def __init__(self, service: ExternalSignalService | None = None) -> None:
        self.service = service or ExternalSignalService()

    async def collect(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        payload = await self.service.collect_rss_signals(query=query, mode=mode)
        return {"adapter": self.adapter_key, "query": query, "mode": mode, "payload": payload}


class MinimalRealSignalAdapter(BaseDataAdapter):
    adapter_key = "minimal_real"

    def __init__(self, service: ExternalSignalService | None = None) -> None:
        self.service = service or ExternalSignalService()

    async def collect(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        payload = await self.service.collect_minimal_real_signals(query=query, mode=mode)
        return {"adapter": self.adapter_key, "query": query, "mode": mode, "payload": payload}


class BusinessRealSignalAdapter(BaseDataAdapter):
    adapter_key = "business_real"

    def __init__(self, service: ExternalSignalService | None = None) -> None:
        self.service = service or ExternalSignalService()

    async def collect(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        payload = await self.service.collect_business_real_signals(query=query, mode=mode)
        return {"adapter": self.adapter_key, "query": query, "mode": mode, "payload": payload}


class GDELTSignalAdapter(BaseDataAdapter):
    adapter_key = "gdelt_real"

    def __init__(self, service: ExternalSignalService | None = None) -> None:
        self.service = service or ExternalSignalService()

    async def collect(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        payload = await self.service.collect_gdelt_event_signals(query=query, mode=mode)
        return {"adapter": self.adapter_key, "query": query, "mode": mode, "payload": payload}


def build_data_adapter(adapter_key: str, service: ExternalSignalService | None = None) -> BaseDataAdapter:
    normalized = adapter_key.strip().lower()
    if normalized in {"rss", "media_rss", "rss_news"}:
        return RSSNewsAdapter(service=service)
    if normalized in {"minimal", "minimal_real", "minimal-real"}:
        return MinimalRealSignalAdapter(service=service)
    if normalized in {"business", "business_real", "business-real"}:
        return BusinessRealSignalAdapter(service=service)
    if normalized in {"gdelt", "gdelt_real", "gdelt-real", "media_news"}:
        return GDELTSignalAdapter(service=service)
    raise ValueError(f"不支持的适配器: {adapter_key}")


def list_data_adapters() -> list[dict[str, str]]:
    return [
        {"adapter_key": "rss", "resolved_key": RSSNewsAdapter.adapter_key, "description": "RSS媒体资讯订阅适配器"},
        {"adapter_key": "minimal-real", "resolved_key": MinimalRealSignalAdapter.adapter_key, "description": "Wikipedia/GitHub/HN 最小真实信号适配器"},
        {"adapter_key": "business-real", "resolved_key": BusinessRealSignalAdapter.adapter_key, "description": "跨境电商业务外部真实信号适配器"},
        {"adapter_key": "gdelt-real", "resolved_key": GDELTSignalAdapter.adapter_key, "description": "GDELT事件分类与品类关联适配器"},
    ]
