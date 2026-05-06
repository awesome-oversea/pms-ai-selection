from __future__ import annotations

from types import SimpleNamespace

import pytest
from src.services.erp_integration_service import ErpIntegrationService


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
    def __init__(self, timeout=10):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None):
        return _Resp({"status": "running", "run_id": "log-1", "result": {"step": "approval"}})

    async def post(self, url, headers=None, json=None):
        return _Resp({"accepted": True, "run_id": "log-1", "status": "dispatched"})


@pytest.mark.asyncio
async def test_paas_integration_service_connection_trigger_callback_and_logs(monkeypatch):
    monkeypatch.setattr("src.infrastructure.paas_client.httpx.AsyncClient", _Client)

    fake_config = SimpleNamespace(
        id="cfg-paas-001",
        name="default",
        system_type=SimpleNamespace(value="paas"),
        api_endpoint="http://fake-paas.local",
        api_key="demo-key",
        extra_config={
            "health_path": "/health",
            "trigger_path": "/workflows/trigger",
            "status_path": "/workflows/{run_id}",
            "callback_token": "cb-token",
            "timeout_seconds": 5,
            "workflow_key": "selection_workflow",
            "callback_url": "http://callback.local",
        },
        last_sync_at=None,
        is_active=True,
    )
    logs: list[SimpleNamespace] = []

    async def _get_config(system_type, name="default"):
        return fake_config

    async def _create_sync_log(config_id: str, sync_type: str, entity_type: str):
        log = SimpleNamespace(
            id=f"log-{len(logs)+1}",
            sync_type=sync_type,
            entity_type=entity_type,
            status="running",
            items_total=0,
            items_success=0,
            items_failed=0,
            error_detail=None,
            started_at=None,
            finished_at=None,
            duration_seconds=None,
        )
        logs.append(log)
        return log

    async def _update_sync_log(log_id: str, **fields):
        for log in logs:
            if str(log.id) == str(log_id):
                for k, v in fields.items():
                    setattr(log, k, v)
                return log
        raise ValueError(log_id)

    async def _get_sync_log_with_config(log_id: str):
        for log in logs:
            if str(log.id) == str(log_id):
                return log, fake_config
        return None, None

    async def _list_sync_logs(system_type, limit=20):
        return [(log, fake_config) for log in logs[:limit]]

    service = ErpIntegrationService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    service.repo = SimpleNamespace(
        get_config=_get_config,
        create_sync_log=_create_sync_log,
        update_sync_log=_update_sync_log,
        get_sync_log_with_config=_get_sync_log_with_config,
        list_sync_logs=_list_sync_logs,
        create_or_update_config=None,
    )

    connection = await service.test_paas_connection(name="default")
    assert connection["status"] == "ok"
    assert connection["next_action"] == "trigger_workflow"

    triggered = await service.trigger_paas_workflow(
        name="default",
        workflow_key="selection_workflow",
        trigger_payload={"task_id": "task-001"},
        callback_url="http://callback.local",
    )
    assert triggered["status"] == "dispatched"
    assert triggered["workflow_key"] == "selection_workflow"
    assert triggered["callback_registered"] is True
    assert triggered["callback_token_required"] is True

    callback = await service.update_paas_callback(run_id="log-1", status="completed", result={"approved": True})
    assert callback["callback_received"] is True
    assert callback["callback_verified"] is True
    assert callback["result"]["approved"] is True

    status = await service.get_paas_run_status(name="default", run_id="log-1")
    assert status["system_type"] == "paas"
    assert status["status"] == "running"
    assert status["retry_recommended"] is True

    logs_result = await service.list_paas_logs(limit=10)
    assert logs_result["total"] >= 1
