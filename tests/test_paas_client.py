from __future__ import annotations

import pytest
from src.infrastructure.paas_client import PaaSClient


class _Resp:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {"ok": True}
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _Client:
    last_request = None

    def __init__(self, timeout=10):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None):
        _Client.last_request = {"method": "GET", "url": url, "headers": headers or {}}
        return _Resp({"status": "running", "run_id": "run-001", "result": {"step": "approval"}})

    async def post(self, url, headers=None, json=None):
        _Client.last_request = {"method": "POST", "url": url, "headers": headers or {}, "json": json or {}}
        return _Resp({"accepted": True, "run_id": "run-001", "status": "dispatched"})


@pytest.mark.asyncio
async def test_paas_client_connection_trigger_and_status(monkeypatch):
    monkeypatch.setattr("src.infrastructure.paas_client.httpx.AsyncClient", _Client)
    client = PaaSClient(
        api_endpoint="http://fake-paas.local",
        api_key="demo-key",
        health_path="/health",
        trigger_path="/workflows/trigger",
        status_path="/workflows/{run_id}",
        timeout_seconds=5,
    )
    tested = await client.test_connection()
    triggered = await client.trigger_workflow(
        workflow_key="selection_workflow",
        payload={"task_id": "task-001"},
        callback={"url": "http://callback.local", "token": "cb-token"},
        callback_context={"internal_run_id": "log-001"},
    )
    status = await client.get_workflow_status("run-001")
    assert tested["status"] == "ok"
    assert triggered["run_id"] == "run-001"
    assert status["status"] == "running"
    assert _Client.last_request["url"].endswith("/workflows/run-001")
