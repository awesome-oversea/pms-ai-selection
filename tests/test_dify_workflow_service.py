from __future__ import annotations

import json

import httpx
import pytest
from src.config.settings import get_settings
from src.services.dify_workflow_service import DifyWorkflowError, DifyWorkflowService


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_dify_workflow_service_reports_compatible_only_runtime(monkeypatch):
    for key in (
        "DIFY_ENABLED",
        "DIFY_BASE_URL",
        "DIFY_API_KEY",
        "DIFY_WORKFLOW_RUN_PATH",
        "DIFY_TIMEOUT_SECONDS",
        "DIFY_RESPONSE_MODE",
        "DIFY_USER_PREFIX",
        "DIFY_PREFER_COMPATIBLE_FALLBACK",
    ):
        monkeypatch.delenv(key, raising=False)

    service = DifyWorkflowService()
    runtime = service.build_runtime_status()

    assert runtime["enabled"] is False
    assert runtime["runtime_status"] == "compatible-only"
    assert runtime["real_runtime_ready"] is False
    assert runtime["blocked_reason"] is None


@pytest.mark.asyncio
async def test_dify_workflow_service_invokes_http_runtime(monkeypatch):
    monkeypatch.setenv("DIFY_ENABLED", "true")
    monkeypatch.setenv("DIFY_BASE_URL", "http://dify.local")
    monkeypatch.setenv("DIFY_API_KEY", "app-local-token")
    monkeypatch.setenv("DIFY_RESPONSE_MODE", "blocking")

    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "data": {
                    "workflow_run_id": "wf-123",
                    "task_id": "task-456",
                    "status": "succeeded",
                    "elapsed_time": 0.42,
                    "outputs": {
                        "answer": "已输出蓝牙耳机市场机会摘要",
                        "score": "high",
                    },
                }
            },
        )

    service = DifyWorkflowService(transport=httpx.MockTransport(_handler))
    result = await service.invoke_workflow(
        input_data={
            "query": "输出蓝牙耳机市场机会摘要",
            "category": "electronics",
            "target_market": "US",
            "request_user": "tester",
        }
    )

    assert captured["path"] == "/v1/workflows/run"
    assert captured["authorization"] == "Bearer app-local-token"
    assert captured["payload"] == {
        "inputs": {
            "query": "输出蓝牙耳机市场机会摘要",
            "category": "electronics",
            "target_market": "US",
            "request_user": "tester",
        },
        "response_mode": "blocking",
        "user": "pms:tester",
    }
    assert result["framework"] == "dify-compatible"
    assert result["runtime_channel"] == "dify-http"
    assert result["routing"]["channel"] == "dify-http"
    assert result["provider_response"]["workflow_run_id"] == "wf-123"
    assert result["dify_runtime"]["runtime_status"] == "active"
    assert result["business_summary"]["next_action"]


@pytest.mark.asyncio
async def test_dify_workflow_service_raises_when_runtime_not_configured(monkeypatch):
    monkeypatch.setenv("DIFY_ENABLED", "true")
    monkeypatch.setenv("DIFY_BASE_URL", "http://dify.local")
    monkeypatch.delenv("DIFY_API_KEY", raising=False)

    service = DifyWorkflowService()

    with pytest.raises(DifyWorkflowError):
        await service.invoke_workflow(input_data={"query": "输出市场机会摘要", "category": "electronics"})
