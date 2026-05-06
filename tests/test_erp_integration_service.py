from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from src.infrastructure.bi_client import BIClient
from src.infrastructure.crm_client import CRMClient
from src.infrastructure.fms_client import FMSClient
from src.infrastructure.oms_client import OMSClient
from src.infrastructure.paas_client import PaaSClient
from src.infrastructure.scm_client import SCMClient
from src.infrastructure.wms_client import WMSClient
from src.models.enums import TaskPriority, TaskStatus
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
        return _Resp({"items": []})

    async def post(self, url, headers=None, json=None):
        return _Resp({"ok": True})


@pytest.mark.asyncio
async def test_erp_integration_service_test_connection(monkeypatch):
    monkeypatch.setattr("src.infrastructure.oms_client.httpx.AsyncClient", _Client)

    fake_config = SimpleNamespace(
        id="cfg-001",
        name="default",
        system_type=SimpleNamespace(value="oms"),
        api_endpoint="http://fake-oms.local",
        api_key="demo-key",
        extra_config={"inbound_path": "/products", "outbound_path": "/products/bulk-upsert", "timeout_seconds": 5},
    )

    async def _fake_get_config(system_type, name="default"):
        return fake_config

    service = ErpIntegrationService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    service.repo = SimpleNamespace(get_config=_fake_get_config)
    result = await service.test_oms_connection(name="default")
    assert result["status"] == "ok"
    assert result["system_type"] == "oms"


