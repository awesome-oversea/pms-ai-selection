from __future__ import annotations

import asyncio
from pathlib import Path

from src.services import local_external_collection_readiness_service as readiness_module
from src.services.local_external_collection_readiness_service import LocalExternalCollectionReadinessService


def test_classify_probe_distinguishes_api_real_and_web_fallback():
    assert (
        LocalExternalCollectionReadinessService._classify_probe(
            "amazon",
            {"mode": "real", "degraded": False},
            credential_ready=True,
        )
        == "preferred_api_real"
    )
    assert (
        LocalExternalCollectionReadinessService._classify_probe(
            "amazon",
            {"mode": "real", "degraded": False},
            credential_ready=False,
        )
        == "web_signal_fallback"
    )
    assert (
        LocalExternalCollectionReadinessService._classify_probe(
            "google_trends",
            {"mode": "real", "real_signal": {"source": "google_trends"}},
            credential_ready=True,
        )
        == "web_signal_fallback"
    )
    assert (
        LocalExternalCollectionReadinessService._classify_probe(
            "tiktok",
            {
                "mode": "real",
                "degraded": True,
                "signal_context": {"provider": "external_signal_service", "source_channel": "public_web_signal"},
            },
            credential_ready=True,
        )
        == "web_signal_fallback"
    )


def test_run_writes_readiness_artifacts(tmp_path, monkeypatch):
    calls: dict[str, bool] = {"closed": False}

    class FakeAgent:
        def __init__(self, config: dict[str, object]) -> None:
            self.config = config

        async def call_tool(self, tool_name: str, **kwargs):
            if kwargs.get("mode") == "mock":
                return {
                    "source": tool_name,
                    "mode": "mock",
                    "degraded": True,
                    "degradation_reason": "mock degraded scenario",
                }
            if tool_name == "amazon_bsr":
                return {
                    "source": "amazon_bsr",
                    "mode": "real",
                    "total_results": 1,
                    "signal_context": {"provider": "external_signal_service", "source_name": "amazon", "source_channel": "public_web_signal"},
                    "signal_readiness": {"local_business_ready": True, "enterprise_ready": False, "readiness_tier": "local_business_ready"},
                }
            if tool_name == "tiktok_products":
                return {
                    "source": "tiktok_products",
                    "mode": "real",
                    "total_results": 1,
                    "signal_context": {"provider": "external_signal_service", "source_name": "tiktok", "source_channel": "public_web_signal"},
                    "signal_readiness": {"local_business_ready": True, "enterprise_ready": False, "readiness_tier": "local_business_ready"},
                }
            if tool_name == "google_trends":
                return {"source": "google_trends", "mode": "real", "trend_data": {}, "collected_at": "2026-04-21T00:00:00+00:00"}
            if tool_name == "ali1688_supply":
                return {
                    "source": "ali1688",
                    "mode": "real",
                    "total_suppliers": 1,
                    "signal_context": {"provider": "external_signal_service", "source_name": "ali1688", "source_channel": "public_web_signal"},
                    "signal_readiness": {"local_business_ready": True, "enterprise_ready": False, "readiness_tier": "local_business_ready"},
                }
            raise AssertionError(tool_name)

    class FakeSignalService:
        def __init__(self, timeout_seconds: float = 8.0) -> None:
            self.timeout_seconds = timeout_seconds

        async def collect_gdelt_event_signals(self, *, query: str, mode: str = "auto"):
            return {
                "source": "media_news",
                "mode": "real",
                "ready": True,
                "degradation": {"degraded": False, "live_endpoint_ready": True},
            }

    monkeypatch.setattr(readiness_module, "DataCollectionAgent", FakeAgent)
    monkeypatch.setattr(readiness_module, "ExternalSignalService", FakeSignalService)

    async def fake_close_kafka() -> None:
        calls["closed"] = True

    monkeypatch.setattr(readiness_module, "close_kafka", fake_close_kafka)
    monkeypatch.setattr(
        readiness_module.LocalExternalCollectionReadinessService,
        "_build_source_config",
        staticmethod(
            lambda: {
                "amazon": {"credential_ready": False, "endpoint": "https://amazon.example", "preferred_channel": "amazon_sp_api"},
                "tiktok": {"credential_ready": False, "endpoint": "https://tiktok.example", "preferred_channel": "tiktok_business_api"},
                "google_trends": {"credential_ready": True, "endpoint": "https://trends.example", "preferred_channel": "google_trends_endpoint"},
                "ali1688": {"credential_ready": False, "endpoint": "https://1688.example", "preferred_channel": "ali1688_open_api"},
                "gdelt": {"credential_ready": True, "endpoint": "https://gdelt.example", "preferred_channel": "gdelt_http"},
                "http_retry": {"max_attempts": 3, "base_backoff_seconds": 0.5, "max_backoff_seconds": 3.0, "proxy_provider": "none"},
            }
        ),
    )

    service = LocalExternalCollectionReadinessService(root=tmp_path)
    summary = service.run(output_root=tmp_path / "artifacts" / "local_external_collection_readiness")

    latest_path = tmp_path / "artifacts" / "ops" / "local_external_collection_readiness_latest.json"

    assert summary["accepted"] is True
    assert summary["gdelt_probe"]["real_ready"] is True
    assert summary["business_readiness_overview"]["local_validation_only_sources"] == ["ali1688", "amazon", "tiktok"]
    assert summary["business_readiness_overview"]["formal_api_ready_count"] == 1
    assert summary["readiness_snapshot"]["local_validation_only_count"] == 3
    assert summary["source_probes"]["amazon"]["signal_readiness"]["local_business_ready"] is True
    assert summary["source_probes"]["amazon"]["formal_api_ready"] is False
    assert summary["source_probes"]["amazon"]["fallback_reason"] == "public_web_signal"
    assert summary["source_probes"]["google_trends"]["formal_api_ready"] is True
    assert Path(summary["artifacts"]["config_matrix"]).exists()
    assert Path(summary["artifacts"]["source_probes"]).exists()
    assert Path(summary["artifacts"]["business_readiness_overview"]).exists()
    assert latest_path.exists()
    assert calls["closed"] is True


