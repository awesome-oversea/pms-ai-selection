from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from src.config.settings import CollectionAPISettings, get_settings

DEFAULT_FALLBACK_PROXIES = (
    "http://proxy-1.internal:8080",
    "http://proxy-2.internal:8080",
)


class ProxyProviderService:
    """代理服务接入准备：配置解析、状态输出与可选实机探测。"""

    SUPPORTED_PROVIDERS = ("none", "static", "self_hosted", "brightdata", "oxylabs")

    def __init__(self, settings: CollectionAPISettings | None = None) -> None:
        self.settings = settings or get_settings().collection_api

    @staticmethod
    def _split_proxy_entries(raw_value: str | None) -> list[str]:
        if not raw_value:
            return []
        normalized = raw_value.replace(";", ",")
        entries: list[str] = []
        for chunk in normalized.splitlines():
            entries.extend(part.strip() for part in chunk.split(",") if part.strip())
        return entries

    @staticmethod
    def _normalize_provider(provider: str | None, *, has_static_list: bool) -> str:
        normalized = (provider or "").strip().lower()
        if normalized in {"static", "self_hosted", "brightdata", "oxylabs"}:
            return normalized
        return "static" if has_static_list else "none"

    @staticmethod
    def _redact_proxy(proxy_url: str) -> str:
        parsed = urlsplit(proxy_url if "://" in proxy_url else f"http://{proxy_url}")
        if "@" not in parsed.netloc:
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))
        auth, host = parsed.netloc.rsplit("@", 1)
        username = auth.split(":", 1)[0] if auth else "***"
        redacted_auth = f"{username}:***" if username else "***"
        return urlunsplit((parsed.scheme, f"{redacted_auth}@{host}", parsed.path, parsed.query, parsed.fragment))

    @staticmethod
    def _redact_endpoint(endpoint: str | None) -> str | None:
        if not endpoint:
            return None
        parsed = urlsplit(endpoint if "://" in endpoint else f"http://{endpoint}")
        netloc = parsed.netloc or parsed.path
        path = parsed.path if parsed.netloc else ""
        return urlunsplit((parsed.scheme or "http", netloc, path, "", ""))

    def _build_managed_proxy_url(self) -> str | None:
        endpoint = (self.settings.proxy_endpoint or "").strip()
        username = (self.settings.proxy_username or "").strip()
        password = self.settings.proxy_password or ""
        if not endpoint or not username or not password:
            return None
        parsed = urlsplit(endpoint if "://" in endpoint else f"http://{endpoint}")
        netloc = parsed.netloc or parsed.path
        path = parsed.path if parsed.netloc else ""
        if not netloc:
            return None
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}"
        return urlunsplit((parsed.scheme or "http", f"{auth}@{netloc}", path, "", ""))

    def resolve_proxy_urls(self) -> list[str]:
        static_proxies = self._split_proxy_entries(self.settings.proxy_list)
        provider = self._normalize_provider(self.settings.proxy_provider, has_static_list=bool(static_proxies))
        if provider in {"static", "self_hosted"}:
            return static_proxies
        if provider in {"brightdata", "oxylabs"}:
            managed_proxy = self._build_managed_proxy_url()
            return [managed_proxy] if managed_proxy else []
        return []

    def resolve_proxy_pool(self) -> list[str]:
        configured_proxies = self.resolve_proxy_urls()
        return configured_proxies or list(DEFAULT_FALLBACK_PROXIES)

    def _probe_proxy_url(self, proxy_url: str) -> dict[str, Any]:
        redacted_proxy = self._redact_proxy(proxy_url)
        try:
            with httpx.Client(
                proxy=proxy_url,
                timeout=self.settings.proxy_probe_timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = client.get(self.settings.proxy_probe_url)
            payload: dict[str, Any] | None = None
            try:
                payload = response.json()
            except ValueError:
                payload = None
            remote_ip = None
            if isinstance(payload, dict):
                remote_ip = payload.get("origin") or payload.get("ip")
            proxy_identity = payload.get("proxy_node") if isinstance(payload, dict) else None
            return {
                "proxy": redacted_proxy,
                "ready": response.status_code < 400,
                "http_status": response.status_code,
                "remote_ip": remote_ip,
                "proxy_identity": proxy_identity,
            }
        except Exception as exc:  # pragma: no cover - exercised via monkeypatch in tests
            return {
                "proxy": redacted_proxy,
                "ready": False,
                "error": str(exc),
            }

    def build_status(self, *, include_probe: bool = False) -> dict[str, Any]:
        configured_proxies = self.resolve_proxy_urls()
        provider = self._normalize_provider(self.settings.proxy_provider, has_static_list=bool(configured_proxies))
        uses_managed_provider = provider in {"brightdata", "oxylabs"}
        self_hosted_provider = provider == "self_hosted"
        credential_ready = bool(configured_proxies)
        configuration_ready = provider != "none" and credential_ready
        proxy_pool_source = "configured-provider" if configured_proxies else "local-fallback"

        probe_results: list[dict[str, Any]] = []
        if include_probe and configured_proxies:
            probe_results = [self._probe_proxy_url(proxy_url) for proxy_url in configured_proxies[:3]]
        probe_success_count = sum(1 for result in probe_results if result.get("ready"))
        probe_ready = probe_success_count > 0

        blocking_reason: str | None = None
        if not configuration_ready:
            blocking_reason = "未配置 COLLECTION_API_PROXY_LIST 或代理 provider 凭证。"
        elif include_probe and not probe_ready:
            blocking_reason = "代理配置已存在，但实机探测未通过。"
        elif not include_probe:
            blocking_reason = "代理配置已存在，待执行实机探测。"

        return {
            "provider": provider,
            "supported_providers": list(self.SUPPORTED_PROVIDERS),
            "status": "ready" if probe_ready else "in_progress",
            "configuration_ready": configuration_ready,
            "credential_ready": credential_ready,
            "uses_managed_provider": uses_managed_provider,
            "self_hosted_provider": self_hosted_provider,
            "proxy_pool_source": proxy_pool_source,
            "configured_proxy_count": len(configured_proxies),
            "resolved_pool_proxy_count": len(self.resolve_proxy_pool()),
            "configured_proxy_examples": [self._redact_proxy(proxy_url) for proxy_url in configured_proxies[:2]],
            "provider_endpoint": self._redact_endpoint(self.settings.proxy_endpoint),
            "zone": self.settings.proxy_zone,
            "country": self.settings.proxy_country,
            "probe": {
                "performed": include_probe,
                "ready": probe_ready,
                "success_count": probe_success_count,
                "attempted_count": len(probe_results),
                "probe_url": self.settings.proxy_probe_url,
                "results": probe_results,
            },
            "blocking_reason": None if probe_ready else blocking_reason,
            "recommended_env": [
                "COLLECTION_API_PROXY_PROVIDER",
                "COLLECTION_API_PROXY_LIST",
                "COLLECTION_API_PROXY_ENDPOINT",
                "COLLECTION_API_PROXY_USERNAME",
                "COLLECTION_API_PROXY_PASSWORD",
            ],
            "generated_at": datetime.now(UTC).isoformat(),
        }