@pytest.mark.asyncio
async def test_erp_integration_service_oms_config_actions():
    fake_config = SimpleNamespace(
        id="cfg-001",
        name="default",
        system_type=SimpleNamespace(value="oms"),
        api_endpoint="http://fake-oms.local",
        api_key="demo-key",
        extra_config={"config_version": 1, "sync_cursor": "2026-04-17T00:00:00+00:00", "manual_state": "enabled"},
        is_active=True,
    )

    async def _fake_get_config(system_type, name="default"):
        return fake_config

    async def _fake_flush():
        return None

    service = ErpIntegrationService(session=SimpleNamespace(flush=_fake_flush), tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    service.repo = SimpleNamespace(get_config=_fake_get_config)

    reset_result = await service.reset_oms_cursor(name="default")
    assert reset_result["sync_cursor"] is None
    assert reset_result["config_version"] == 2

    disable_result = await service.disable_oms_config(name="default")
    assert disable_result["manual_state"] == "disabled"
    assert disable_result["config_version"] == 3
    assert fake_config.is_active is False


@pytest.mark.asyncio
async def test_erp_integration_service_operational_statuses(monkeypatch):
    monkeypatch.setattr("src.infrastructure.oms_client.httpx.AsyncClient", _Client)
    monkeypatch.setattr("src.infrastructure.scm_client.httpx.AsyncClient", _Client)
    monkeypatch.setattr("src.infrastructure.crm_client.httpx.AsyncClient", _Client)
    monkeypatch.setattr("src.infrastructure.fms_client.httpx.AsyncClient", _Client)

    fake_configs = {
        "oms": SimpleNamespace(
            id="cfg-oms-001",
            name="default",
            system_type=SimpleNamespace(value="oms"),
            api_endpoint="http://fake-oms.local",
            api_key="demo-key",
            extra_config={"inbound_path": "/products", "outbound_path": "/products/bulk-upsert", "timeout_seconds": 5},
        ),
        "scm": SimpleNamespace(
            id="cfg-scm-001",
            name="default",
            system_type=SimpleNamespace(value="scm"),
            api_endpoint="http://fake-scm.local",
            api_key="demo-key",
            extra_config={"inbound_path": "/supplier-products", "outbound_path": "/product-plans/bulk-upsert", "timeout_seconds": 5},
        ),
        "crm": SimpleNamespace(
            id="cfg-crm-001",
            name="default",
            system_type=SimpleNamespace(value="crm"),
            api_endpoint="http://fake-crm.local",
            api_key="demo-key",
            extra_config={"inbound_path": "/customer-feedback", "outbound_path": "/followups/bulk-upsert", "timeout_seconds": 5},
        ),
        "fms": SimpleNamespace(
            id="cfg-fms-001",
            name="default",
            system_type=SimpleNamespace(value="fms"),
            api_endpoint="http://fake-fms.local",
            api_key="demo-key",
            extra_config={"inbound_path": "/finance-metrics", "outbound_path": "/profit-plans/bulk-upsert", "timeout_seconds": 5},
        ),
    }

    async def _fake_get_config(system_type, name="default"):
        key = system_type.value if hasattr(system_type, "value") else str(system_type)
        return fake_configs[key]

    service = ErpIntegrationService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    service.repo = SimpleNamespace(get_config=_fake_get_config)

    async def _fake_fetch_orders(self):
        return [{"order_id": "ORD-001", "quantity": 2, "revenue": 199.0}, {"order_id": "ORD-002", "quantity": 1, "revenue": 99.0}]

    async def _fake_fetch_sales_metrics(self):
        return [{"sales": 298.0, "conversion_rate": 0.13}, {"sales_7d": 200.0, "conversion": 0.11}]

    async def _fake_fetch_quotes(self):
        return [{"supplier_code": "SUP-001", "procurement_price": 23.5}, {"supplier_name": "供应商A", "quote_price": 24.5}]

    async def _fake_fetch_feedbacks(self):
        return [{"id": "crm-001", "product_id": "prod-001", "feedback": "退款投诉", "customer_score": 4.8, "review_count": 12}]

    async def _fake_fetch_complaints(self):
        return [{"id": "complaint-001", "product_id": "prod-001", "reason": "物流延迟", "feedback": "物流投诉"}]

    async def _fake_fetch_profit_facts(self):
        return [{"gross_profit": 99.0, "cost": 20.0, "margin_rate": 0.28}, {"profit": 40.0, "cost": 10.0, "margin": 0.21}]

    async def _fake_fetch_ad_spending(self):
        return [{"product_id": "prod-001", "ad_spending": 30.0, "ad_sales": 120.0}, {"product_id": "prod-002", "advertising_spend": 20.0, "advertising_sales": 80.0}]

    monkeypatch.setattr("src.infrastructure.oms_client.OMSClient.fetch_orders", _fake_fetch_orders)
    monkeypatch.setattr("src.infrastructure.oms_client.OMSClient.fetch_sales_metrics", _fake_fetch_sales_metrics)
    monkeypatch.setattr("src.infrastructure.scm_client.SCMClient.fetch_supplier_quotes", _fake_fetch_quotes)
    monkeypatch.setattr("src.infrastructure.crm_client.CRMClient.fetch_customer_feedbacks", _fake_fetch_feedbacks)
    monkeypatch.setattr("src.infrastructure.crm_client.CRMClient.fetch_complaints", _fake_fetch_complaints)
    monkeypatch.setattr("src.infrastructure.fms_client.FMSClient.fetch_profit_facts", _fake_fetch_profit_facts)
    monkeypatch.setattr("src.infrastructure.fms_client.FMSClient.fetch_ad_spending", _fake_fetch_ad_spending)

    oms_status = await service.get_oms_operational_status(name="default")
    scm_status = await service.get_scm_operational_status(name="default")
    crm_status = await service.get_crm_operational_status(name="default")
    fms_status = await service.get_fms_operational_status(name="default")

    assert oms_status["system_type"] == "oms"
    assert oms_status["order_summary"]["orders"] == 2
    assert oms_status["sales_summary"]["items"] == 2
    assert oms_status["result_writeback_ready"] is True

    assert scm_status["system_type"] == "scm"
    assert scm_status["quote_summary"]["items"] == 2
    assert scm_status["purchase_suggestion_ready"] is True

    assert crm_status["system_type"] == "crm"
    assert crm_status["customer_feedback_ready"] is True
    assert crm_status["feedback_summary"]["avg_rating"] == 4.8
    assert crm_status["feedback_summary"]["complaint_count"] >= 1
    assert crm_status["complaint_summary"]["items"] == 1
    assert crm_status["complaint_summary"]["reason_breakdown"]["logistics"] >= 1

    assert fms_status["system_type"] == "fms"
    assert fms_status["profit_summary"]["items"] == 2
    assert fms_status["ad_spending_summary"]["items"] == 2
    assert fms_status["ad_spending_summary"]["acos"] == 0.25
    assert fms_status["profit_trace_ready"] is True


@pytest.mark.asyncio
async def test_oms_operational_status_applies_actor_permission_filter(monkeypatch):
    fake_config = SimpleNamespace(
        id="cfg-oms-filter-001",
        name="default",
        system_type=SimpleNamespace(value="oms"),
        api_endpoint="http://fake-oms.local",
        api_key="demo-key",
        extra_config={"inbound_path": "/orders", "outbound_path": "/products/bulk-upsert", "timeout_seconds": 5},
    )

    async def _fake_get_config(system_type, name="default"):
        return fake_config

    async def _fake_fetch_orders(self, permission_context=None):
        rows = [
            {"order_id": "ORD-US", "tenant_id": "tenant-a", "store_id": "store-us", "marketplace": "US", "quantity": 2, "revenue": 100.0},
            {"order_id": "ORD-EU", "tenant_id": "tenant-a", "store_id": "store-eu", "marketplace": "EU", "quantity": 9, "revenue": 900.0},
        ]
        assert permission_context is not None
        return [row for row in rows if row.get("store_id") == permission_context.store_id and row.get("marketplace") == permission_context.marketplace]

    async def _fake_fetch_sales_metrics(self, permission_context=None):
        assert permission_context is not None
        return [{"sales": 100.0, "store_id": permission_context.store_id, "marketplace": permission_context.marketplace}]

    monkeypatch.setattr("src.infrastructure.oms_client.OMSClient.fetch_orders", _fake_fetch_orders)
    monkeypatch.setattr("src.infrastructure.oms_client.OMSClient.fetch_sales_metrics", _fake_fetch_sales_metrics)

    service = ErpIntegrationService(
        session=None,
        tenant_id="tenant-a",
        actor={"tenant_id": "tenant-a", "user_id": "user-001", "store_id": "store-us", "marketplace": "US", "trace_id": "trace-filter-001"},
    )
    service.repo = SimpleNamespace(get_config=_fake_get_config)

    result = await service.get_oms_operational_status(name="default")

    assert result["order_summary"]["orders"] == 1
    assert result["order_summary"]["units"] == 2
    assert result["sales_summary"]["items"] == 1


@pytest.mark.asyncio
async def test_latest_bi_kpi_applies_actor_permission_filter(monkeypatch):
    fake_config = SimpleNamespace(
        id="cfg-bi-filter-001",
        name="default",
        system_type=SimpleNamespace(value="bi"),
        api_endpoint="http://fake-bi.local",
        api_key="demo-key",
        extra_config={"health_path": "/health", "dataset_path": "/datasets", "timeout_seconds": 5},
    )

    async def _fake_get_config(system_type, name="default"):
        return fake_config

    async def _fake_read_dataset(self, permission_context=None):
        rows = [
            {"kpi_date": "2026-04-14", "tenant_id": "tenant-a", "store_id": "store-us", "marketplace": "US", "ROI": 1.2},
            {"kpi_date": "2026-04-15", "tenant_id": "tenant-a", "store_id": "store-eu", "marketplace": "EU", "ROI": 9.9},
        ]
        assert permission_context is not None
        return {
            "datasets": [
                {
                    "dataset_name": "selection_daily_kpis",
                    "rows": [row for row in rows if row["store_id"] == permission_context.store_id and row["marketplace"] == permission_context.marketplace],
                }
            ]
        }

    monkeypatch.setattr("src.infrastructure.bi_client.BIClient.read_dataset", _fake_read_dataset)

    service = ErpIntegrationService(
        session=None,
        tenant_id="tenant-a",
        actor={"tenant_id": "tenant-a", "user_id": "user-001", "store_id": "store-us", "marketplace": "US", "trace_id": "trace-bi-filter-001"},
    )
    service.repo = SimpleNamespace(get_config=_fake_get_config)

    result = await service.get_latest_daily_selection_kpis(name="default")

    assert result["kpi_date"] == "2026-04-14"
    assert result["ROI"] == 1.2


@pytest.mark.asyncio
async def test_close_selection_loop_auto_rescores_and_exports_feature_asset():
    service = ErpIntegrationService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})

    task = SimpleNamespace(
        id="task-close-loop-001",
        title="蓝牙耳机",
        target_category="electronics",
        target_market="US",
        config={
            "trace_id": "trace-close-loop-001",
            "execution_result": {
                "decision_output": {
                    "decision": {"decision": "GO"},
                    "pricing": {"recommended_price": 39.99},
                    "supply_chain": {"primary_supplier": "SUP-001"},
                }
            },
        },
    )

    async def _fake_get_task(task_id):
        return task

    async def _fake_sync_outbound_product_plan(name="default", limit=20):
        return {"status": "completed", "system_type": "scm"}

    async def _fake_sync_outbound_replenishment_plan(name="default", limit=20):
        return {"status": "completed", "system_type": "wms"}

    async def _fake_sync_outbound_products(name="default", limit=20):
        return {"status": "completed", "system_type": "oms"}

    async def _fake_sync_outbound_profit_plan(name="default", limit=20):
        return {"status": "completed", "system_type": "fms"}

    async def _fake_get_oms_operational_status(name="default"):
        return {
            "system_type": "oms",
            "sales_summary": {"items": 7, "sales": 298.0, "avg_conversion_rate": 0.12},
            "result_writeback_ready": True,
        }

    async def _fake_get_wms_operational_status(name="default"):
        return {
            "system_type": "wms",
            "inventory_summary": {"available_quantity_total": 18, "low_stock_count": 0},
            "fulfillment_status": {"status": "healthy", "backorder_risk": False},
        }

    async def _fake_get_crm_operational_status(name="default"):
        return {
            "system_type": "crm",
            "feedback_summary": {"avg_rating": 4.7, "review_count": 12, "complaint_count": 1},
            "customer_feedback_ready": True,
        }

    async def _fake_get_fms_operational_status(name="default"):
        return {
            "system_type": "fms",
            "profit_summary": {"gross_profit_total": 139.0, "avg_margin_rate": 0.28},
            "profit_trace_ready": True,
        }

    class _FakeSelectionTaskService:
        def __init__(self, session, tenant_id=None, actor=None):
            self.session = session
            self.tenant_id = tenant_id
            self.actor = actor

        async def rescore_task_from_execution_feedback(self, task_id, payload):
            return {
                "task_id": task_id,
                "rescore_summary": {"score": 83.9, "decision": "GO"},
                "decision_output": {"execution_feedback": payload},
            }

        async def export_feedback_feature_asset(self, task_id):
            return {
                "task_id": task_id,
                "feature_asset": {
                    "asset_type": "feedback_feature_asset",
                    "features": {"sales_7d": 7},
                    "evaluation_sample": {"decision": "GO", "rescore_score": 83.9},
                },
            }

    service.selection_repo = SimpleNamespace(get_task=_fake_get_task)
    service.sync_outbound_product_plan = _fake_sync_outbound_product_plan
    service.sync_outbound_replenishment_plan = _fake_sync_outbound_replenishment_plan
    service.sync_outbound_products = _fake_sync_outbound_products
    service.sync_outbound_profit_plan = _fake_sync_outbound_profit_plan
    service.get_oms_operational_status = _fake_get_oms_operational_status
    service.get_wms_operational_status = _fake_get_wms_operational_status
    service.get_crm_operational_status = _fake_get_crm_operational_status
    service.get_fms_operational_status = _fake_get_fms_operational_status

    from src.services import erp_integration_service as erp_module

    original_selection_task_service = erp_module.SelectionTaskService
    erp_module.SelectionTaskService = _FakeSelectionTaskService
    try:
        result = await service.close_selection_loop(task_id="task-close-loop-001")
    finally:
        erp_module.SelectionTaskService = original_selection_task_service

    assert result["summary"]["close_loop_completed"] is True
    assert result["feedback_loop"]["auto_rescore_completed"] is True
    assert result["feedback_loop"]["feature_asset_ready"] is True
    assert result["feedback_loop"]["rescore_summary"]["decision"] == "GO"
    assert result["feedback_loop"]["feature_asset"]["asset_type"] == "feedback_feature_asset"
    assert result["feedback_loop"]["rescore_inputs"]["review_rating"] == 4.7
    assert result["feedback_loop"]["rescore_inputs"]["review_count"] == 12
    assert result["feedback_loop"]["rescore_inputs"]["stockout_risk"] is True
    assert result["feedback_loop"]["rescore_inputs"]["gross_profit"] == 139.0
    assert result["feedback_loop"]["rescore_inputs"]["available_inventory"] == 18