def test_format_exception_uses_repr_for_empty_message():
    assert LocalExternalCollectionReadinessService._format_exception(TimeoutError()) == "TimeoutError()"


def test_run_converts_probe_timeout_to_structured_error(tmp_path, monkeypatch):
    calls: dict[str, bool] = {"closed": False}

    class SlowAgent:
        def __init__(self, config: dict[str, object]) -> None:
            self.config = config

        async def call_tool(self, tool_name: str, **kwargs):
            if kwargs.get("mode") == "mock":
                return {
                    "source": tool_name,
                    "mode": "mock",
                    "degraded": True,
                    "degradation_reason": "mock degraded scenario",
                }
            if tool_name == "google_trends":
                await asyncio.sleep(0.05)
            return {
                "source": tool_name,
                "mode": "real",
                "total_results": 1,
                "signal_context": {"provider": "external_signal_service", "source_name": tool_name, "source_channel": "public_web_signal"},
                "signal_readiness": {
                    "local_business_ready": True,
                    "enterprise_ready": False,
                    "readiness_tier": "local_business_ready",
                },
            }

    class FakeSignalService:
        def __init__(self, timeout_seconds: float = 8.0) -> None:
            self.timeout_seconds = timeout_seconds

        async def collect_gdelt_event_signals(self, *, query: str, mode: str = "auto"):
            return {
                "source": "media_news",
                "mode": "real",
                "ready": True,
                "degradation": {"degraded": False, "live_endpoint_ready": True},
            }

    async def fake_close_kafka() -> None:
        calls["closed"] = True

    monkeypatch.setattr(readiness_module, "DataCollectionAgent", SlowAgent)
    monkeypatch.setattr(readiness_module, "ExternalSignalService", FakeSignalService)
    monkeypatch.setattr(readiness_module, "close_kafka", fake_close_kafka)
    monkeypatch.setattr(LocalExternalCollectionReadinessService, "COLLECTION_PROBE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        readiness_module.LocalExternalCollectionReadinessService,
        "_build_source_config",
        staticmethod(
            lambda: {
                "amazon": {"credential_ready": False, "endpoint": "https://amazon.example", "preferred_channel": "amazon_sp_api"},
                "tiktok": {"credential_ready": False, "endpoint": "https://tiktok.example", "preferred_channel": "tiktok_business_api"},
                "google_trends": {"credential_ready": True, "endpoint": "https://trends.example", "preferred_channel": "google_trends_endpoint"},
                "ali1688": {"credential_ready": False, "endpoint": "https://1688.example", "preferred_channel": "ali1688_open_api"},
                "gdelt": {"credential_ready": True, "endpoint": "https://gdelt.example", "preferred_channel": "gdelt_http"},
                "http_retry": {"max_attempts": 3, "base_backoff_seconds": 0.5, "max_backoff_seconds": 3.0, "proxy_provider": "none"},
            }
        ),
    )

    service = LocalExternalCollectionReadinessService(root=tmp_path)
    summary = service.run(output_root=tmp_path / "artifacts" / "local_external_collection_readiness")

    assert summary["accepted"] is True
    assert summary["source_probes"]["google_trends"]["status"] == "error"
    assert summary["source_probes"]["google_trends"]["formal_api_ready"] is False
    assert summary["source_probes"]["google_trends"]["fallback_reason"] == "probe_error"
    assert "timed out" in summary["source_probes"]["google_trends"]["error"]
    assert Path(summary["artifacts"]["summary"]).exists()
    assert Path(summary["artifacts"]["source_probes"]).exists()
    assert calls["closed"] is True
