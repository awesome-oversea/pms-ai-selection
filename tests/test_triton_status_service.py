from __future__ import annotations

from src.services.triton_status_service import TritonStatusService


def test_triton_status_service_build_status(monkeypatch):
    class _LLM:
        triton_enabled = True
        triton_endpoint = "http://triton-rerank:8000"
        triton_timeout_seconds = 8.0
        rerank_model = "bge-reranker-base"

    class _Settings:
        llm = _LLM()

    monkeypatch.setattr("src.services.triton_status_service.get_settings", lambda: _Settings())
    monkeypatch.setattr(
        TritonStatusService,
        "_run_script_json",
        lambda self, path: {
            "environment_connected": False,
            "healthcheck_ok": False,
            "rerank_ok": False,
            "blocking_reason": "triton_endpoint_unreachable",
            "detected_mode": None,
            "local_compatible": False,
        },
    )
    data = TritonStatusService().build_status()
    assert data["enabled"] is True
    assert data["endpoint"] == "http://triton-rerank:8000"
    assert data["deployment"]["rerank_manifest"] == "k8s/triton-rerank.yml"
    assert data["fallback"] == "local-or-mock-rerank"
    assert data["runtime_probe"]["blocking_reason"] == "triton_endpoint_unreachable"
    assert data["route_status"]["environment_connected"] is False
    assert data["route_status"]["rerank_ready"] is False
    assert data["route_status"]["local_compatible"] is False
    assert data["validation"]["script"] == "scripts/triton_smoke_check.py"
    assert data["validation"]["status"] == "blocked"
    assert data["deploy_ready"] is False


def test_triton_status_service_marks_local_compatible_ready(monkeypatch):
    class _LLM:
        triton_enabled = True
        triton_endpoint = "http://127.0.0.1:8000"
        triton_timeout_seconds = 8.0
        rerank_model = "bge-reranker-base"

    class _Settings:
        llm = _LLM()

    monkeypatch.setattr("src.services.triton_status_service.get_settings", lambda: _Settings())
    monkeypatch.setattr(
        TritonStatusService,
        "_run_script_json",
        lambda self, path: {
            "environment_connected": True,
            "healthcheck_ok": True,
            "rerank_ok": True,
            "blocking_reason": None,
            "detected_mode": "local-compatible",
            "local_compatible": True,
        },
    )
    data = TritonStatusService().build_status()
    assert data["route_status"]["mode"] == "local-compatible"
    assert data["route_status"]["local_compatible"] is True
    assert data["validation"]["status"] == "ready"
    assert data["deploy_ready"] is True