@pytest.mark.asyncio
async def test_get_profit_trend_aggregates_points_by_date():
    service = ErpIntegrationService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})

    class _FakeClient:
        async def fetch_profit_facts(self):
            return [
                {"profit_date": "2026-04-15", "gross_profit": 100.0, "cost": 40.0, "margin_rate": 0.25, "ad_spending": 10.0, "ad_sales": 50.0},
                {"profit_date": "2026-04-15", "gross_profit": 50.0, "cost": 20.0, "margin_rate": 0.35, "ad_spending": 5.0, "ad_sales": 25.0},
                {"profit_date": "2026-04-16", "gross_profit": 80.0, "cost": 30.0, "margin_rate": 0.40, "ad_spending": 8.0, "ad_sales": 40.0},
            ]

    fake_config = SimpleNamespace(id="cfg-fms", name="default", api_endpoint="http://fake-fms.local", extra_config={})

    async def _fake_get_required_config(system_type, name, error_message):
        return fake_config

    service._get_required_config = _fake_get_required_config
    service._build_fms_client = lambda config: _FakeClient()

    result = await service.get_profit_trend(name="default")
    assert result["ready"] is True
    assert result["total_points"] == 2
    assert result["points"][0]["date"] == "2026-04-15"
    assert result["points"][0]["gross_profit"] == 150.0
    assert result["points"][0]["cost"] == 60.0
    assert result["points"][0]["acos"] == 0.2


@pytest.mark.asyncio
async def test_get_selection_feedback_loop_status_filters_logs_by_config_name():
    service = ErpIntegrationService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})

    task = SimpleNamespace(
        id="task-feedback-state-002",
        config={
            "feedback_loop_rescored": True,
            "feedback_loop_rescore": {"score": 88.0, "decision": "GO"},
            "feedback_feature_asset_ready": True,
            "feedback_feature_asset": {"asset_type": "feedback_feature_asset"},
            "execution_result": {
                "decision_output": {
                    "decision": {"decision": "GO"},
                    "pricing": {"recommended_price": 39.99},
                    "rescore_summary": {"score": 88.0, "decision": "GO"},
                }
            },
        },
    )

    async def _fake_get_selection_task(task_id):
        return task

    async def _fake_get_bi_task_metrics(task_id):
        return {
            "task_id": task_id,
            "recommended_price": 39.99,
            "decision": "GO",
            "rescore_score": 88.0,
            "feedback_feature_asset_ready": True,
        }

    async def _fake_list_crm_logs(limit=5, name="default"):
        assert name == "crm-eu"
        return {"total": 1, "logs": [{"config_name": "crm-eu", "status": "completed"}]}

    async def _fake_list_bi_logs(limit=5, name="default"):
        assert name == "default"
        return {"total": 1, "logs": [{"config_name": "default", "status": "completed"}]}

    async def _fake_list_paas_logs(limit=5, name="default"):
        assert name == "paas-drill"
        return {"total": 1, "logs": [{"log_id": "log-paas-drill-001", "config_name": "paas-drill", "status": "dispatched"}]}

    async def _fake_get_paas_run_status(name="default", run_id=""):
        assert name == "paas-drill"
        assert run_id == "log-paas-drill-001"
        return {"system_type": "paas", "status": "running", "callback_expected": True}

    service._get_selection_task = _fake_get_selection_task
    service.get_bi_task_metrics = _fake_get_bi_task_metrics
    service.list_crm_logs = _fake_list_crm_logs
    service.list_bi_logs = _fake_list_bi_logs
    service.list_paas_logs = _fake_list_paas_logs
    service.get_paas_run_status = _fake_get_paas_run_status

    result = await service.get_selection_feedback_loop_status(task_id="task-feedback-state-002", crm_name="crm-eu", paas_name="paas-drill")
    assert result["crm"]["config_name"] == "crm-eu"
    assert result["crm"]["latest_log"]["config_name"] == "crm-eu"
    assert result["paas"]["latest_log"]["config_name"] == "paas-drill"
    assert result["selection_feedback_loop"]["feature_asset_ready"] is True


