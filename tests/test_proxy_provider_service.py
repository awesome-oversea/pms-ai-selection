from __future__ import annotations

from src.config.settings import CollectionAPISettings
from src.services.proxy_provider_service import ProxyProviderService


def test_proxy_provider_service_reads_static_proxy_list():
    settings = CollectionAPISettings(
        proxy_provider="static",
        proxy_list="http://user:secret@127.0.0.1:8080, http://127.0.0.1:8888",
    )

    service = ProxyProviderService(settings=settings)
    status = service.build_status()

    assert status["provider"] == "static"
    assert status["configuration_ready"] is True
    assert status["configured_proxy_count"] == 2
    assert status["proxy_pool_source"] == "configured-provider"
    assert status["configured_proxy_examples"][0] == "http://user:***@127.0.0.1:8080"


def test_proxy_provider_service_builds_managed_provider_proxy():
    settings = CollectionAPISettings(
        proxy_provider="brightdata",
        proxy_endpoint="brd.superproxy.io:33335",
        proxy_username="brd-customer-demo-zone-zone1",
        proxy_password="secret",
        proxy_zone="zone1",
    )

    service = ProxyProviderService(settings=settings)
    resolved = service.resolve_proxy_urls()
    status = service.build_status()

    assert len(resolved) == 1
    assert resolved[0].startswith("http://brd-customer-demo-zone-zone1:")
    assert status["uses_managed_provider"] is True
    assert status["configuration_ready"] is True
    assert status["provider_endpoint"] == "http://brd.superproxy.io:33335"


def test_proxy_provider_service_supports_self_hosted_provider():
    settings = CollectionAPISettings(
        proxy_provider="self_hosted",
        proxy_list="http://127.0.0.1:18080,http://127.0.0.1:18081",
    )

    service = ProxyProviderService(settings=settings)
    status = service.build_status()

    assert status["provider"] == "self_hosted"
    assert status["self_hosted_provider"] is True
    assert status["configuration_ready"] is True
    assert status["configured_proxy_count"] == 2


def test_proxy_provider_service_reports_probe_success():
    settings = CollectionAPISettings(
        proxy_provider="static",
        proxy_list="http://127.0.0.1:8080",
    )
    service = ProxyProviderService(settings=settings)
    service._probe_proxy_url = lambda proxy_url: {  # type: ignore[method-assign]
        "proxy": proxy_url,
        "ready": True,
        "http_status": 200,
        "remote_ip": "127.0.0.1",
    }

    status = service.build_status(include_probe=True)

    assert status["status"] == "ready"
    assert status["probe"]["performed"] is True
    assert status["probe"]["success_count"] == 1
    assert status["blocking_reason"] is None
