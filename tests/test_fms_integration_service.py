from __future__ import annotations

from types import SimpleNamespace

import pytest
from src.services.erp_integration_service import ErpIntegrationService


class _Resp:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {"items": []}
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
        return _Resp({"items": [{"id": "fms-001", "product_id": "prod-001", "gross_profit": 99.0, "cost": 20.0, "margin_rate": 0.28}]})

    async def post(self, url, headers=None, json=None):
        return _Resp({"ok": True})


@pytest.mark.asyncio
async def test_fms_integration_service_test_connection_and_sync(monkeypatch):
    monkeypatch.setattr("src.infrastructure.fms_client.httpx.AsyncClient", _Client)

    fake_config = SimpleNamespace(
        id="cfg-fms-001",
        name="default",
        system_type=SimpleNamespace(value="fms"),
        api_endpoint="http://fake-fms.local",
        api_key="demo-key",
        extra_config={"inbound_path": "/finance-metrics", "outbound_path": "/profit-plans/bulk-upsert", "timeout_seconds": 5},
        last_sync_at=None,
    )
    logs: list[SimpleNamespace] = []
    products = [SimpleNamespace(id="prod-001", name="蓝牙耳机", brand="BrandA", platform="oms", external_product_id="oms-001", asin=None, price=99.0, rating=0.28, review_count=10, sales_rank=1)]

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

    async def _upsert_product_by_external_id(data):
        return SimpleNamespace(id=data["external_product_id"]), True

    async def _list_products_for_export(limit=100):
        return products[:limit]

    async def _list_sync_logs(system_type, limit=20):
        return [(log, fake_config) for log in logs[:limit]]

    service = ErpIntegrationService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    service.repo = SimpleNamespace(
        get_config=_get_config,
        create_sync_log=_create_sync_log,
        update_sync_log=_update_sync_log,
        upsert_product_by_external_id=_upsert_product_by_external_id,
        list_products_for_export=_list_products_for_export,
        list_sync_logs=_list_sync_logs,
    )

    connection = await service.test_fms_connection(name="default")
    assert connection["status"] == "ok"
    assert connection["system_type"] == "fms"

    inbound = await service.sync_inbound_finance_metrics(name="default")
    assert inbound["status"] in {"completed", "partial_success"}

    outbound = await service.sync_outbound_profit_plan(name="default", limit=10)
    assert outbound["status"] == "completed"

    listed = await service.list_fms_logs(limit=10)
    assert listed["total"] >= 2