@pytest.mark.asyncio
async def test_get_selection_feedback_loop_status_reads_persisted_feedback_state():
    service = ErpIntegrationService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})

    task = SimpleNamespace(
        id="task-feedback-state-001",
        config={
            "feedback_loop_rescored": True,
            "feedback_loop_rescore": {"score": 92.5, "decision": "GO"},
            "feedback_feature_asset_ready": True,
            "feedback_feature_asset": {"asset_type": "feedback_feature_asset"},
            "execution_result": {
                "decision_output": {
                    "rescore_summary": {"score": 92.5, "decision": "GO"},
                }
            },
        },
    )

    async def _fake_get_selection_task(task_id):
        return task

    async def _fake_get_bi_task_metrics(task_id):
        return {
            "task_id": task_id,
            "recommended_price": 39.99,
            "roi_year1_percent": 42.0,
            "decision": "GO",
            "rescore_score": 92.5,
            "feedback_feature_asset_ready": True,
        }

    async def _fake_list_logs(limit=5, name="default"):
        return {"logs": [{"status": "completed", "log_id": "log-001", "config_name": name}]}

    async def _fake_get_paas_run_status(name="default", run_id="log-paas-latest"):
        return {"system_type": "paas", "status": "running", "callback_expected": True, "retry_recommended": False}

    service._get_selection_task = _fake_get_selection_task
    service.get_bi_task_metrics = _fake_get_bi_task_metrics
    service.list_crm_logs = _fake_list_logs
    service.list_bi_logs = _fake_list_logs
    service.list_paas_logs = _fake_list_logs
    service.get_paas_run_status = _fake_get_paas_run_status

    result = await service.get_selection_feedback_loop_status("task-feedback-state-001")
    assert result["selection_feedback_loop"]["auto_rescore_completed"] is True
    assert result["selection_feedback_loop"]["feature_asset_ready"] is True
    assert result["selection_feedback_loop"]["rescore_summary"]["score"] == 92.5
    assert result["selection_feedback_loop"]["feature_asset"]["asset_type"] == "feedback_feature_asset"


@pytest.mark.asyncio
async def test_compute_daily_selection_kpis_aggregates_execution_feedback():
    service = ErpIntegrationService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})

    task = SimpleNamespace(
        id="selection-task-kpi-001",
        title="蓝牙耳机",
        target_category="electronics",
        target_market="US",
        created_at=datetime.fromisoformat("2026-04-10T00:00:00+00:00"),
        completed_at=datetime.fromisoformat("2026-04-14T00:00:00+00:00"),
        config={
            "adoption": {
                "status": "executed",
                "total_amount": 240.0,
                "adopted_at": "2026-04-14T00:00:00+00:00",
            },
            "execution_feedback_snapshot": {
                "sales": {"orders": {"units": 32}},
                "reviews": {"avg_rating": 4.6, "review_count": 13},
                "profit": {"gross_profit_total": 139.0, "cost_total": 80.0},
                "inventory": {"summary": {"available_quantity_total": 18}},
                "synced_at": "2026-04-14T01:00:00+00:00",
            },
            "execution_result": {
                "decision_output": {
                    "decision": {"decision": "GO"},
                }
            },
        },
    )

    class _Repo:
        async def list_tasks(self, limit=100, offset=0):
            return [task], 1

    service.selection_repo = _Repo()
    result = await service.compute_daily_selection_kpis(day="2026-04-14")
    assert result["kpi_date"] == "2026-04-14"
    assert result["summary"]["task_count"] == 1
    assert result["summary"]["爆款命中率"] == 1.0
    assert round(result["summary"]["ROI"], 4) == round((139.0 / 240.0) * 100, 4)
    assert result["summary"]["选品周期"] == 4.0
    assert result["rows"][0]["is_hot_hit"] is True


@pytest.mark.asyncio
async def test_sync_daily_bi_kpis_writes_selection_daily_kpis_dataset():
    artifacts_root = Path("artifacts/erp_local").resolve().as_posix()
    bi_outbound = Path("artifacts/erp_local/bi/outbound-datasets.json")
    if bi_outbound.exists():
        bi_outbound.unlink()

    service = ErpIntegrationService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    config = SimpleNamespace(
        id=uuid.uuid4(),
        name="default",
        system_type=SimpleNamespace(value="bi"),
        api_endpoint=f"file://{artifacts_root}/bi",
        api_key=None,
        extra_config={"health_path": "/health.json", "dataset_path": "/outbound-datasets.json", "timeout_seconds": 5},
        last_sync_at=None,
    )

    class _Repo:
        created = None
        updated = None

        async def create_sync_log(self, *, config_id: str, sync_type: str, entity_type: str):
            self.created = {"config_id": config_id, "sync_type": sync_type, "entity_type": entity_type}
            return SimpleNamespace(id=uuid.uuid4(), sync_type=sync_type, entity_type=entity_type, status="running", items_total=0, items_success=0, items_failed=0, error_detail=None, started_at=datetime.now(UTC), finished_at=None, duration_seconds=None)

        async def update_sync_log(self, log_id: str, **fields):
            self.updated = fields
            return fields

    async def _fake_get_required_config(system_type, name, message):
        return config

    async def _fake_compute_daily_selection_kpis(day=None, limit=200):
        return {
            "kpi_date": day or "2026-04-14",
            "generated_at": "2026-04-14T10:00:00+00:00",
            "input_scope": {"day": day, "task_limit": limit},
            "summary": {"task_count": 1, "爆款命中率": 1.0, "ROI": 57.9167, "选品周期": 4.0},
            "rows": [{"task_id": "selection-task-kpi-001", "kpi_date": day or "2026-04-14"}],
        }

    service.repo = _Repo()
    service._get_required_config = _fake_get_required_config
    service.compute_daily_selection_kpis = _fake_compute_daily_selection_kpis

    result = await service.sync_daily_bi_kpis(name="default", day="2026-04-14")
    payload = json.loads(bi_outbound.read_text(encoding="utf-8"))
    dataset = next(item for item in payload["datasets"] if item["dataset_name"] == "selection_daily_kpis")
    assert result["entity_type"] == "selection_daily_kpis"
    assert dataset["rows"][0]["summary"]["task_count"] == 1
    assert dataset["rows"][0]["kpi_date"] == "2026-04-14"


