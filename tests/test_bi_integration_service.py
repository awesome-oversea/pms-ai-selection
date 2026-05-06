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
        return _Resp({"status": "ok"})

    async def post(self, url, headers=None, json=None):
        return _Resp({"ok": True})


@pytest.mark.asyncio
async def test_bi_integration_service_connection_and_outbound(monkeypatch):
    monkeypatch.setattr("src.infrastructure.bi_client.httpx.AsyncClient", _Client)

    fake_config = SimpleNamespace(
        id="cfg-bi-001",
        name="default",
        system_type=SimpleNamespace(value="bi"),
        api_endpoint="http://fake-bi.local",
        api_key="demo-key",
        extra_config={"health_path": "/health", "dataset_path": "/datasets/push", "timeout_seconds": 5},
        last_sync_at=None,
    )
    logs: list[SimpleNamespace] = []
    products = [
        SimpleNamespace(
            id="prod-001",
            name="蓝牙耳机",
            brand="BrandA",
            platform="oms",
            external_product_id="oms-001",
            asin=None,
            price=99.0,
            rating=4.5,
            review_count=10,
            sales_rank=1,
            attributes={},
        )
    ]
    selection_tasks = [
        SimpleNamespace(
            id="task-001",
            title="蓝牙耳机",
            status=SimpleNamespace(value="completed"),
            target_category="electronics",
            target_market="US",
            completed_at=None,
            config={
                "execution_result": {
                    "decision_output": {
                        "decision": {"decision": "GO"},
                        "pricing": {"recommended_price": 39.99},
                        "profitability": {"roi_year1_percent": 42.0, "payback_period_months": 11.5, "expected_margin": 28.5},
                        "risks": [{"category": "market", "name": "价格竞争"}],
                        "recommendation_reasons": ["趋势向上", "利润良好"]
                    }
                }
            },
        )
    ]

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

    async def _list_products_for_export(limit=100):
        return products[:limit]

    async def _list_sync_logs(system_type, limit=20):
        return [(log, fake_config) for log in logs[:limit]]

    async def _list_tasks(status=None, limit=100, offset=0, cursor=None, tenant_id=None):
        return selection_tasks[:limit], len(selection_tasks)

    async def _get_task(task_id, tenant_id=None):
        for item in selection_tasks:
            if str(item.id) == str(task_id):
                return item
        return None

    service = ErpIntegrationService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    service.repo = SimpleNamespace(
        get_config=_get_config,
        create_sync_log=_create_sync_log,
        update_sync_log=_update_sync_log,
        list_products_for_export=_list_products_for_export,
        list_sync_logs=_list_sync_logs,
        create_or_update_config=None,
    )
    service.selection_repo = SimpleNamespace(list_tasks=_list_tasks, get_task=_get_task)

    connection = await service.test_bi_connection(name="default")
    assert connection["status"] == "ok"
    assert connection["system_type"] == "bi"

    outbound = await service.sync_outbound_bi_assets(name="default")
    assert outbound["status"] == "completed"
    assert outbound["datasets"] == ["selection_tasks_snapshot", "data_sync_events_snapshot", "selection_task_metrics"]

    metrics = await service.get_bi_task_metrics("task-001")
    assert metrics is not None
    assert metrics["recommended_price"] == 39.99
    assert metrics["roi_year1_percent"] == 42.0

    listed = await service.list_bi_logs(limit=10)
    assert listed["total"] >= 1
