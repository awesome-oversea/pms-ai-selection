from __future__ import annotations

import pytest
from src.infrastructure.database import get_async_session_factory
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
        return _Resp({"items": [{"id": "crm-001", "product_id": "prod-001", "feedback": "很好", "customer_score": 4.8}]})

    async def post(self, url, headers=None, json=None):
        return _Resp({"ok": True})


@pytest.mark.asyncio
async def test_crm_integration_service_test_connection_and_sync(monkeypatch):
    monkeypatch.setattr("src.infrastructure.crm_client.httpx.AsyncClient", _Client)
    session = get_async_session_factory()()
    try:
        service = ErpIntegrationService(session, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
        await service.save_crm_config(
            name="default",
            api_endpoint="http://fake-crm.local",
            api_key="demo-key",
            secret_key="demo-secret",
            inbound_path="/customer-feedbacks",
            outbound_path="/followups/bulk-upsert",
            timeout_seconds=5,
        )
        await session.commit()
        connection = await service.test_crm_connection(name="default")
        assert connection["status"] == "ok"
        assert connection["system_type"] == "crm"

        inbound = await service.sync_inbound_customer_feedback(name="default")
        await session.commit()
        assert inbound["status"] in {"completed", "partial_success"}

        outbound = await service.sync_outbound_customer_followup(name="default", limit=10)
        await session.commit()
        assert outbound["status"] == "completed"

        logs = await service.list_crm_logs(limit=10)
        assert logs["total"] >= 2
    finally:
        await session.close()