@pytest.mark.asyncio
async def test_erp_file_artifact_clients_roundtrip():
    artifacts_root = Path("artifacts/erp_local").resolve().as_posix()

    bi_outbound = Path("artifacts/erp_local/bi/outbound-datasets.json")
    scm_outbound = Path("artifacts/erp_local/scm/outbound-product-plan.json")
    wms_outbound = Path("artifacts/erp_local/wms/outbound-replenishment.json")
    crm_outbound = Path("artifacts/erp_local/crm/outbound-followups.json")
    fms_outbound = Path("artifacts/erp_local/fms/outbound-profit-plan.json")
    paas_status = Path("artifacts/erp_local/paas/runs/run-selection-task-erp-real-001.json")
    for path in [bi_outbound, scm_outbound, wms_outbound, crm_outbound, fms_outbound, paas_status]:
        if path.exists():
            path.unlink()

    oms_client = OMSClient(api_endpoint=f"file://{artifacts_root}/oms", api_key=None, inbound_path="/orders.json", outbound_path="/outbound-products.json", timeout_seconds=5)
    scm_client = SCMClient(api_endpoint=f"file://{artifacts_root}/scm", api_key=None, inbound_path="/quotes.json", outbound_path="/outbound-product-plan.json", timeout_seconds=5)
    wms_client = WMSClient(api_endpoint=f"file://{artifacts_root}/wms", api_key=None, inbound_path="/inventory.json", outbound_path="/outbound-replenishment.json", timeout_seconds=5)
    crm_client = CRMClient(api_endpoint=f"file://{artifacts_root}/crm", api_key=None, inbound_path="/feedback.json", outbound_path="/outbound-followups.json", timeout_seconds=5)
    fms_client = FMSClient(api_endpoint=f"file://{artifacts_root}/fms", api_key=None, inbound_path="/profit.json", outbound_path="/outbound-profit-plan.json", timeout_seconds=5)
    bi_client = BIClient(api_endpoint=f"file://{artifacts_root}/bi", api_key=None, health_path="/health.json", dataset_path="/outbound-datasets.json", timeout_seconds=5)
    paas_client = PaaSClient(api_endpoint=f"file://{artifacts_root}/paas", api_key=None, health_path="/health.json", trigger_path="/trigger.json", status_path="/runs/{run_id}.json", timeout_seconds=5)

    assert (await oms_client.test_connection())["status"] == "ok"
    assert (await scm_client.test_connection())["status"] == "ok"
    assert (await wms_client.test_connection())["status"] == "ok"
    assert (await crm_client.test_connection())["status"] == "ok"
    assert (await fms_client.test_connection())["status"] == "ok"
    assert (await bi_client.test_connection())["status"] == "ok"
    assert (await paas_client.test_connection())["status"] == "ok"

    orders = await oms_client.fetch_orders()
    quotes = await scm_client.fetch_supplier_quotes()
    inventory = await wms_client.fetch_inventory_snapshots()
    feedbacks = await crm_client.fetch_customer_feedbacks()
    profit_facts = await fms_client.fetch_profit_facts()

    assert len(orders) == 2
    assert orders[0]["order_id"] == "ORD-ERP-001"
    assert quotes[0]["supplier_code"] == "SUP-ERP-001"
    assert inventory[0]["available_quantity"] == 18
    assert feedbacks[0]["customer_score"] == 4.6
    assert profit_facts[0]["gross_profit"] == 139.0

    await scm_client.push_product_plan({"items": [{"product_id": "selection-task-erp-real-001"}]})
    await wms_client.push_replenishment_plan({"items": [{"sku": "selection-task-erp-real-001", "recommended_replenishment": 24}]})
    await crm_client.push_followups({"items": [{"product_id": "selection-task-erp-real-001", "followup_type": "satisfaction-check"}]})
    await fms_client.push_profit_plan({"items": [{"product_id": "selection-task-erp-real-001", "target_profit": 99.9}]})
    await bi_client.push_dataset({"datasets": [{"dataset_name": "selection_task_metrics", "rows": [{"task_id": "selection-task-erp-real-001"}]}]})

    trigger = await paas_client.trigger_workflow(
        workflow_key="selection_workflow",
        payload={"task_id": "selection-task-erp-real-001"},
        callback={"url": "http://localhost/api/v1/integration/paas/callback", "token": None},
        callback_context={"internal_run_id": "selection-task-erp-real-001"},
    )
    status = await paas_client.get_workflow_status(trigger["run_id"])

    assert scm_outbound.exists()
    assert json.loads(scm_outbound.read_text(encoding="utf-8"))["items"][0]["product_id"] == "selection-task-erp-real-001"
    assert wms_outbound.exists()
    assert json.loads(wms_outbound.read_text(encoding="utf-8"))["items"][0]["recommended_replenishment"] == 24
    assert crm_outbound.exists()
    assert json.loads(crm_outbound.read_text(encoding="utf-8"))["items"][0]["followup_type"] == "satisfaction-check"
    assert fms_outbound.exists()
    assert json.loads(fms_outbound.read_text(encoding="utf-8"))["items"][0]["target_profit"] == 99.9
    assert bi_outbound.exists()
    assert paas_status.exists()
    assert trigger["accepted"] is True
    assert status["status"] == "running"
    assert json.loads(bi_outbound.read_text(encoding="utf-8"))["datasets"][0]["dataset_name"] == "selection_task_metrics"
    assert json.loads(paas_status.read_text(encoding="utf-8"))["run_id"] == "run-selection-task-erp-real-001"


