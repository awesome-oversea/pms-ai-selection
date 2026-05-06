from __future__ import annotations

from scripts.bootstrap_local_gdelt_signal import _build_acceptance_payload
from src.services.local_external_collection_readiness_service import (
    LocalExternalCollectionReadinessService,
)


def test_gdelt_acceptance_uses_auto_real_success_after_live_timeout():
    live_result = {
        "mode": "error",
        "total_count": 0,
        "degradation": {"degraded": True, "businessization_ready": True},
        "upstream_error": {"error_code": "timeout", "attempts": 3},
    }
    auto_result = {
        "mode": "real",
        "total_count": 5,
        "degradation": {"degraded": False, "businessization_ready": True},
    }

    payload = _build_acceptance_payload(
        query="bluetooth speaker",
        live_result=live_result,
        auto_result=auto_result,
    )

    assert payload["accepted"] is True
    assert payload["live_endpoint_ready"] is True
    assert payload["real_result_source"] == "auto"
    assert payload["real_article_count"] == 5
    assert payload["degradation_evidence_ready"] is True
    assert payload["first_attempt"]["upstream_error"]["error_code"] == "timeout"


def test_gdelt_acceptance_fails_when_only_fallback_is_available():
    live_result = {
        "mode": "error",
        "total_count": 0,
        "degradation": {"degraded": True, "businessization_ready": True},
    }
    auto_result = {
        "mode": "mock",
        "total_count": 2,
        "degradation": {"degraded": True, "businessization_ready": True},
    }

    payload = _build_acceptance_payload(
        query="bluetooth speaker",
        live_result=live_result,
        auto_result=auto_result,
    )

    assert payload["accepted"] is False
    assert payload["live_endpoint_ready"] is False
    assert payload["real_result_source"] is None
    assert payload["real_article_count"] == 0


def test_external_collection_readiness_accepts_auto_real_gdelt_result():
    service = LocalExternalCollectionReadinessService()
    source, result = service._select_gdelt_real_result(
        {
            "real_result": {
                "mode": "error",
                "ready": False,
                "degradation": {"degraded": True, "businessization_ready": False},
            },
            "auto_result": {
                "mode": "real",
                "ready": True,
                "total_count": 5,
                "degradation": {"degraded": False, "businessization_ready": True},
            },
        }
    )

    assert source == "auto"
    assert result["total_count"] == 5
