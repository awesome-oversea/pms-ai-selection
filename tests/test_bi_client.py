from __future__ import annotations

import pytest
from src.infrastructure.bi_client import BIClient


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
        if url.endswith("/health"):
            return _Resp({"status": "ok"})
        return _Resp(
            {
                "datasets": [
                    {
                        "dataset_name": "selection_daily_kpis",
                        "rows": [
                            {
                                "kpi_date": "2026-04-14",
                                "tenant_id": "tenant-a",
                                "org_id": "org-1",
                                "department_id": "dep-1",
                                "store_id": "store-us",
                                "marketplace": "US",
                                "channel": "amazon",
                                "warehouse_id": "wh-1",
                                "supplier_id": "sup-1",
                                "category_id": "cat-1",
                                "data_level": "internal",
                            },
                            {"kpi_date": "2026-04-15", "tenant_id": "tenant-b", "store_id": "store-eu", "marketplace": "EU"},
                        ],
                    }
                ]
            }
        )

    async def post(self, url, headers=None, json=None):
        _Client.last_request = {"method": "POST", "url": url, "headers": headers or {}, "json": json or {}}
        return _Resp({"ok": True})


@pytest.mark.asyncio
async def test_bi_client_connection_push_and_read(monkeypatch):
    monkeypatch.setattr("src.infrastructure.bi_client.httpx.AsyncClient", _Client)
    client = BIClient(
        api_endpoint="http://fake-bi.local",
        api_key="demo-key",
        health_path="/health",
        dataset_path="/datasets/push",
        timeout_seconds=5,
    )
    connection = await client.test_connection()
    assert connection["status"] == "ok"
    await client.push_dataset({"datasets": [{"dataset_name": "selection_tasks_snapshot", "rows": []}]})
    assert _Client.last_request["method"] == "POST"
    assert _Client.last_request["headers"]["X-API-Key"] == "demo-key"

    dataset = await client.read_dataset(
        permission_context={
            "tenant_id": "tenant-a",
            "org_id": "org-1",
            "department_id": "dep-1",
            "store_id": "store-us",
            "marketplace": "US",
            "channel": "amazon",
            "warehouse_id": "wh-1",
            "supplier_id": "sup-1",
            "category_id": "cat-1",
            "data_level": "internal",
        }
    )
    assert dataset["datasets"][0]["dataset_name"] == "selection_daily_kpis"
    assert [row["kpi_date"] for row in dataset["datasets"][0]["rows"]] == ["2026-04-14"]