@pytest.mark.asyncio
async def test_execute_selection_adoption_creates_real_purchase_suggestion():
    scm_outbound = Path("artifacts/erp_local/scm/outbound-product-plan.json")
    wms_outbound = Path("artifacts/erp_local/wms/outbound-replenishment.json")
    oms_outbound = Path("artifacts/erp_local/oms/outbound-products.json")
    som_outbound = Path("artifacts/erp_local/som/listing-draft.json")
    pdm_inbound = Path("artifacts/erp_local/pdm/recommendations.json")
    pdm_outbound = Path("artifacts/erp_local/pdm/recommendation-submission.json")
    pdm_inbound.parent.mkdir(parents=True, exist_ok=True)
    pdm_inbound.write_text('{"items": []}', encoding="utf-8")
    for path in [scm_outbound, wms_outbound, oms_outbound, som_outbound, pdm_outbound]:
        if path.exists():
            path.unlink()

    service = ErpIntegrationService(
        session=None,
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin"], "username": "ops-admin"},
    )
    task = SimpleNamespace(
        id="selection-task-erp-real-001",
        title="蓝牙耳机",
        target_category="electronics",
        target_market="US",
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.MEDIUM,
        config={
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "trace_id": "trace-adopt-001",
            "execution_result": {
                "decision_output": {
                    "decision": {"decision": "GO", "recommendation": "蓝牙耳机 Pro"},
                    "pricing": {"recommended_price": 39.99},
                    "product": {"name": "蓝牙耳机 Pro"},
                    "supply_chain": {"primary_supplier": "SUP-ERP-001"},
                }
            },
        },
    )

    async def _fake_get_task(task_id):
        assert task_id == "selection-task-erp-real-001"
        return task

    log_holder = SimpleNamespace(id="log-adopt-001", sync_type="export", entity_type="purchase_suggestion", status="running", items_total=0, items_success=0, items_failed=0, error_detail=None, started_at=None, finished_at=None, duration_seconds=None)

    class _Repo:
        async def create_sync_log(self, *, config_id, sync_type, entity_type):
            log_holder.sync_type = sync_type
            log_holder.entity_type = entity_type
            return log_holder

        async def update_sync_log(self, log_id, **fields):
            for key, value in fields.items():
                setattr(log_holder, key, value)
            return log_holder

        async def get_config(self, system_type, name="default"):
            system_key = getattr(system_type, "value", str(system_type))
            if system_key == "scm" and name == "default":
                return SimpleNamespace(
                    id="cfg-scm-adopt-001",
                    name="default",
                    system_type=SimpleNamespace(value="scm"),
                    api_endpoint=f"file://{Path('artifacts/erp_local/scm').resolve().as_posix()}",
                    api_key=None,
                    extra_config={"inbound_path": "/quotes.json", "outbound_path": "/outbound-product-plan.json", "timeout_seconds": 5},
                    last_sync_at=None,
                )
            if system_key == "wms" and name == "default":
                return SimpleNamespace(
                    id="cfg-wms-adopt-001",
                    name="default",
                    system_type=SimpleNamespace(value="wms"),
                    api_endpoint=f"file://{Path('artifacts/erp_local/wms').resolve().as_posix()}",
                    api_key=None,
                    extra_config={"inbound_path": "/inventory.json", "outbound_path": "/outbound-replenishment.json", "timeout_seconds": 5},
                    last_sync_at=None,
                )
            if system_key == "oms" and name == "default":
                return SimpleNamespace(
                    id="cfg-oms-adopt-001",
                    name="default",
                    system_type=SimpleNamespace(value="oms"),
                    api_endpoint=f"file://{Path('artifacts/erp_local/oms').resolve().as_posix()}",
                    api_key=None,
                    extra_config={"inbound_path": "/orders.json", "outbound_path": "/outbound-products.json", "timeout_seconds": 5},
                    last_sync_at=None,
                )
            if system_key == "som" and name == "default":
                return SimpleNamespace(
                    id="cfg-som-adopt-001",
                    name="default",
                    system_type=SimpleNamespace(value="som"),
                    api_endpoint=f"file://{Path('artifacts/erp_local/som').resolve().as_posix()}",
                    api_key=None,
                    extra_config={"inbound_path": "/listings.json", "outbound_path": "/listing-draft.json", "timeout_seconds": 5},
                    last_sync_at=None,
                )
            if system_key == "pdm" and name == "default":
                return SimpleNamespace(
                    id="cfg-pdm-adopt-001",
                    name="default",
                    system_type=SimpleNamespace(value="pdm"),
                    api_endpoint=f"file://{Path('artifacts/erp_local/pdm').resolve().as_posix()}",
                    api_key=None,
                    extra_config={"inbound_path": "/recommendations.json", "outbound_path": "/recommendation-submission.json", "timeout_seconds": 5},
                    last_sync_at=None,
                )
            return None

    async def _fake_flush():
        return None

    service.selection_repo = SimpleNamespace(get_task=_fake_get_task)
    service.repo = _Repo()
    service.session = SimpleNamespace(flush=_fake_flush)

    result = await service.execute_selection_adoption(task_id="selection-task-erp-real-001", scm_name="default", quantity=240, notes="转采购建议")

    assert result["status"] == "completed"
    assert result["pdm_receipt"]["recommendation_id"] == "REC-selection-task-erp-real-001"
    assert result["pdm_receipt"]["owner_domain"] == "pdm"
    assert result["purchase_suggestion"]["supplier_code"] == "SUP-ERP-001"
    assert result["purchase_suggestion"]["quantity"] == 240
    assert result["purchase_suggestion"]["unit_price"] == 28.6
    assert result["purchase_suggestion"]["total_amount"] == 6864.0
    assert result["scm_receipt"]["purchase_order_id"] == "PO-selection-task-erp-real-001"
    assert result["scm_receipt"]["owner_domain"] == "scm"
    assert result["scm_receipt"]["write_object"] == "recommendation"
    assert result["wms_reservation"]["reservation_id"] == "RSV-selection-task-erp-real-001"
    assert result["wms_reservation"]["owner_domain"] == "wms"
    assert result["wms_reservation"]["write_object"] == "recommendation"
    assert result["som_listing_draft"]["listing_draft_id"] == "LST-selection-task-erp-real-001"
    assert result["som_listing_draft"]["status"] == "pending_approval"
    assert result["som_listing_draft"]["owner_domain"] == "som"
    assert result["som_listing_draft"]["write_object"] == "draft"
    assert task.config["adoption"]["status"] == "executed"
    assert task.config["adoption"]["quantity"] == 240
    assert task.config["adoption"]["supplier_code"] == "SUP-ERP-001"
    assert task.config["adoption"]["execution_status"]["pdm"]["status"] == "submitted"
    assert task.config["adoption"]["execution_status"]["pdm"]["owner_domain"] == "pdm"
    assert task.config["adoption"]["execution_status"]["scm"]["status"] == "pending_review"
    assert task.config["adoption"]["execution_status"]["wms"]["status"] == "reserved"
    assert task.config["adoption"]["execution_status"]["som"]["status"] == "pending_approval"
    assert task.config["adoption"]["execution_status"]["oms"]["status"] == "read_only_feedback"
    assert pdm_outbound.exists()
    assert scm_outbound.exists()
    assert wms_outbound.exists()
    assert som_outbound.exists()
    assert not oms_outbound.exists()
    pdm_payload = json.loads(pdm_outbound.read_text(encoding="utf-8"))
    assert pdm_payload["owner_domain"] == "pdm"
    assert pdm_payload["write_object"] == "recommendation"
    assert pdm_payload["product_name"] == "蓝牙耳机 Pro"
    assert pdm_payload["audit_context"]["tenant_id"] == "86d1f796-7c55-57a1-ac77-2e952a2111ca"
    assert pdm_payload["audit_context"]["purpose"] == "submit_selection_recommendation"
    outbound_payload = json.loads(scm_outbound.read_text(encoding="utf-8"))
    assert outbound_payload["supplier_code"] == "SUP-ERP-001"
    assert outbound_payload["quantity"] == 240
    assert outbound_payload["product_name"] == "蓝牙耳机 Pro"
    assert outbound_payload["owner_domain"] == "scm"
    assert outbound_payload["write_object"] == "recommendation"
    assert outbound_payload["audit_context"]["tenant_id"] == "86d1f796-7c55-57a1-ac77-2e952a2111ca"
    assert outbound_payload["audit_context"]["purpose"] == "submit_purchase_recommendation"
    wms_payload = json.loads(wms_outbound.read_text(encoding="utf-8"))
    assert wms_payload["quantity"] == 240
    assert wms_payload["status"] == "reserved"
    assert wms_payload["owner_domain"] == "wms"
    assert wms_payload["write_object"] == "recommendation"
    assert wms_payload["audit_context"]["tenant_id"] == "86d1f796-7c55-57a1-ac77-2e952a2111ca"
    assert wms_payload["audit_context"]["purpose"] == "submit_capacity_suggestion"
    som_payload = json.loads(som_outbound.read_text(encoding="utf-8"))
    assert som_payload["title"] == "蓝牙耳机 Pro"
    assert som_payload["status"] == "pending_approval"
    assert som_payload["owner_domain"] == "som"
    assert som_payload["write_object"] == "draft"
    assert som_payload["audit_context"]["tenant_id"] == "86d1f796-7c55-57a1-ac77-2e952a2111ca"
    assert som_payload["audit_context"]["purpose"] == "submit_listing_draft"
    assert "listing_id" not in som_payload
    assert "published_at" not in som_payload


