from __future__ import annotations

import os

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

import pytest
from fastapi.testclient import TestClient
from src.core.auth import create_access_token
from src.main import create_app


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

    monkeypatch.setattr("src.infrastructure.database.init_db", _noop_init_db)
    monkeypatch.setattr("src.infrastructure.database.check_db_health", _healthy_db)
    monkeypatch.setattr("src.infrastructure.redis.check_redis_health", _healthy_redis)
    monkeypatch.setattr("src.infrastructure.qdrant.check_qdrant_health", _healthy_qdrant)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


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


def test_bff_auth_me_contract(client, auth_headers):
    resp = client.get("/api/v1/bff/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["username"] == "testuser"
    assert data["tenant_id"]
    assert isinstance(data["roles"], list)


def test_auth_me_contract(client, auth_headers):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["username"] == "testuser"
    assert data["tenant_key"] == "default"
    assert data["is_superuser"] is True


def test_bff_selection_stream_contract(client, auth_headers, monkeypatch):
    async def _fake_list_tasks(self, status=None, limit=20, offset=0):
        return {
            "total": 1,
            "tasks": [
                {
                    "task_id": "task-001",
                    "query": "蓝牙耳机",
                    "status": "running",
                    "phase": "market_analysis",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        }

    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.list_tasks", _fake_list_tasks)
    with client.stream("GET", "/api/v1/bff/workbench/selection/stream", headers=auth_headers) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["cache-control"] == "no-cache"
        assert resp.headers["x-accel-buffering"] == "no"
        body = "".join(resp.iter_text())
        assert "event: selection-workbench" in body
        assert "task-001" in body
        assert "market_analysis" in body
        assert "signals" in body
        assert "agent_steps" in body
        assert "client_reconnect" in body
        assert "retry: 3000" in body
        assert "keep-alive" in body
        assert '"protocol": "sse"' in body


def test_bff_selection_websocket_contract(client, auth_headers, monkeypatch):
    token = auth_headers["Authorization"].split(" ", 1)[1]

    async def _fake_list_tasks(self, status=None, limit=20, offset=0):
        return {
            "total": 1,
            "tasks": [
                {
                    "task_id": "task-ws-001",
                    "query": "蓝牙耳机",
                    "status": "running",
                    "phase": "market_analysis",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "decision_output": {
                        "market_summary": {"trend_direction": "up"},
                        "decision": {"decision": "GO"},
                        "risks": [{"level": "low"}],
                        "execution_summary": {"steps": [{"name": "market_analysis"}]},
                    },
                }
            ],
        }

    async def _fake_manual_intervene(self, task_id, action, comment=None):
        return {
            "task_id": task_id,
            "query": "蓝牙耳机",
            "status": "paused",
            "phase": "human_review",
            "status_reason": comment,
            "decision_output": {"decision": {"decision": "REVIEW"}},
        }

    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.list_tasks", _fake_list_tasks)
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.manual_intervene", _fake_manual_intervene)

    with client.websocket_connect(f"/api/v1/bff/workbench/selection/ws?token={token}") as websocket:
        first = websocket.receive_json()
        assert first["summary"]["username"] == "testuser"
        assert first["tasks"]["tasks"][0]["task_id"] == "task-ws-001"
        assert first["transport"]["protocol"] == "websocket"
        websocket.send_json({"action": "heartbeat"})
        heartbeat = websocket.receive_json()
        assert heartbeat["type"] == "heartbeat"
        websocket.send_json({"action": "refresh"})
        refreshed = websocket.receive_json()
        assert refreshed["signals"][0]["decision"] == "GO"
        websocket.send_json({
            "action": "intervene",
            "task_id": "task-ws-001",
            "intervention_action": "pause_and_review",
            "comment": "需要人工复核",
        })
        intervened = websocket.receive_json()
        assert intervened["tasks"]["tasks"][0]["task_id"] == "task-ws-001"


def test_bff_selection_detail_result_approval_feedback_contracts(client, auth_headers, monkeypatch):
    async def _fake_get_task(self, task_id):
        return {
            "task_id": task_id,
            "session_id": task_id,
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "query": "蓝牙耳机",
            "category": "electronics",
            "target_market": "US",
            "investment_budget": 50000,
            "status": "running",
            "phase": "market_analysis",
            "adoption": {"status": "pending", "execution_status": {"scm": {"status": "pending_review"}, "wms": {"status": "reserved"}, "som": {"status": "pending_approval"}, "oms": {"status": "read_only_feedback"}}},
        }

    async def _fake_get_task_result(self, task_id):
        return {
            "task_id": task_id,
            "query": "蓝牙耳机",
            "status": "completed",
            "result_summary": "执行完成",
            "decision_output": {"decision": {"decision": "GO"}},
            "similar_history_cases": {
                "case_type": "selection_history_case",
                "total_found": 1,
                "results": [{"source": "selection_case_task-001.md", "score": 0.92}],
            },
            "review_cases": {
                "case_type": "crm_review_case",
                "total_found": 1,
                "results": [{"source": "crm_review_case_crm-001.md", "score": 0.9}],
            },
            "historical_performance": {
                "case_type": "historical_performance",
                "total_found": 1,
                "results": [{"task_id": "task-history-001", "performance": {"oms": {"units": 28}}}],
            },
        }

    async def _fake_approve_task(self, task_id, action, reviewer, comment):
        return {"task_id": task_id, "action": action, "reviewer": reviewer, "comment": comment, "status": "approved"}

    async def _fake_add_feedback(self, task_id, payload):
        return {"task_id": task_id, "feedback_entry": payload, "status": "completed"}

    async def _fake_selection_adopt(self, task_id, quantity, scm_name="default", supplier_code=None, notes=None):
        assert scm_name == "scm-default"
        assert quantity == 240
        return {
            "task_id": task_id,
            "status": "adopted",
            "message": "采纳推荐成功",
            "adoption": {
                "status": "adopted",
                "scm_name": scm_name,
                "quantity": quantity,
                "supplier_code": supplier_code or "SUP-001",
            },
        }

    async def _fake_execute_adoption(self, *, task_id, scm_name="default", wms_name="default", oms_name="default", som_name="default", quantity=200, supplier_code=None, notes=None):
        assert scm_name == "scm-default"
        assert wms_name == "default"
        assert oms_name == "default"
        assert som_name == "default"
        assert quantity == 240
        return {
            "task_id": task_id,
            "status": "completed",
            "message": "采纳推荐并完成SCM/WMS建议承接，Listing草稿进入SOM待审批",
            "scm_receipt": {"purchase_order_id": "PO-task-001", "status": "pending_review"},
            "wms_reservation": {"reservation_id": "RSV-task-001", "status": "reserved", "location_code": "WH-A-01"},
            "som_listing_draft": {"listing_draft_id": "LST-task-001", "status": "pending_approval", "owner_domain": "som"},
            "adoption": {
                "status": "executed",
                "scm_name": scm_name,
                "quantity": quantity,
                "supplier_code": supplier_code or "SUP-001",
                "execution_status": {
                    "scm": {"status": "pending_review"},
                    "wms": {"status": "reserved"},
                    "som": {"status": "pending_approval"},
                    "oms": {"status": "read_only_feedback"},
                },
            },
        }

    async def _fake_feedback_feature_asset(self, task_id):
        return {
            "task_id": task_id,
            "feature_asset": {
                "asset_type": "feedback_feature_asset",
                "features": {"sales_7d": 7},
                "evaluation_sample": {"decision": "GO", "rescore_score": 83.9},
            },
        }

    async def _fake_feedback_loop_status(self, task_id, crm_name="default", paas_name="default"):
        assert crm_name == "crm-eu"
        assert paas_name == "paas-drill"
        return {
            "task_id": task_id,
            "crm": {"customer_feedback_ready": True},
            "bi": {"task_metrics_ready": True},
            "paas": {"workflow_ready": True},
            "selection_feedback_loop": {"rescore_ready": True, "auto_rescore_completed": True, "feature_asset_ready": True, "recommended_actions": []},
        }

    async def _fake_profit_trace(self, task_id, crm_name="default", fms_name="default", wms_name="default", paas_name="default"):
        assert crm_name == "crm-eu"
        assert fms_name == "fms-finance"
        assert wms_name == "wms-east"
        assert paas_name == "paas-drill"
        return {
            "task_id": task_id,
            "trace_id": f"selection-profit-trace-{task_id}",
            "trace_chain": {"selection": {"decision": "GO"}, "fms": {"profit_trace_ready": True}},
            "profit_contract": {"gross_profit_total": 139.0},
            "ready": True,
        }

    async def _fake_sync_execution_feedback(self, *, task_id, oms_name="default", crm_name="default", fms_name="default", wms_name="default", auto_rescore=True):
        assert auto_rescore is True
        return {
            "task_id": task_id,
            "execution_feedback_snapshot": {
                "sales": {"orders": {"orders": 2, "units": 12}},
                "reviews": {"avg_rating": 4.6, "review_count": 13},
                "profit": {"gross_profit_total": 139.0},
                "inventory": {"summary": {"available_quantity_total": 18}},
            },
            "rescore_payload": {"sales_7d": 12, "gross_profit": 139.0},
            "rescore_result": {"rescore_summary": {"decision": "GO", "score": 88.0}},
            "feature_asset": {"asset_type": "feedback_feature_asset"},
        }

    async def _fake_close_loop(self, *, task_id, oms_name="default", scm_name="default", wms_name="default", crm_name="default", fms_name="default", paas_name="default", limit=20):
        assert crm_name == "crm-eu"
        return {
            "task_id": task_id,
            "trace_id": f"selection-close-loop-{task_id}",
            "feedback_loop": {"auto_rescore_completed": True, "feature_asset_ready": True},
            "summary": {"close_loop_completed": True, "steps": ["selection", "scm", "wms", "oms", "fms"]},
            "route_status": {"selection_to_scm": True, "scm_to_wms": True, "wms_to_oms": True, "oms_to_fms": True},
        }

    async def _fake_ingest_selection_case(self, task):
        return {
            "doc_id": "case-doc-001",
            "filename": f"selection_case_{task['task_id']}.md",
            "status": "indexed",
            "chunk_count": 3,
            "case_type": "selection_history_case",
            "task_id": task["task_id"],
        }

    async def _fake_query_selection_cases(self, query, top_k, threshold):
        return {
            "query": query,
            "case_type": "selection_history_case",
            "total_found": 1,
            "results": [
                {
                    "content": "# 历史选品案例 task-001",
                    "score": 0.92,
                    "source": "selection_case_task-001.md",
                    "document_id": "case-doc-001",
                    "chunk_index": 0,
                    "metadata": {"filename": "selection_case_task-001.md"},
                }
            ],
        }

    async def _fake_review_case_ingest(self, task_id, crm_name="default", publish_events=True):
        return {
            "task_id": task_id,
            "matched_review_count": 1,
            "case_type": "crm_review_case",
            "ingested_cases": [{"doc_id": "review-doc-001", "review_id": "crm-001"}],
            "published_events": [{"event_id": "evt-review-001", "event_type": "review.updated"}] if publish_events else [],
        }

    async def _fake_query_review_cases(self, query, top_k, threshold):
        return {
            "query": query,
            "case_type": "crm_review_case",
            "total_found": 1,
            "results": [
                {
                    "content": "# CRM评价案例 crm-001",
                    "score": 0.9,
                    "source": "crm_review_case_crm-001.md",
                    "document_id": "review-doc-001",
                    "chunk_index": 0,
                    "metadata": {"filename": "crm_review_case_crm-001.md"},
                }
            ],
        }

    async def _fake_get_accuracy_trend(self, limit=100):
        return {
            "total_tasks": 2,
            "correct_tasks": 1,
            "accuracy": 0.5,
            "trend": [{"date": "2026-04-14", "total": 2, "correct": 1, "accuracy": 0.5, "cumulative_accuracy": 0.5}],
            "points": [],
        }

    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.get_task", _fake_get_task)
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.get_task_result", _fake_get_task_result)
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.get_accuracy_trend", _fake_get_accuracy_trend)
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.approve_task", _fake_approve_task)
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.add_feedback", _fake_add_feedback)
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.adopt_recommendation", _fake_selection_adopt)
    monkeypatch.setattr("src.api.v1.endpoints.bff.ErpIntegrationService.execute_selection_adoption", _fake_execute_adoption)
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.export_feedback_feature_asset", _fake_feedback_feature_asset)
    monkeypatch.setattr("src.api.v1.endpoints.bff.ErpIntegrationService.get_selection_feedback_loop_status", _fake_feedback_loop_status)
    monkeypatch.setattr("src.api.v1.endpoints.bff.ErpIntegrationService.get_selection_profit_trace", _fake_profit_trace)
    monkeypatch.setattr("src.api.v1.endpoints.bff.ErpIntegrationService.sync_selection_execution_feedback", _fake_sync_execution_feedback)
    monkeypatch.setattr("src.api.v1.endpoints.bff.ErpIntegrationService.close_selection_loop", _fake_close_loop)
    monkeypatch.setattr("src.api.v1.endpoints.bff.ErpIntegrationService.ingest_selection_review_cases", _fake_review_case_ingest)
    monkeypatch.setattr("src.api.v1.endpoints.bff.KnowledgeService.ingest_selection_case", _fake_ingest_selection_case)
    monkeypatch.setattr("src.api.v1.endpoints.bff.KnowledgeService.query_selection_cases", _fake_query_selection_cases)
    monkeypatch.setattr("src.api.v1.endpoints.bff.KnowledgeService.query_review_cases", _fake_query_review_cases)

    detail_resp = client.get("/api/v1/bff/workbench/selection/tasks/task-001", headers=auth_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["task_id"] == "task-001"

    result_resp = client.get("/api/v1/bff/workbench/selection/tasks/task-001/result", headers=auth_headers)
    assert result_resp.status_code == 200
    assert result_resp.json()["data"]["decision_output"]["decision"]["decision"] == "GO"
    assert result_resp.json()["data"]["similar_history_cases"]["case_type"] == "selection_history_case"
    assert result_resp.json()["data"]["review_cases"]["case_type"] == "crm_review_case"

    approve_resp = client.post(
        "/api/v1/bff/workbench/selection/tasks/task-001/approve",
        headers=auth_headers,
        json={"action": "approve", "comment": "通过", "reviewer": "testuser"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["data"]["status"] == "approved"

    feedback_resp = client.post(
        "/api/v1/bff/workbench/selection/tasks/task-001/feedback",
        headers=auth_headers,
        json={"source": "crm", "sentiment": "positive", "tags": ["high_potential"], "comment": "客户反馈较好"},
    )
    assert feedback_resp.status_code == 200
    assert feedback_resp.json()["data"]["feedback_entry"]["source"] == "crm"

    adopt_resp = client.post(
        "/api/v1/bff/workbench/selection/tasks/task-001/adopt",
        headers=auth_headers,
        json={"scm_name": "scm-default", "quantity": 240},
    )
    assert adopt_resp.status_code == 200
    assert adopt_resp.json()["data"]["adoption"]["status"] == "executed"
    assert adopt_resp.json()["data"]["adoption"]["quantity"] == 240
    assert adopt_resp.json()["data"]["scm_receipt"]["purchase_order_id"] == "PO-task-001"
    assert adopt_resp.json()["data"]["wms_reservation"]["status"] == "reserved"
    assert adopt_resp.json()["data"]["som_listing_draft"]["status"] == "pending_approval"
    assert adopt_resp.json()["data"]["som_listing_draft"]["owner_domain"] == "som"

    feedback_loop_resp = client.get(
        "/api/v1/bff/workbench/selection/tasks/task-001/feedback-loop-status",
        headers=auth_headers,
        params={"crm_name": "crm-eu", "paas_name": "paas-drill"},
    )
    assert feedback_loop_resp.status_code == 200
    assert feedback_loop_resp.json()["data"]["selection_feedback_loop"]["auto_rescore_completed"] is True

    profit_trace_resp = client.get(
        "/api/v1/bff/workbench/selection/tasks/task-001/profit-trace",
        headers=auth_headers,
        params={"crm_name": "crm-eu", "fms_name": "fms-finance", "wms_name": "wms-east", "paas_name": "paas-drill"},
    )
    assert profit_trace_resp.status_code == 200
    assert profit_trace_resp.json()["data"]["profit_contract"]["gross_profit_total"] == 139.0

    feature_asset_resp = client.get(
        "/api/v1/bff/workbench/selection/tasks/task-001/feedback-feature-asset",
        headers=auth_headers,
    )
    assert feature_asset_resp.status_code == 200
    assert feature_asset_resp.json()["data"]["feature_asset"]["asset_type"] == "feedback_feature_asset"

    execution_feedback_resp = client.post(
        "/api/v1/bff/workbench/selection/tasks/task-001/execution-feedback-sync",
        headers=auth_headers,
        json={"oms_name": "default", "crm_name": "default", "fms_name": "default", "wms_name": "default", "auto_rescore": True},
    )
    assert execution_feedback_resp.status_code == 200
    assert execution_feedback_resp.json()["data"]["execution_feedback_snapshot"]["sales"]["orders"]["units"] == 12
    assert execution_feedback_resp.json()["data"]["rescore_result"]["rescore_summary"]["decision"] == "GO"

    history_case_ingest_resp = client.post(
        "/api/v1/bff/workbench/selection/tasks/task-001/history-case-ingest",
        headers=auth_headers,
    )
    assert history_case_ingest_resp.status_code == 200
    assert history_case_ingest_resp.json()["data"]["case_type"] == "selection_history_case"

    history_case_query_resp = client.post(
        "/api/v1/bff/workbench/selection/history-cases/query",
        headers=auth_headers,
        json={"query": "蓝牙耳机 执行反馈", "top_k": 3, "threshold": 0.1},
    )
    assert history_case_query_resp.status_code == 200
    assert history_case_query_resp.json()["data"]["total_found"] == 1
    assert history_case_query_resp.json()["data"]["results"][0]["source"] == "selection_case_task-001.md"

    review_case_ingest_resp = client.post(
        "/api/v1/bff/workbench/selection/tasks/task-001/review-case-ingest",
        headers=auth_headers,
        json={"crm_name": "default", "publish_events": True},
    )
    assert review_case_ingest_resp.status_code == 200
    assert review_case_ingest_resp.json()["data"]["case_type"] == "crm_review_case"
    assert review_case_ingest_resp.json()["data"]["matched_review_count"] == 1

    review_case_query_resp = client.post(
        "/api/v1/bff/workbench/selection/review-cases/query",
        headers=auth_headers,
        json={"query": "蓝牙耳机 投诉 包装", "top_k": 3, "threshold": 0.1},
    )
    assert review_case_query_resp.status_code == 200
    assert review_case_query_resp.json()["data"]["case_type"] == "crm_review_case"
    assert review_case_query_resp.json()["data"]["results"][0]["source"] == "crm_review_case_crm-001.md"

    close_loop_overview_resp = client.get(
        "/api/v1/bff/workbench/selection/tasks/task-001/close-loop-overview",
        headers=auth_headers,
        params={"crm_name": "crm-eu", "fms_name": "fms-finance", "wms_name": "wms-east", "paas_name": "paas-drill"},
    )
    assert close_loop_overview_resp.status_code == 200
    close_loop_overview_data = close_loop_overview_resp.json()["data"]
    assert close_loop_overview_data["overview_ready"] is True
    assert close_loop_overview_data["feature_asset"]["asset_type"] == "feedback_feature_asset"
    assert close_loop_overview_data["profit_trace"]["profit_contract"]["gross_profit_total"] == 139.0
    assert close_loop_overview_data["adoption_status"]["execution_status"]["scm"]["status"] == "pending_review"
    assert close_loop_overview_data["similar_history_cases"]["case_type"] == "selection_history_case"
    assert close_loop_overview_data["review_cases"]["case_type"] == "crm_review_case"
    assert close_loop_overview_data["historical_performance"]["case_type"] == "historical_performance"

    accuracy_trend_resp = client.get(
        "/api/v1/bff/workbench/selection/accuracy-trend",
        headers=auth_headers,
        params={"limit": 100},
    )
    assert accuracy_trend_resp.status_code == 200
    accuracy_trend_data = accuracy_trend_resp.json()["data"]
    assert "accuracy" in accuracy_trend_data
    assert "trend" in accuracy_trend_data

    close_loop_resp = client.post(
        "/api/v1/bff/workbench/selection/tasks/task-001/close-loop",
        headers=auth_headers,
        json={"oms_name": "default", "scm_name": "default", "wms_name": "default", "crm_name": "crm-eu", "fms_name": "default", "limit": 20},
    )
    assert close_loop_resp.status_code == 200
    close_loop_data = close_loop_resp.json()["data"]
    assert close_loop_data["trace_id"] == "selection-close-loop-task-001"
    assert close_loop_data["summary"]["close_loop_completed"] is True
