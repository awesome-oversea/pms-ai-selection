from __future__ import annotations

from fastapi.testclient import TestClient
from src.apps.agent_service import app
from src.config.settings import get_settings


def test_agent_service_status_exposes_dify_runtime(monkeypatch):
    monkeypatch.setenv("DIFY_ENABLED", "true")
    monkeypatch.setenv("DIFY_BASE_URL", "http://localhost:58080")
    monkeypatch.setenv("DIFY_API_KEY", "local-dify-token")
    get_settings.cache_clear()

    try:
        with TestClient(app) as client:
            health = client.get("/health")
            assert health.status_code == 200
            assert health.json()["service"] == "agent-service"

            status = client.get("/status")
            assert status.status_code == 200
            data = status.json()
            assert data["service"] == "agent-service"
            assert data["deployment"] == "k8s/agent-service.yml"
            assert "dify-compatible" in data["supported_frameworks"]
            assert data["dify"]["runtime_status"] == "active"
            assert data["dify"]["workflow_endpoint"].endswith("/v1/workflows/run")
    finally:
        get_settings.cache_clear()