@pytest.mark.asyncio
async def test_execute_selection_adoption_over_http_mock_service():
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "scripts/mock_services.py", "--external-api", "--external-api-port", str(port)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.0)
    try:
        service = ErpIntegrationService(
            session=None,
            tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
            actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin"], "username": "ops-admin"},
        )
        task = SimpleNamespace(
            id="selection-task-http-001",
            title="蓝牙耳机",
            target_category="electronics",
            target_market="US",
            status=TaskStatus.COMPLETED,
            priority=TaskPriority.MEDIUM,
            config={
                "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
                "trace_id": "trace-adopt-http-001",
                "execution_result": {
                    "decision_output": {
                        "decision": {"decision": "GO", "recommendation": "蓝牙耳机 Pro"},
                        "pricing": {"recommended_price": 39.99},
                        "product": {"name": "蓝牙耳机 Pro", "core_features": ["ANC", "长续航"]},
                        "supply_chain": {"primary_supplier": "SUP-HTTP-001"},
                    }
                },
            },
        )

        async def _fake_get_task(task_id):
            assert task_id == "selection-task-http-001"
            return task

        class _Repo:
            def __init__(self):
                self.logs: dict[str, SimpleNamespace] = {}

            async def create_sync_log(self, *, config_id, sync_type, entity_type):
                log = SimpleNamespace(id=f"log-{entity_type}", sync_type=sync_type, entity_type=entity_type, status="running", items_total=0, items_success=0, items_failed=0, error_detail=None, started_at=None, finished_at=None, duration_seconds=None)
                self.logs[str(log.id)] = log
                return log

            async def update_sync_log(self, log_id, **fields):
                log = self.logs[str(log_id)]
                for key, value in fields.items():
                    setattr(log, key, value)
                return log

            async def get_config(self, system_type, name="default"):
                system_key = getattr(system_type, "value", str(system_type))
                endpoint = f"http://127.0.0.1:{port}"
                if system_key == "scm":
                    return SimpleNamespace(id="cfg-scm-http-001", name=name, system_type=SimpleNamespace(value="scm"), api_endpoint=endpoint, api_key="demo-key", extra_config={"inbound_path": "/supplier-products", "outbound_path": "/product-plans/bulk-upsert", "timeout_seconds": 5}, last_sync_at=None)
                if system_key == "wms":
                    return SimpleNamespace(id="cfg-wms-http-001", name=name, system_type=SimpleNamespace(value="wms"), api_endpoint=endpoint, api_key="demo-key", extra_config={"inbound_path": "/products", "outbound_path": "/replenishment-plans/bulk-upsert", "timeout_seconds": 5}, last_sync_at=None)
                if system_key == "oms":
                    return SimpleNamespace(id="cfg-oms-http-001", name=name, system_type=SimpleNamespace(value="oms"), api_endpoint=endpoint, api_key="demo-key", extra_config={"inbound_path": "/products", "outbound_path": "/products/bulk-upsert", "timeout_seconds": 5}, last_sync_at=None)
                if system_key == "som":
                    return SimpleNamespace(id="cfg-som-http-001", name=name, system_type=SimpleNamespace(value="som"), api_endpoint=endpoint, api_key="demo-key", extra_config={"inbound_path": "/products", "outbound_path": "/products/bulk-upsert", "timeout_seconds": 5}, last_sync_at=None)
                if system_key == "pdm":
                    return SimpleNamespace(id="cfg-pdm-http-001", name=name, system_type=SimpleNamespace(value="pdm"), api_endpoint=endpoint, api_key="demo-key", extra_config={"inbound_path": "/products", "outbound_path": "/recommendations", "timeout_seconds": 5}, last_sync_at=None)
                return None

        async def _fake_flush():
            return None

        service.selection_repo = SimpleNamespace(get_task=_fake_get_task)
        service.repo = _Repo()
        service.session = SimpleNamespace(flush=_fake_flush)

        result = await service.execute_selection_adoption(
            task_id="selection-task-http-001",
            scm_name="default",
            wms_name="default",
            oms_name="default",
            quantity=180,
            notes="HTTP联调",
        )

        assert result["status"] == "completed"
        assert result["pdm_receipt"]["recommendation_id"] == "REC-selection-task-http-001"
        assert result["pdm_receipt"]["status"] == "submitted"
        assert result["scm_receipt"]["purchase_order_id"] == "PO-selection-task-http-001"
        assert result["wms_reservation"]["reservation_id"] == "RSV-selection-task-http-001"
        assert result["som_listing_draft"]["listing_draft_id"] == "LST-selection-task-http-001"
        assert result["som_listing_draft"]["status"] == "pending_approval"
        assert result["som_listing_draft"]["write_object"] == "draft"
        assert result["adoption"]["execution_status"]["pdm"]["status"] == "submitted"
        assert result["adoption"]["execution_status"]["scm"]["status"] == "pending_review"
        assert result["adoption"]["execution_status"]["wms"]["status"] == "reserved"
        assert result["adoption"]["execution_status"]["som"]["status"] == "pending_approval"
        assert result["adoption"]["execution_status"]["oms"]["status"] == "read_only_feedback"
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.asyncio
async def test_sync_selection_execution_feedback_with_real_artifacts():
    service = ErpIntegrationService(
        session=None,
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin"], "username": "ops-admin"},
    )
    task_uuid = uuid.uuid4()
    task = SimpleNamespace(
        id=task_uuid,
        title="蓝牙耳机企业联调样本",
        target_category="electronics",
        target_market="US",
        budget_max=1000.0,
        created_at=None,
        updated_at=None,
        completed_at=None,
        result_summary="执行完成",
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.MEDIUM,
        config={
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "trace_id": "trace-feedback-sync-001",
            "adoption": {
                "status": "executed",
                "quantity": 240,
                "supplier_code": "SUP-ERP-001",
                "purchase_order_id": f"PO-{task_uuid}",
                "purchase_suggestion": {
                    "task_id": str(task_uuid),
                    "sku": str(task_uuid),
                    "asin": "B0ERP0001",
                },
                "warehouse_reservation": {
                    "reservation_id": f"RSV-{task_uuid}",
                    "sku": str(task_uuid),
                },
                "listing_draft": {
                    "listing_draft_id": f"LST-{task_uuid}",
                    "sku": str(task_uuid),
                },
            },
            "execution_result": {
                "decision_output": {
                    "decision": {"decision": "GO", "recommendation": "蓝牙耳机企业联调样本"},
                    "pricing": {"recommended_price": 99.9},
                    "profitability": {"expected_margin": 28.5},
                    "risks": [],
                    "recommendation_reasons": ["趋势上升"],
                }
            },
        },
    )

    async def _fake_get_task(task_id):
        assert str(task_id) == str(task_uuid)
        return task

    async def _fake_flush():
        return None

    class _DummySession:
        async def flush(self):
            return None

        async def commit(self):
            return None

        async def refresh(self, _obj):
            return None

    class _Repo:
        async def get_config(self, system_type, name="default"):
            system_key = getattr(system_type, "value", str(system_type))
            if system_key == "oms":
                return SimpleNamespace(id="cfg-oms-feedback-001", name=name, system_type=SimpleNamespace(value="oms"), api_endpoint=f"file://{Path('artifacts/erp_local/oms').resolve().as_posix()}", api_key=None, extra_config={"inbound_path": "/orders.json", "outbound_path": "/outbound-products.json", "timeout_seconds": 5}, last_sync_at=None)
            if system_key == "crm":
                return SimpleNamespace(id="cfg-crm-feedback-001", name=name, system_type=SimpleNamespace(value="crm"), api_endpoint=f"file://{Path('artifacts/erp_local/crm').resolve().as_posix()}", api_key=None, extra_config={"inbound_path": "/feedback.json", "outbound_path": "/outbound-followups.json", "timeout_seconds": 5}, last_sync_at=None)
            if system_key == "fms":
                return SimpleNamespace(id="cfg-fms-feedback-001", name=name, system_type=SimpleNamespace(value="fms"), api_endpoint=f"file://{Path('artifacts/erp_local/fms').resolve().as_posix()}", api_key=None, extra_config={"inbound_path": "/profit.json", "outbound_path": "/outbound-profit-plan.json", "timeout_seconds": 5}, last_sync_at=None)
            if system_key == "wms":
                return SimpleNamespace(id="cfg-wms-feedback-001", name=name, system_type=SimpleNamespace(value="wms"), api_endpoint=f"file://{Path('artifacts/erp_local/wms').resolve().as_posix()}", api_key=None, extra_config={"inbound_path": "/inventory.json", "outbound_path": "/outbound-replenishment.json", "timeout_seconds": 5}, last_sync_at=None)
            return None

    service.selection_repo = SimpleNamespace(get_task=_fake_get_task)
    service.repo = _Repo()
    service.session = _DummySession()

    result = await service.sync_selection_execution_feedback(task_id=str(task_uuid))

    assert result["execution_feedback_snapshot"]["sales"]["orders"]["orders"] == 2
    assert result["execution_feedback_snapshot"]["sales"]["orders"]["units"] == 12
    assert result["execution_feedback_snapshot"]["reviews"]["avg_rating"] == 4.6
    assert result["execution_feedback_snapshot"]["profit"]["gross_profit_total"] == 139.0
    assert result["execution_feedback_snapshot"]["inventory"]["summary"]["available_quantity_total"] == 18
    assert result["rescore_result"]["rescore_summary"]["decision"] == "GO"
    assert result["feature_asset"]["asset_type"] == "feedback_feature_asset"
    assert task.config["adoption"]["feedback_sync"]["status"] == "synced"


