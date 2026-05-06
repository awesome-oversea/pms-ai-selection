from __future__ import annotations

import os

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

import pytest
from fastapi.testclient import TestClient

from src.core.auth import create_access_token
from src.core.security import clear_audit_logs, latest_audit_log, list_audit_logs
from src.main import create_app


@pytest.fixture(autouse=True)
def _clear_audit_state():
    clear_audit_logs()
    yield
    clear_audit_logs()


@pytest.fixture
def client(monkeypatch):
    async def _noop_init_db():
        return None

    async def _healthy_db():
        return {"status": "healthy"}

    async def _healthy_redis():
        return {"status": "healthy"}

    async def _healthy_qdrant():
        return {"status": "healthy"}

    def _noop_get_redis_connection():
        return object()

    def _noop_get_qdrant_client():
        return object()

    async def _noop_close():
        return None

    monkeypatch.setattr("src.infrastructure.database.init_db", _noop_init_db)
    monkeypatch.setattr("src.infrastructure.database.close_db", _noop_close)
    monkeypatch.setattr("src.infrastructure.database.check_db_health", _healthy_db)
    monkeypatch.setattr("src.infrastructure.redis.get_redis_connection", _noop_get_redis_connection)
    monkeypatch.setattr("src.infrastructure.redis.close_redis", _noop_close)
    monkeypatch.setattr("src.infrastructure.redis.check_redis_health", _healthy_redis)
    monkeypatch.setattr("src.infrastructure.qdrant.get_qdrant_client", _noop_get_qdrant_client)
    monkeypatch.setattr("src.infrastructure.qdrant.close_qdrant", _noop_close)
    monkeypatch.setattr("src.infrastructure.qdrant.check_qdrant_health", _healthy_qdrant)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    token = create_access_token(
        {
            "sub": "testuser",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "is_superuser": True,
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "tenant_key": "default",
            "tenant_name": "Default Tenant",
            "roles": ["tenant_admin"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_selection_e2e_create_result_and_adopt_to_erp_suggestion_pool(client, auth_headers, monkeypatch) -> None:
    selection_task_id = "11111111-1111-1111-1111-111111111111"

    class _FakeSession:
        async def commit(self):
            return None

        async def refresh(self, _obj):
            return None

        async def close(self):
            return None

    async def _fake_create_task(self, payload, created_by=None, tenant_id=None):
        assert payload["query"] == "bluetooth headset market analysis"
        assert created_by == "00000000-0000-0000-0000-000000000001"
        assert tenant_id == "86d1f796-7c55-57a1-ac77-2e952a2111ca"
        return {
            "task_id": selection_task_id,
            "query": payload["query"],
            "status": "pending",
            "created_at": "2026-04-29T10:00:00+00:00",
            "tenant_id": tenant_id,
        }

    async def _fake_get_task_result(self, task_id):
        assert task_id == selection_task_id
        return {
            "task_id": task_id,
            "query": "bluetooth headset market analysis",
            "status": "completed",
            "result_summary": "recommendation generated",
            "go_no_go_decision": "GO",
            "decision_output": {
                "decision": {
                    "decision": "GO",
                    "recommendation": "launch bluetooth headset pro",
                },
                "pricing": {"recommended_price": 39.99},
                "supply_chain": {"primary_supplier": "SUP-ERP-001"},
                "recommendation_reasons": ["rising demand", "acceptable margin"],
            },
            "similar_history_cases": {
                "case_type": "selection_history_case",
                "total_found": 1,
                "results": [{"source": "selection_case_task-001.md", "score": 0.93}],
            },
            "completed_at": "2026-04-29T10:05:00+00:00",
        }

    async def _fake_execute_selection_adoption(
        self,
        *,
        task_id,
        scm_name="default",
        wms_name="default",
        oms_name="default",
        som_name="default",
        quantity=200,
        supplier_code=None,
        notes=None,
    ):
        assert task_id == selection_task_id
        assert self.tenant_id == "86d1f796-7c55-57a1-ac77-2e952a2111ca"
        assert scm_name == "scm-default"
        assert wms_name == "wms-default"
        assert oms_name == "oms-default"
        assert som_name == "som-default"
        assert quantity == 240
        assert supplier_code == "SUP-ERP-001"
        assert notes == "submit to ERP suggestion pool"
        return {
            "task_id": task_id,
            "status": "completed",
            "trace_id": f"selection-adopt-{task_id}",
            "purchase_suggestion": {
                "supplier_code": supplier_code,
                "quantity": quantity,
                "scm_name": scm_name,
                "api_path": "/api/internal/v1/scm/purchase-suggestions",
            },
            "scm_receipt": {
                "purchase_order_id": f"PO-{task_id}",
                "status": "pending_review",
            },
            "wms_reservation": {
                "reservation_id": f"RSV-{task_id}",
                "status": "reserved",
            },
            "som_listing_draft": {
                "listing_draft_id": f"LST-{task_id}",
                "status": "pending_approval",
                "owner_domain": "som",
            },
            "adoption": {
                "status": "executed",
                "supplier_code": supplier_code,
                "quantity": quantity,
                "scm_name": scm_name,
                "execution_status": {
                    "pdm": {"status": "submitted", "owner_domain": "pdm"},
                    "scm": {"status": "pending_review"},
                    "wms": {"status": "reserved"},
                    "som": {"status": "pending_approval"},
                    "oms": {"status": "read_only_feedback"},
                },
            },
            "message": "adoption submitted to ERP suggestion pool",
        }

    async def _fake_get_db_session():
        return _FakeSession()

    class _FakeIntegrationService:
        def __init__(self, tenant_id: str):
            self.tenant_id = tenant_id

        async def execute_selection_adoption(self, **kwargs):
            return await _fake_execute_selection_adoption(self, **kwargs)

    async def _fake_get_integration_service(current_user: dict):
        session = _FakeSession()
        service = _FakeIntegrationService(current_user["tenant_id"])
        return service, session

    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.create_task", _fake_create_task)
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.get_task_result", _fake_get_task_result)
    monkeypatch.setattr("src.api.v1.endpoints.selection._get_db_session", _fake_get_db_session)
    monkeypatch.setattr("src.api.v1.endpoints.integration._get_service", _fake_get_integration_service)

    create_resp = client.post(
        "/api/v1/selection/tasks",
        headers=auth_headers,
        json={
            "query": "bluetooth headset market analysis",
            "category": "electronics",
            "target_market": "US",
            "investment_budget": 50000,
        },
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()
    assert create_data["task_id"] == selection_task_id
    assert create_data["status"] == "pending"
    assert create_data["phase"] == "pending"
    create_logs = list_audit_logs(action="selection.task.create")
    assert len(create_logs) == 1
    assert create_logs[0]["target_id"] == selection_task_id

    result_resp = client.get(
        f"/api/v1/selection/tasks/{selection_task_id}/result",
        headers=auth_headers,
    )
    assert result_resp.status_code == 200
    result_data = result_resp.json()
    assert result_data["status"] == "completed"
    assert result_data["go_no_go_decision"] == "GO"
    assert result_data["decision_output"]["decision"]["recommendation"] == "launch bluetooth headset pro"
    assert result_data["decision_output"]["pricing"]["recommended_price"] == 39.99
    assert result_data["decision_output"]["supply_chain"]["primary_supplier"] == "SUP-ERP-001"

    adopt_resp = client.post(
        f"/api/v1/integration/selection/{selection_task_id}/adopt",
        headers=auth_headers,
        json={
            "scm_name": "scm-default",
            "wms_name": "wms-default",
            "oms_name": "oms-default",
            "som_name": "som-default",
            "quantity": 240,
            "supplier_code": "SUP-ERP-001",
            "notes": "submit to ERP suggestion pool",
        },
    )
    assert adopt_resp.status_code == 200
    adopt_data = adopt_resp.json()["data"]
    assert adopt_data["trace_id"] == f"selection-adopt-{selection_task_id}"
    assert adopt_data["purchase_suggestion"]["api_path"] == "/api/internal/v1/scm/purchase-suggestions"
    assert adopt_data["purchase_suggestion"]["quantity"] == 240
    assert adopt_data["scm_receipt"]["status"] == "pending_review"
    assert adopt_data["wms_reservation"]["status"] == "reserved"
    assert adopt_data["som_listing_draft"]["status"] == "pending_approval"
    assert adopt_data["som_listing_draft"]["owner_domain"] == "som"
    assert adopt_data["adoption"]["status"] == "executed"
    assert adopt_data["adoption"]["execution_status"]["pdm"]["status"] == "submitted"
    assert adopt_data["adoption"]["execution_status"]["som"]["status"] == "pending_approval"

    adopt_logs = list_audit_logs(action="integration.selection.adopt")
    assert len(adopt_logs) == 1
    assert adopt_logs[0]["target_id"] == selection_task_id
    assert adopt_logs[0]["detail"]["trace_id"] == f"selection-adopt-{selection_task_id}"
    assert latest_audit_log()["action"] == "integration.selection.adopt"