@pytest.mark.asyncio
async def test_ingest_selection_review_cases_with_real_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.local_knowledge_service._DB_PATH", tmp_path / "local_review_case.db")

    service = ErpIntegrationService(
        session=None,
        tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
        actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin"], "username": "ops-admin"},
    )
    task_uuid = uuid.uuid4()
    task = SimpleNamespace(
        id=task_uuid,
        title="蓝牙耳机企业联调样本",
        target_category="electronics",
        target_market="US",
        budget_max=1000.0,
        created_at=None,
        updated_at=None,
        completed_at=None,
        result_summary="执行完成",
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.MEDIUM,
        config={
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "adoption": {
                "status": "executed",
                "purchase_suggestion": {"task_id": str(task_uuid), "sku": str(task_uuid), "asin": "B0ERP0001"},
                "warehouse_reservation": {"reservation_id": f"RSV-{task_uuid}", "sku": str(task_uuid)},
                "listing_draft": {"listing_draft_id": f"LST-{task_uuid}", "sku": str(task_uuid), "asin": "B0ERP0001"},
            },
        },
    )

    async def _fake_get_task(task_id):
        assert str(task_id) == str(task_uuid)
        return task

    class _Repo:
        async def get_config(self, system_type, name="default"):
            system_key = getattr(system_type, "value", str(system_type))
            if system_key == "crm":
                return SimpleNamespace(id="cfg-crm-review-001", name=name, system_type=SimpleNamespace(value="crm"), api_endpoint=f"file://{Path('artifacts/erp_local/crm').resolve().as_posix()}", api_key=None, extra_config={"inbound_path": "/feedback.json", "outbound_path": "/outbound-followups.json", "timeout_seconds": 5}, last_sync_at=None)
            return None

    service.selection_repo = SimpleNamespace(get_task=_fake_get_task)
    service.repo = _Repo()

    result = await service.ingest_selection_review_cases(task_id=str(task_uuid), publish_events=False)

    assert result["case_type"] == "crm_review_case"
    assert result["matched_review_count"] == 1
    assert len(result["ingested_cases"]) == 1
    assert result["ingested_cases"][0]["case_type"] == "crm_review_case"
    assert result["ingested_cases"][0]["vector_sync"]["is_incremental"] is True
    assert result["ingested_cases"][0]["vector_sync"]["chunk_count"] >= 1
    assert task.config["review_case_ingest"]["status"] == "completed"
