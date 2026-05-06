from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.core.pms_governance import PermissionContext, validate_pms_write_boundary, validate_pms_write_object
from src.infrastructure.bi_client import BIClient, BIClientError
from src.infrastructure.crm_client import CRMClient, CRMClientError
from src.infrastructure.fms_client import FMSClient, FMSClientError
from src.infrastructure.oms_client import OMSClient, OMSClientError
from src.infrastructure.paas_client import PaaSClient, PaaSClientError
from src.infrastructure.pdm_client import PDMClient, PDMClientError
from src.infrastructure.scm_client import SCMClient, SCMClientError
from src.infrastructure.som_client import SOMClient, SOMClientError
from src.infrastructure.wms_client import WMSClient, WMSClientError
from src.models.enums import ERPSystemType
from src.repositories.erp_repository import ErpIntegrationRepository
from src.repositories.selection_repository import SelectionTaskRepository
from src.services.data_sync_service import DataSyncService
from src.services.knowledge_service import KnowledgeService
from src.services.local_knowledge_service import LocalKnowledgeService
from src.services.selection_service import SelectionTaskService

logger = get_logger(__name__)


class ErpIntegrationService:
    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.repo = ErpIntegrationRepository(session, tenant_id=self.tenant_id) if session is not None else None
        self.selection_repo = SelectionTaskRepository(session, tenant_id=self.tenant_id) if session is not None else None

    async def save_oms_config(
        self,
        *,
        name: str,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None,
        inbound_path: str,
        outbound_path: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return self._serialize_config(
            await self.repo.create_or_update_config(
                system_type=ERPSystemType.OMS,
                name=name,
                api_endpoint=api_endpoint,
                api_key=api_key,
                secret_key=secret_key,
                extra_config={
                    "tenant_id": self.tenant_id,
                    "inbound_path": inbound_path,
                    "outbound_path": outbound_path,
                    "timeout_seconds": timeout_seconds,
                    "sync_direction": "bidirectional",
                    "entity_type": "product",
                    "owner_system": "oms",
                },
            )
        )

    async def save_som_config(
        self,
        *,
        name: str,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None,
        inbound_path: str,
        outbound_path: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return self._serialize_config(
            await self.repo.create_or_update_config(
                system_type=ERPSystemType.SOM,
                name=name,
                api_endpoint=api_endpoint,
                api_key=api_key,
                secret_key=secret_key,
                extra_config={
                    "tenant_id": self.tenant_id,
                    "inbound_path": inbound_path,
                    "outbound_path": outbound_path,
                    "timeout_seconds": timeout_seconds,
                    "sync_direction": "outbound-only",
                    "entity_type": "listing_draft",
                    "owner_system": "som",
                },
            )
        )

    async def save_pdm_config(
        self,
        *,
        name: str,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None,
        inbound_path: str,
        outbound_path: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return self._serialize_config(
            await self.repo.create_or_update_config(
                system_type=ERPSystemType.PDM,
                name=name,
                api_endpoint=api_endpoint,
                api_key=api_key,
                secret_key=secret_key,
                extra_config={
                    "tenant_id": self.tenant_id,
                    "inbound_path": inbound_path,
                    "outbound_path": outbound_path,
                    "timeout_seconds": timeout_seconds,
                    "sync_direction": "outbound-only",
                    "entity_type": "selection_recommendation",
                    "owner_system": "pdm",
                },
            )
        )

    async def save_scm_config(
        self,
        *,
        name: str,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None,
        inbound_path: str,
        outbound_path: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return self._serialize_config(
            await self.repo.create_or_update_config(
                system_type=ERPSystemType.SCM,
                name=name,
                api_endpoint=api_endpoint,
                api_key=api_key,
                secret_key=secret_key,
                extra_config={
                    "tenant_id": self.tenant_id,
                    "inbound_path": inbound_path,
                    "outbound_path": outbound_path,
                    "timeout_seconds": timeout_seconds,
                    "sync_direction": "bidirectional",
                    "entity_type": "product",
                    "owner_system": "scm",
                },
            )
        )

    async def save_wms_config(
        self,
        *,
        name: str,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None,
        inbound_path: str,
        outbound_path: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return self._serialize_config(
            await self.repo.create_or_update_config(
                system_type=ERPSystemType.WMS,
                name=name,
                api_endpoint=api_endpoint,
                api_key=api_key,
                secret_key=secret_key,
                extra_config={
                    "tenant_id": self.tenant_id,
                    "inbound_path": inbound_path,
                    "outbound_path": outbound_path,
                    "timeout_seconds": timeout_seconds,
                    "sync_direction": "bidirectional",
                    "entity_type": "inventory",
                    "owner_system": "wms",
                },
            )
        )

    async def save_crm_config(
        self,
        *,
        name: str,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None,
        inbound_path: str,
        outbound_path: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return self._serialize_config(
            await self.repo.create_or_update_config(
                system_type=ERPSystemType.CRM,
                name=name,
                api_endpoint=api_endpoint,
                api_key=api_key,
                secret_key=secret_key,
                extra_config={
                    "tenant_id": self.tenant_id,
                    "inbound_path": inbound_path,
                    "outbound_path": outbound_path,
                    "timeout_seconds": timeout_seconds,
                    "sync_direction": "bidirectional",
                    "entity_type": "customer_feedback",
                    "owner_system": "crm",
                },
            )
        )

    async def save_fms_config(
        self,
        *,
        name: str,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None,
        inbound_path: str,
        outbound_path: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return self._serialize_config(
            await self.repo.create_or_update_config(
                system_type=ERPSystemType.FMS,
                name=name,
                api_endpoint=api_endpoint,
                api_key=api_key,
                secret_key=secret_key,
                extra_config={
                    "tenant_id": self.tenant_id,
                    "inbound_path": inbound_path,
                    "outbound_path": outbound_path,
                    "timeout_seconds": timeout_seconds,
                    "sync_direction": "bidirectional",
                    "entity_type": "finance_metric",
                    "owner_system": "fms",
                },
            )
        )

    async def save_bi_config(
        self,
        *,
        name: str,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None,
        health_path: str,
        dataset_path: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return self._serialize_config(
            await self.repo.create_or_update_config(
                system_type=ERPSystemType.BI,
                name=name,
                api_endpoint=api_endpoint,
                api_key=api_key,
                secret_key=secret_key,
                extra_config={
                    "tenant_id": self.tenant_id,
                    "health_path": health_path,
                    "dataset_path": dataset_path,
                    "timeout_seconds": timeout_seconds,
                    "sync_direction": "outbound-only",
                    "entity_type": "bi_dataset",
                    "owner_system": "bi",
                },
            )
        )

    async def save_paas_config(
        self,
        *,
        name: str,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None,
        health_path: str,
        trigger_path: str,
        status_path: str,
        callback_token: str | None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return self._serialize_config(
            await self.repo.create_or_update_config(
                system_type=ERPSystemType.PAAS,
                name=name,
                api_endpoint=api_endpoint,
                api_key=api_key,
                secret_key=secret_key,
                extra_config={
                    "tenant_id": self.tenant_id,
                    "health_path": health_path,
                    "trigger_path": trigger_path,
                    "status_path": status_path,
                    "callback_token": callback_token,
                    "timeout_seconds": timeout_seconds,
                    "sync_direction": "callback",
                    "entity_type": "workflow_run",
                    "owner_system": "paas",
                    "workflow_key": "selection_workflow",
                },
            )
        )

    async def test_oms_connection(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.OMS, name, "OMS 配置不存在")
        return await self._test_connection(config, self._build_oms_client(config), system_type="oms")

    async def test_scm_connection(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.SCM, name, "SCM 配置不存在")
        return await self._test_connection(config, self._build_scm_client(config), system_type="scm")

    async def test_som_connection(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.SOM, name, "SOM 配置不存在")
        return await self._test_connection(config, self._build_som_client(config), system_type="som")

    async def test_pdm_connection(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.PDM, name, "PDM 配置不存在")
        return await self._test_connection(config, self._build_pdm_client(config), system_type="pdm")

    async def test_wms_connection(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.WMS, name, "WMS 配置不存在")
        return await self._test_connection(config, self._build_wms_client(config), system_type="wms")

    async def test_crm_connection(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.CRM, name, "CRM 配置不存在")
        return await self._test_connection(config, self._build_crm_client(config), system_type="crm")

    async def test_fms_connection(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.FMS, name, "FMS 配置不存在")
        return await self._test_connection(config, self._build_fms_client(config), system_type="fms")

    async def test_bi_connection(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.BI, name, "BI 配置不存在")
        return await self._test_connection(config, self._build_bi_client(config), system_type="bi")

    async def test_paas_connection(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.PAAS, name, "PaaS 配置不存在")
        result = await self._test_connection(config, self._build_paas_client(config), system_type="paas")
        if result["status"] == "ok":
            result["next_action"] = "trigger_workflow"
        return result

    async def reset_oms_cursor(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.OMS, name, "OMS 配置不存在")
        extra = dict(config.extra_config or {})
        extra["sync_cursor"] = None
        extra["config_version"] = int(extra.get("config_version") or 0) + 1
        config.extra_config = extra
        if self.session is not None and callable(getattr(self.session, "flush", None)):
            await self.session.flush()
        return {
            "config_id": str(config.id),
            "config_name": config.name,
            "system_type": "oms",
            "sync_cursor": extra.get("sync_cursor"),
            "config_version": extra["config_version"],
        }

    async def disable_oms_config(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.OMS, name, "OMS 配置不存在")
        extra = dict(config.extra_config or {})
        extra["manual_state"] = "disabled"
        extra["config_version"] = int(extra.get("config_version") or 0) + 1
        config.extra_config = extra
        config.is_active = False
        if self.session is not None and callable(getattr(self.session, "flush", None)):
            await self.session.flush()
        return {
            "config_id": str(config.id),
            "config_name": config.name,
            "system_type": "oms",
            "manual_state": extra["manual_state"],
            "config_version": extra["config_version"],
            "is_active": bool(config.is_active),
        }

    async def sync_inbound_products(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.OMS, name, "OMS 配置不存在")
        return await self._run_import_sync(
            config=config,
            entity_type="product",
            fetcher=lambda: self._fetch_oms_products(config),
            normalizer=self._normalize_oms_product,
        )

    async def sync_outbound_products(self, name: str = "default", limit: int = 20) -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.OMS, name, "OMS 配置不存在")
        return await self._run_export_sync(
            config=config,
            entity_type="product",
            limit=limit,
            serializer=self._serialize_product,
            pusher=lambda payload: self._push_oms_products(config, payload),
        )

    async def sync_inbound_supplier_products(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.SCM, name, "SCM 配置不存在")
        return await self._run_import_sync(
            config=config,
            entity_type="product",
            fetcher=lambda: self._fetch_scm_supplier_products(config),
            normalizer=self._normalize_scm_product,
        )

    async def sync_outbound_product_plan(self, name: str = "default", limit: int = 20) -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.SCM, name, "SCM 配置不存在")
        return await self._run_export_sync(
            config=config,
            entity_type="product",
            limit=limit,
            serializer=self._serialize_product_plan,
            pusher=lambda payload: self._push_scm_product_plan(config, payload),
        )

    async def sync_inbound_inventory(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.WMS, name, "WMS 配置不存在")
        result = await self._run_import_sync(
            config=config,
            entity_type="inventory",
            fetcher=lambda: self._fetch_wms_inventory(config),
            normalizer=self._normalize_wms_inventory,
        )
        inventory_items = await self._fetch_wms_inventory(config)
        result["inventory_summary"] = self._summarize_wms_inventory(inventory_items)
        result["fulfillment_status"] = self._build_fulfillment_status(result["inventory_summary"])
        return result

    async def sync_outbound_replenishment_plan(self, name: str = "default", limit: int = 20) -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.WMS, name, "WMS 配置不存在")
        result = await self._run_export_sync(
            config=config,
            entity_type="inventory_replenishment",
            limit=limit,
            serializer=self._serialize_replenishment_plan,
            pusher=lambda payload: self._push_wms_replenishment_plan(config, payload),
        )
        products = await self.repo.list_products_for_export(limit=limit)
        replenishment_rows = [self._serialize_replenishment_plan(product) for product in products]
        result["inventory_summary"] = {
            "items": len(replenishment_rows),
            "recommended_replenishment_total": sum(int(item.get("recommended_replenishment", 0) or 0) for item in replenishment_rows),
        }
        result["fulfillment_status"] = {
            "status": "ready_for_replenishment" if replenishment_rows else "idle",
            "warehouse_count": len({item.get("warehouse_id") for item in replenishment_rows if item.get("warehouse_id")}),
            "backorder_risk": any(int(item.get("recommended_replenishment", 0) or 0) > 0 for item in replenishment_rows),
        }
        return result

    async def sync_inbound_customer_feedback(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.CRM, name, "CRM 配置不存在")
        return await self._run_import_sync(
            config=config,
            entity_type="customer_feedback",
            fetcher=lambda: self._fetch_crm_feedbacks(config),
            normalizer=self._normalize_crm_feedback,
        )

    async def sync_outbound_customer_followup(self, name: str = "default", limit: int = 20) -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.CRM, name, "CRM 配置不存在")
        return await self._run_export_sync(
            config=config,
            entity_type="customer_followup",
            limit=limit,
            serializer=self._serialize_customer_followup,
            pusher=lambda payload: self._push_crm_followups(config, payload),
        )

    async def sync_inbound_finance_metrics(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.FMS, name, "FMS 配置不存在")
        return await self._run_import_sync(
            config=config,
            entity_type="finance_metric",
            fetcher=lambda: self._fetch_fms_metrics(config),
            normalizer=self._normalize_fms_metric,
        )

    async def sync_outbound_profit_plan(self, name: str = "default", limit: int = 20) -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.FMS, name, "FMS 配置不存在")
        return await self._run_export_sync(
            config=config,
            entity_type="profit_plan",
            limit=limit,
            serializer=self._serialize_profit_plan,
            pusher=lambda payload: self._push_fms_profit_plan(config, payload),
        )

    async def execute_selection_adoption(
        self,
        *,
        task_id: str,
        scm_name: str = "default",
        wms_name: str = "default",
        oms_name: str = "default",
        som_name: str = "default",
        pdm_name: str = "default",
        quantity: int = 200,
        supplier_code: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        execution_result = config.get("execution_result") if isinstance(config, dict) else {}
        decision_output = execution_result.get("decision_output") if isinstance(execution_result, dict) else {}
        decision_meta = decision_output.get("decision") if isinstance(decision_output.get("decision"), dict) else {}
        if str(decision_meta.get("decision") or "").upper() not in {"GO", "REVIEW"}:
            raise ValueError("当前任务不满足采纳推荐条件")

        scm_config = await self._get_required_config(ERPSystemType.SCM, scm_name, "SCM 配置不存在")
        wms_config = await self._get_required_config(ERPSystemType.WMS, wms_name, "WMS 配置不存在")
        oms_config = await self._get_required_config(ERPSystemType.OMS, oms_name, "OMS 配置不存在")
        som_config = await self._get_required_config(ERPSystemType.SOM, som_name, "SOM 配置不存在")
        pdm_config = await self._get_required_config(ERPSystemType.PDM, pdm_name, "PDM 配置不存在")
        scm_log = await self.repo.create_sync_log(config_id=str(scm_config.id), sync_type="export", entity_type="purchase_suggestion")
        wms_log = await self.repo.create_sync_log(config_id=str(wms_config.id), sync_type="export", entity_type="warehouse_replenishment_suggestion")
        oms_log = await self.repo.create_sync_log(config_id=str(oms_config.id), sync_type="read", entity_type="oms_feedback_boundary")
        som_log = await self.repo.create_sync_log(config_id=str(som_config.id), sync_type="export", entity_type="listing_draft")
        pdm_log = await self.repo.create_sync_log(config_id=str(pdm_config.id), sync_type="export", entity_type="selection_recommendation")
        start = perf_counter()
        try:
            validate_pms_write_object("recommendation")
            validate_pms_write_object("draft")
            validate_pms_write_boundary("purchase", "suggest")
            validate_pms_write_boundary("inventory", "suggest")
            validate_pms_write_boundary("listing", "draft")
            validate_pms_write_boundary("product_master", "suggest")
            scm_client = self._build_scm_client(scm_config)
            wms_client = self._build_wms_client(wms_config)
            som_client = self._build_som_client(som_config)
            pdm_client = self._build_pdm_client(pdm_config)
            pdm_audit_context = self._build_write_audit_context(
                selection_task=selection_task,
                domain="pdm",
                purpose="submit_selection_recommendation",
                task_id=task_id,
            )
            scm_audit_context = self._build_write_audit_context(
                selection_task=selection_task,
                domain="scm",
                purpose="submit_purchase_recommendation",
                task_id=task_id,
            )
            wms_audit_context = self._build_write_audit_context(
                selection_task=selection_task,
                domain="wms",
                purpose="submit_capacity_suggestion",
                task_id=task_id,
            )
            som_audit_context = self._build_write_audit_context(
                selection_task=selection_task,
                domain="som",
                purpose="submit_listing_draft",
                task_id=task_id,
            )

            pdm_recommendation = self._build_pdm_recommendation_payload(
                selection_task,
                decision_output if isinstance(decision_output, dict) else {},
                notes=notes,
                audit_context=pdm_audit_context,
            )
            pdm_receipt = await pdm_client.submit_selection_recommendation(
                pdm_recommendation,
                audit_context=pdm_audit_context,
            )

            quotes = await scm_client.fetch_supplier_quotes()
            chosen_quote = self._select_supplier_quote(quotes, supplier_code=supplier_code)
            purchase_suggestion = self._build_purchase_suggestion_payload(
                selection_task,
                decision_output if isinstance(decision_output, dict) else {},
                quantity=quantity,
                supplier_code=supplier_code,
                quote=chosen_quote,
                notes=notes,
                audit_context=scm_audit_context,
            )
            scm_receipt = await scm_client.create_purchase_suggestion(
                purchase_suggestion,
                audit_context=scm_audit_context,
            )

            wms_reservation = self._build_wms_reservation_payload(
                selection_task,
                decision_output if isinstance(decision_output, dict) else {},
                quantity=quantity,
                purchase_suggestion=purchase_suggestion,
                audit_context=wms_audit_context,
            )
            wms_receipt = await wms_client.create_reservation(
                wms_reservation,
                audit_context=wms_audit_context,
            )

            som_listing_draft = self._build_som_listing_draft_payload(
                selection_task,
                decision_output if isinstance(decision_output, dict) else {},
                purchase_suggestion=purchase_suggestion,
                audit_context=som_audit_context,
            )
            som_receipt = await som_client.create_listing_draft(
                som_listing_draft,
                audit_context=som_audit_context,
            )

            now = datetime.now(UTC)
            duration_seconds = round(perf_counter() - start, 4)
            scm_config.last_sync_at = now
            wms_config.last_sync_at = now
            oms_config.last_sync_at = now
            som_config.last_sync_at = now
            pdm_config.last_sync_at = now
            await self.repo.update_sync_log(
                str(scm_log.id),
                status="completed",
                items_total=1,
                items_success=1,
                items_failed=0,
                error_detail=None,
                finished_at=now,
                duration_seconds=duration_seconds,
            )
            await self.repo.update_sync_log(
                str(wms_log.id),
                status="completed",
                items_total=1,
                items_success=1,
                items_failed=0,
                error_detail=None,
                finished_at=now,
                duration_seconds=duration_seconds,
            )
            await self.repo.update_sync_log(
                str(oms_log.id),
                status="completed",
                items_total=1,
                items_success=1,
                items_failed=0,
                error_detail=None,
                finished_at=now,
                duration_seconds=duration_seconds,
            )
            await self.repo.update_sync_log(
                str(som_log.id),
                status="completed",
                items_total=1,
                items_success=1,
                items_failed=0,
                error_detail=None,
                finished_at=now,
                duration_seconds=duration_seconds,
            )
            await self.repo.update_sync_log(
                str(pdm_log.id),
                status="completed",
                items_total=1,
                items_success=1,
                items_failed=0,
                error_detail=None,
                finished_at=now,
                duration_seconds=duration_seconds,
            )
            adoption = config.get("adoption") if isinstance(config.get("adoption"), dict) else {}
            execution_status = {
                "pdm": {
                    "config_name": pdm_name,
                    "log_id": str(pdm_log.id),
                    "recommendation_id": pdm_receipt.get("recommendation_id"),
                    "status": pdm_receipt.get("status") or "submitted",
                    "owner_domain": "pdm",
                },
                "scm": {
                    "config_name": scm_name,
                    "log_id": str(scm_log.id),
                    "purchase_order_id": scm_receipt.get("purchase_order_id"),
                    "status": scm_receipt.get("status") or "pending_review",
                },
                "wms": {
                    "config_name": wms_name,
                    "log_id": str(wms_log.id),
                    "reservation_id": wms_receipt.get("reservation_id"),
                    "location_code": wms_receipt.get("location_code"),
                    "status": wms_receipt.get("status") or "reserved",
                },
                "som": {
                    "config_name": som_name,
                    "log_id": str(som_log.id),
                    "listing_draft_id": som_receipt.get("listing_draft_id"),
                    "status": som_receipt.get("status") or "pending_approval",
                    "owner_domain": "som",
                },
                "oms": {
                    "config_name": oms_name,
                    "log_id": str(oms_log.id),
                    "status": "read_only_feedback",
                    "owner_domain": "oms",
                },
            }
            adoption.update(
                {
                    "status": "executed",
                    "scm_name": scm_name,
                    "quantity": int(quantity),
                    "supplier_code": purchase_suggestion.get("supplier_code"),
                    "supplier_name": purchase_suggestion.get("supplier_name"),
                    "unit_price": purchase_suggestion.get("unit_price"),
                    "total_amount": purchase_suggestion.get("total_amount"),
                    "pdm_recommendation": pdm_recommendation,
                    "pdm_recommendation_receipt": pdm_receipt,
                    "purchase_suggestion": purchase_suggestion,
                    "purchase_order_id": scm_receipt.get("purchase_order_id"),
                    "warehouse_reservation": wms_receipt,
                    "listing_draft": som_receipt,
                    "execution_status": execution_status,
                    "executed_at": now.isoformat(),
                    "notes": notes,
                }
            )
            config["adoption"] = adoption
            config["status_reason"] = "已采纳推荐并完成SCM/WMS/SOM建议与草稿承接，OMS仅用于订单反馈"
            selection_task.config = config
            await self.session.flush()
            detail = self._serialize_log(scm_log, scm_config)
            detail.update(
                {
                    "task_id": task_id,
                    "trace_id": config.get("trace_id") or config.get("request_id") or f"selection-adopt-{task_id}",
                    "pdm_recommendation": pdm_recommendation,
                    "pdm_receipt": pdm_receipt,
                    "purchase_suggestion": purchase_suggestion,
                    "scm_receipt": scm_receipt,
                    "wms_reservation": wms_receipt,
                    "som_listing_draft": som_receipt,
                    "execution_status": execution_status,
                    "adoption": adoption,
                    "message": "采纳推荐并完成SCM/WMS/SOM建议与草稿承接，OMS仅用于订单反馈",
                }
            )
            return detail
        except (SCMClientError, WMSClientError, OMSClientError, SOMClientError, PDMClientError) as e:
            now = datetime.now(UTC)
            duration_seconds = round(perf_counter() - start, 4)
            for current_log in [scm_log, wms_log, oms_log, som_log, pdm_log]:
                await self.repo.update_sync_log(
                    str(current_log.id),
                    status="failed",
                    items_total=1,
                    items_success=0,
                    items_failed=1,
                    error_detail=f"{e.error_code}:{e}",
                    finished_at=now,
                    duration_seconds=duration_seconds,
                )
            raise
        except Exception as e:
            now = datetime.now(UTC)
            duration_seconds = round(perf_counter() - start, 4)
            for current_log in [scm_log, wms_log, oms_log, som_log, pdm_log]:
                await self.repo.update_sync_log(
                    str(current_log.id),
                    status="failed",
                    items_total=1,
                    items_success=0,
                    items_failed=1,
                    error_detail=str(e),
                    finished_at=now,
                    duration_seconds=duration_seconds,
                )
            raise

    async def close_selection_loop(
        self,
        *,
        task_id: str,
        oms_name: str = "default",
        scm_name: str = "default",
        wms_name: str = "default",
        crm_name: str = "default",
        fms_name: str = "default",
        paas_name: str = "default",
        limit: int = 20,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)

        config = selection_task.config or {}
        execution_result = config.get("execution_result") if isinstance(config, dict) else {}
        decision_output = execution_result.get("decision_output") if isinstance(execution_result, dict) else {}
        product_draft = {
            "task_id": task_id,
            "query": selection_task.title,
            "category": selection_task.target_category,
            "target_market": selection_task.target_market,
            "decision": (decision_output.get("decision") or {}).get("decision") if isinstance(decision_output, dict) else None,
            "recommended_price": (decision_output.get("pricing") or {}).get("recommended_price") if isinstance(decision_output, dict) else None,
            "supplier_hint": ((decision_output.get("supply_chain") or {}).get("primary_supplier")) if isinstance(decision_output, dict) else None,
        }

        scm_result = await self.sync_outbound_product_plan(name=scm_name, limit=limit)
        wms_result = await self.sync_outbound_replenishment_plan(name=wms_name, limit=limit)
        oms_result = await self.sync_outbound_products(name=oms_name, limit=limit)
        fms_result = await self.sync_outbound_profit_plan(name=fms_name, limit=limit)

        route_status = {
            "selection_to_scm": scm_result.get("status") == "completed",
            "scm_to_wms": wms_result.get("status") == "completed",
            "wms_to_oms": oms_result.get("status") == "completed",
            "oms_to_fms": fms_result.get("status") == "completed",
        }
        systems: dict[str, Any] = {
            "scm": scm_result,
            "wms": wms_result,
            "oms": oms_result,
            "fms": fms_result,
        }
        steps = ["selection", "scm", "wms", "oms", "fms"]

        if self.repo is not None:
            bi_config = await self.repo.get_config(ERPSystemType.BI, name="default")
            paas_config = await self.repo.get_config(ERPSystemType.PAAS, name=paas_name)
            if bi_config is not None:
                bi_result = await self.sync_outbound_bi_assets(name="default")
                route_status["fms_to_bi"] = bi_result.get("status") == "completed"
                systems["bi"] = bi_result
                steps.append("bi")
                if paas_config is not None:
                    paas_result = await self.trigger_paas_workflow(
                        name=paas_name,
                        workflow_key="selection_workflow",
                        trigger_payload={
                            "task_id": task_id,
                            "trace_id": config.get("trace_id") or config.get("request_id") or f"selection-close-loop-{task_id}",
                        },
                        callback_url="http://localhost/api/v1/integration/paas/callback",
                    )
                    route_status["bi_to_paas"] = bool(paas_result.get("accepted", True))
                    systems["paas"] = paas_result
                    steps.append("paas")

        close_loop_completed = all(route_status.values())

        feedback_loop: dict[str, Any] = {
            "auto_rescore_completed": False,
            "feature_asset_ready": False,
            "rescore_summary": None,
            "feature_asset": None,
            "rescore_inputs": None,
        }
        if close_loop_completed:
            feedback_loop = await self._build_close_loop_feedback_loop(
                task_id=task_id,
                oms_name=oms_name,
                wms_name=wms_name,
                fms_name=fms_name,
                crm_name=crm_name,
            )

        return {
            "task_id": task_id,
            "trace_id": config.get("trace_id") or config.get("request_id") or f"selection-close-loop-{task_id}",
            "product_draft": product_draft,
            "route_status": route_status,
            "systems": systems,
            "feedback_loop": feedback_loop,
            "summary": {
                "close_loop_completed": close_loop_completed,
                "steps": steps,
            },
        }

    async def _get_selection_task(self, task_id: str) -> Any:
        if self.selection_repo is None:
            raise ValueError("选品任务仓储未初始化")
        try:
            normalized_task_id: Any = UUID(str(task_id))
        except ValueError:
            normalized_task_id = task_id
        get_task = self.selection_repo.get_task
        try:
            parameter_count = len(inspect.signature(get_task).parameters)
        except (TypeError, ValueError):
            parameter_count = 1
        if parameter_count == 0:
            task = await type(self.selection_repo).get_task(normalized_task_id)
        else:
            task = await get_task(normalized_task_id)
        if task is None:
            raise ValueError(f"选品任务不存在: {task_id}")
        return task

    async def _build_close_loop_feedback_loop(
        self,
        *,
        task_id: str,
        oms_name: str,
        wms_name: str,
        fms_name: str,
        crm_name: str = "default",
    ) -> dict[str, Any]:
        oms_status = await self.get_oms_operational_status(name=oms_name)
        wms_status = await self.get_wms_operational_status(name=wms_name)
        fms_status = await self.get_fms_operational_status(name=fms_name)
        crm_status = await self.get_crm_operational_status(name=crm_name)

        sales_summary = oms_status.get("sales_summary") or {}
        inventory_summary = wms_status.get("inventory_summary") or {}
        fulfillment_status = wms_status.get("fulfillment_status") or {}
        profit_summary = fms_status.get("profit_summary") or {}
        feedback_summary = crm_status.get("feedback_summary") or {}
        complaint_count = int(feedback_summary.get("complaint_count") or 0)

        rescore_inputs = {
            "sales_7d": int(sales_summary.get("items") or 0),
            "review_rating": feedback_summary.get("avg_rating"),
            "review_count": int(feedback_summary.get("review_count") or 0),
            "gross_profit": float(profit_summary.get("gross_profit_total") or 0.0),
            "margin_rate": profit_summary.get("avg_margin_rate"),
            "available_inventory": int(inventory_summary.get("available_quantity_total") or 0),
            "stockout_risk": bool(fulfillment_status.get("backorder_risk", False) or complaint_count > 0),
            "source": "close_loop_auto",
            "notes": "由 close_selection_loop 基于 OMS/WMS/CRM/FMS 经营信号自动回流",
        }

        selection_service = SelectionTaskService(self.session, tenant_id=self.tenant_id, actor=self.actor)
        rescore_result = await selection_service.rescore_task_from_execution_feedback(task_id, rescore_inputs)
        feature_asset = await selection_service.export_feedback_feature_asset(task_id)

        return {
            "auto_rescore_completed": rescore_result is not None,
            "feature_asset_ready": feature_asset is not None,
            "rescore_summary": rescore_result.get("rescore_summary") if isinstance(rescore_result, dict) else None,
            "feature_asset": feature_asset.get("feature_asset") if isinstance(feature_asset, dict) else None,
            "rescore_inputs": rescore_inputs,
        }

    async def sync_outbound_bi_assets(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.BI, name, "BI 配置不存在")
        log = await self.repo.create_sync_log(config_id=str(config.id), sync_type="export", entity_type="bi_dataset")
        start = perf_counter()
        try:
            datasets = await self._build_bi_datasets()
            payload = {
                "tenant_id": self.tenant_id,
                "datasets": datasets,
                "exported_at": datetime.now(UTC).isoformat(),
            }
            await self._push_bi_datasets(config, payload)
            now = datetime.now(UTC)
            config.last_sync_at = now
            await self.repo.update_sync_log(
                str(log.id),
                status="completed",
                items_total=len(datasets),
                items_success=len(datasets),
                items_failed=0,
                error_detail=None,
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            detail = self._serialize_log(log, config)
            detail.update({
                "error_code": None,
                "retryable": False,
                "next_action": "monitor",
                "datasets": [item["dataset_name"] for item in datasets],
            })
            return detail
        except BIClientError as e:
            now = datetime.now(UTC)
            await self.repo.update_sync_log(
                str(log.id),
                status="failed",
                items_total=0,
                items_success=0,
                items_failed=0,
                error_detail=f"{e.error_code}:{e}",
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            raise
        except Exception as e:
            now = datetime.now(UTC)
            await self.repo.update_sync_log(
                str(log.id),
                status="failed",
                items_total=0,
                items_success=0,
                items_failed=0,
                error_detail=str(e),
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            raise

    async def trigger_paas_workflow(
        self,
        *,
        name: str = "default",
        workflow_key: str,
        trigger_payload: dict[str, Any],
        callback_url: str,
    ) -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.PAAS, name, "PaaS 配置不存在")
        log = await self.repo.create_sync_log(config_id=str(config.id), sync_type="export", entity_type="workflow_run")
        start = perf_counter()
        internal_run_id = str(log.id)
        try:
            callback = {
                "url": callback_url,
                "token": (config.extra_config or {}).get("callback_token"),
            }
            result = await self._build_paas_client(config).trigger_workflow(
                workflow_key=workflow_key,
                payload=trigger_payload,
                callback=callback,
                callback_context={
                    "tenant_id": self.tenant_id,
                    "config_name": config.name,
                    "workflow_key": workflow_key,
                    "internal_run_id": internal_run_id,
                },
            )
            now = datetime.now(UTC)
            config.last_sync_at = now
            await self.repo.update_sync_log(
                str(log.id),
                status=result.get("status", "dispatched"),
                items_total=1,
                items_success=1,
                items_failed=0,
                error_detail=None,
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            detail = self._serialize_log(log, config)
            detail.update({
                "run_id": result["run_id"],
                "workflow_key": workflow_key,
                "accepted": result.get("accepted", True),
                "callback_url": callback_url,
                "callback_registered": True,
                "callback_token_required": bool((config.extra_config or {}).get("callback_token")),
                "next_action": "await_callback",
            })
            return detail
        except PaaSClientError as e:
            now = datetime.now(UTC)
            await self.repo.update_sync_log(
                str(log.id),
                status="failed",
                items_total=1,
                items_success=0,
                items_failed=1,
                error_detail=f"{e.error_code}:{e}",
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            raise
        except Exception as e:
            now = datetime.now(UTC)
            await self.repo.update_sync_log(
                str(log.id),
                status="failed",
                items_total=1,
                items_success=0,
                items_failed=1,
                error_detail=str(e),
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            raise

    async def update_paas_callback(self, *, run_id: str, status: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
        log, config = await self.repo.get_sync_log_with_config(run_id)
        if log is None or config is None:
            raise ValueError("PaaS 运行日志不存在")
        now = datetime.now(UTC)
        serialized_result = result or {}
        await self.repo.update_sync_log(
            str(log.id),
            status=status,
            items_total=1,
            items_success=1 if status in {"completed", "success"} else 0,
            items_failed=0 if status in {"completed", "success"} else 1,
            error_detail=None if status in {"completed", "success"} else serialized_result.get("error_detail"),
            finished_at=now,
        )
        detail = self._serialize_log(log, config)
        detail.update({
            "run_id": str(log.id),
            "callback_received": True,
            "callback_verified": True,
            "result": serialized_result,
        })
        return detail

    async def get_paas_run_status(self, *, name: str = "default", run_id: str) -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.PAAS, name, "PaaS 配置不存在")
        external_status = await self._build_paas_client(config).get_workflow_status(run_id)
        log, _ = await self.repo.get_sync_log_with_config(run_id)
        return {
            "run_id": run_id,
            "config_name": config.name,
            "system_type": "paas",
            "status": external_status["status"],
            "external_result": external_status.get("result"),
            "log_status": log.status if log is not None else None,
            "callback_expected": True,
            "retry_recommended": external_status["status"] not in {"completed", "success"},
        }

    async def retry_sync_log(self, log_id: str) -> dict[str, Any]:
        log, config = await self.repo.get_sync_log_with_config(log_id)
        if log is None or config is None:
            raise ValueError("同步日志不存在")
        system_type = config.system_type.value if hasattr(config.system_type, "value") else str(config.system_type)
        if system_type == "oms":
            result = await (self.sync_inbound_products(config.name) if log.sync_type == "import" else self.sync_outbound_products(config.name))
        elif system_type == "scm":
            result = await (self.sync_inbound_supplier_products(config.name) if log.sync_type == "import" else self.sync_outbound_product_plan(config.name))
        elif system_type == "wms":
            result = await (self.sync_inbound_inventory(config.name) if log.sync_type == "import" else self.sync_outbound_replenishment_plan(config.name))
        elif system_type == "crm":
            result = await (self.sync_inbound_customer_feedback(config.name) if log.sync_type == "import" else self.sync_outbound_customer_followup(config.name))
        elif system_type == "fms":
            result = await (self.sync_inbound_finance_metrics(config.name) if log.sync_type == "import" else self.sync_outbound_profit_plan(config.name))
        elif system_type == "bi":
            result = await self.sync_outbound_bi_assets(config.name)
        elif system_type == "paas":
            workflow_key = (config.extra_config or {}).get("workflow_key", "selection_workflow")
            callback_url = (config.extra_config or {}).get("callback_url", "http://localhost/api/v1/integration/paas/callback")
            result = await self.trigger_paas_workflow(
                name=config.name,
                workflow_key=workflow_key,
                trigger_payload={"retry_of": log_id},
                callback_url=callback_url,
            )
        else:
            raise ValueError(f"不支持的系统类型: {system_type}")
        result["retry_of"] = log_id
        return result

    async def list_oms_logs(self, limit: int = 20) -> dict[str, Any]:
        return await self._list_logs(ERPSystemType.OMS, limit)

    async def get_oms_operational_status(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.OMS, name, "OMS 配置不存在")
        client = self._build_oms_client(config)
        orders = await self._call_with_permission_context(client.fetch_orders)
        sales_metrics = await self._call_with_permission_context(client.fetch_sales_metrics)
        order_summary = self._summarize_oms_orders(orders)
        sales_summary = self._summarize_oms_sales_metrics(sales_metrics)
        return {
            "config_name": name,
            "system_type": "oms",
            "order_summary": order_summary,
            "sales_summary": sales_summary,
            "result_writeback_ready": order_summary["orders"] > 0 or sales_summary["items"] > 0,
        }

    async def list_scm_logs(self, limit: int = 20) -> dict[str, Any]:
        return await self._list_logs(ERPSystemType.SCM, limit)

    async def get_scm_operational_status(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.SCM, name, "SCM 配置不存在")
        quotes = await self._build_scm_client(config).fetch_supplier_quotes()
        return {
            "config_name": name,
            "system_type": "scm",
            "quote_summary": self._summarize_scm_quotes(quotes),
            "purchase_suggestion_ready": len(quotes) > 0,
        }

    async def list_wms_logs(self, limit: int = 20) -> dict[str, Any]:
        return await self._list_logs(ERPSystemType.WMS, limit)

    async def get_wms_operational_status(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.WMS, name, "WMS 配置不存在")
        inventory_items = await self._fetch_wms_inventory(config)
        summary = self._summarize_wms_inventory(inventory_items)
        return {
            "config_name": name,
            "system_type": "wms",
            "inventory_summary": summary,
            "fulfillment_status": self._build_fulfillment_status(summary),
        }

    async def list_crm_logs(self, limit: int = 20, name: str = "default") -> dict[str, Any]:
        return await self._list_logs(ERPSystemType.CRM, limit, name=name)

    async def get_crm_operational_status(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.CRM, name, "CRM 配置不存在")
        client = self._build_crm_client(config)
        feedback_items = await client.fetch_customer_feedbacks()
        complaint_fetcher = getattr(client, "fetch_complaints", None)
        complaint_items = await complaint_fetcher() if callable(complaint_fetcher) else []
        return {
            "config_name": name,
            "system_type": "crm",
            "feedback_summary": self._summarize_crm_feedbacks(feedback_items),
            "complaint_summary": self._summarize_crm_complaints(complaint_items),
            "customer_feedback_ready": len(feedback_items) > 0,
        }

    async def list_fms_logs(self, limit: int = 20) -> dict[str, Any]:
        return await self._list_logs(ERPSystemType.FMS, limit)

    async def get_fms_operational_status(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.FMS, name, "FMS 配置不存在")
        client = self._build_fms_client(config)
        profit_facts = await client.fetch_profit_facts()
        ad_fetcher = getattr(client, "fetch_ad_spending", None)
        ad_spending = await ad_fetcher() if callable(ad_fetcher) else []
        return {
            "config_name": name,
            "system_type": "fms",
            "profit_summary": self._summarize_fms_profit_facts(profit_facts),
            "ad_spending_summary": self._summarize_fms_ad_spending(ad_spending),
            "profit_trace_ready": len(profit_facts) > 0,
        }

    async def get_profit_trend(self, name: str = "default") -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.FMS, name, "FMS profit trend config missing")
        profit_facts = await self._build_fms_client(config).fetch_profit_facts()
        grouped_points: dict[str, dict[str, Any]] = {}
        margin_samples: dict[str, list[float]] = {}

        for item in profit_facts:
            raw_date = (
                item.get("profit_date")
                or item.get("date")
                or item.get("biz_date")
                or item.get("day")
                or item.get("stat_date")
                or item.get("created_at")
                or item.get("updated_at")
                or datetime.now(UTC).date().isoformat()
            )
            point_date = str(raw_date)[:10]
            point = grouped_points.setdefault(
                point_date,
                {
                    "date": point_date,
                    "gross_profit": 0.0,
                    "cost": 0.0,
                    "ad_spending": 0.0,
                    "ad_sales": 0.0,
                    "margin_rate": 0.0,
                    "acos": 0.0,
                },
            )
            point["gross_profit"] += float(item.get("gross_profit", item.get("profit", 0)) or 0.0)
            point["cost"] += float(item.get("cost", 0) or 0.0)
            point["ad_spending"] += float(item.get("ad_spending", 0) or 0.0)
            point["ad_sales"] += float(item.get("ad_sales", item.get("sales", 0)) or 0.0)

            margin_value = item.get("margin_rate", item.get("margin"))
            if margin_value is not None:
                margin_samples.setdefault(point_date, []).append(float(margin_value))

        points = [grouped_points[key] for key in sorted(grouped_points.keys())]
        for point in points:
            samples = margin_samples.get(point["date"]) or []
            point["margin_rate"] = round(sum(samples) / len(samples), 4) if samples else 0.0
            point["gross_profit"] = round(point["gross_profit"], 4)
            point["cost"] = round(point["cost"], 4)
            point["ad_spending"] = round(point["ad_spending"], 4)
            point["ad_sales"] = round(point["ad_sales"], 4)
            point["acos"] = round(point["ad_spending"] / point["ad_sales"], 4) if point["ad_sales"] else 0.0

        summary = self._summarize_fms_profit_facts(points)
        return {
            "config_name": name,
            "config_id": str(config.id),
            "system_type": "fms",
            "ready": len(points) > 0,
            "total_points": len(points),
            "summary": summary,
            "points": points,
            "data_source": "fms_profit_facts",
        }

    async def list_bi_logs(self, limit: int = 20, name: str = "default") -> dict[str, Any]:
        return await self._list_logs(ERPSystemType.BI, limit, name=name)

    async def list_paas_logs(self, limit: int = 20, name: str = "default") -> dict[str, Any]:
        return await self._list_logs(ERPSystemType.PAAS, limit, name=name)

    async def _list_logs(self, system_type: ERPSystemType, limit: int, name: str = "default") -> dict[str, Any]:
        try:
            rows = await self.repo.list_sync_logs(system_type, limit=limit, name=name)
        except TypeError:
            rows = await self.repo.list_sync_logs(system_type, limit=limit)
        logs = [self._serialize_log(log, config) for log, config in rows]
        return {"total": len(logs), "logs": logs}

    async def _get_required_config(self, system_type: ERPSystemType, name: str, error_message: str) -> Any:
        config = await self.repo.get_config(system_type, name=name)
        if config is None:
            raise ValueError(error_message)
        return config

    def _permission_context(self) -> PermissionContext:
        return PermissionContext.from_actor(
            self.actor,
            tenant_id=self.tenant_id,
            purpose="erp_read_permission_filter",
            trace_id=self.actor.get("trace_id") or self.actor.get("request_id") or "erp-read-no-trace",
        )

    def _build_write_audit_context(
        self,
        *,
        selection_task: Any,
        domain: str,
        purpose: str,
        task_id: str,
    ) -> PermissionContext:
        config = selection_task.config or {}
        actor_id = (
            self.actor.get("user_id")
            or self.actor.get("sub")
            or self.actor.get("username")
            or self.actor.get("service_account_id")
            or f"pms-{domain}-service"
        )
        actor_type = (
            self.actor.get("actor_type")
            or ("user" if self.actor.get("user_id") or self.actor.get("username") or self.actor.get("sub") else "service")
        )
        scope = str(self.actor.get("scope") or "tenant")
        trace_id = (
            self.actor.get("trace_id")
            or self.actor.get("request_id")
            or (config.get("trace_id") if isinstance(config, dict) else None)
            or f"selection-adopt-{task_id}"
        )
        tenant_id = (
            self.tenant_id
            or self.actor.get("tenant_id")
            or (config.get("tenant_id") if isinstance(config, dict) else None)
        )
        return PermissionContext.from_actor(
            self.actor,
            tenant_id=tenant_id,
            actor_id=str(actor_id),
            actor_type=str(actor_type),
            scope=scope,
            purpose=purpose,
            trace_id=str(trace_id),
            idempotency_key=f"selection-adopt:{task_id}:{domain}",
            marketplace=self.actor.get("marketplace") or getattr(selection_task, "target_market", None),
            channel=self.actor.get("channel"),
            store_id=self.actor.get("store_id"),
            warehouse_id=self.actor.get("warehouse_id"),
            supplier_id=self.actor.get("supplier_id"),
            category_id=self.actor.get("category_id") or getattr(selection_task, "target_category", None),
            data_level=self.actor.get("data_level") or "internal",
        )

    @staticmethod
    def _attach_audit_context(payload: dict[str, Any], audit_context: PermissionContext) -> dict[str, Any]:
        enriched = dict(payload)
        context_payload = audit_context.to_filter()
        enriched["audit_context"] = context_payload
        enriched.setdefault("tenant_id", audit_context.tenant_id)
        enriched.setdefault("actor_id", audit_context.actor_id)
        enriched.setdefault("actor_type", audit_context.actor_type)
        enriched.setdefault("scope", audit_context.scope)
        enriched.setdefault("purpose", audit_context.purpose)
        enriched.setdefault("trace_id", audit_context.trace_id)
        if audit_context.idempotency_key:
            enriched.setdefault("idempotency_key", audit_context.idempotency_key)
        return enriched

    async def _call_with_permission_context(self, fetcher: Any) -> Any:
        signature = inspect.signature(fetcher)
        if "permission_context" in signature.parameters:
            return await fetcher(permission_context=self._permission_context())
        return await fetcher()

    async def _test_connection(self, config: Any, client: Any, *, system_type: str) -> dict[str, Any]:
        result = await client.test_connection()
        return {
            "config_id": str(config.id),
            "config_name": config.name,
            "system_type": system_type,
            "status": result["status"],
            "error_code": result["error_code"],
            "retryable": result["retryable"],
            "next_action": "sync_outbound" if system_type == "bi" and result["status"] == "ok" else ("sync_inbound" if result["status"] == "ok" else "check_connection"),
        }

    async def _run_import_sync(self, *, config: Any, entity_type: str, fetcher: Any, normalizer: Any) -> dict[str, Any]:
        log = await self.repo.create_sync_log(config_id=str(config.id), sync_type="import", entity_type=entity_type)
        start = perf_counter()
        try:
            items = await fetcher()
            total = len(items)
            success = 0
            failed = 0
            errors: list[str] = []
            for item in items:
                try:
                    await self.repo.upsert_product_by_external_id(normalizer(item))
                    success += 1
                except Exception as e:
                    failed += 1
                    errors.append(str(e))
            now = datetime.now(UTC)
            config.last_sync_at = now
            await self.repo.update_sync_log(
                str(log.id),
                status="completed" if failed == 0 else "partial_success",
                items_total=total,
                items_success=success,
                items_failed=failed,
                error_detail="; ".join(errors) if errors else None,
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            detail = self._serialize_log(log, config)
            detail.update({"error_code": None, "retryable": False, "next_action": "monitor"})
            return detail
        except (OMSClientError, SCMClientError, SOMClientError, PDMClientError, WMSClientError, CRMClientError, FMSClientError, BIClientError, PaaSClientError) as e:
            now = datetime.now(UTC)
            await self.repo.update_sync_log(
                str(log.id),
                status="failed",
                items_total=0,
                items_success=0,
                items_failed=0,
                error_detail=f"{e.error_code}:{e}",
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            raise
        except Exception as e:
            now = datetime.now(UTC)
            await self.repo.update_sync_log(
                str(log.id),
                status="failed",
                items_total=0,
                items_success=0,
                items_failed=0,
                error_detail=str(e),
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            raise

    async def _run_export_sync(self, *, config: Any, entity_type: str, limit: int, serializer: Any, pusher: Any) -> dict[str, Any]:
        log = await self.repo.create_sync_log(config_id=str(config.id), sync_type="export", entity_type=entity_type)
        start = perf_counter()
        try:
            products = await self.repo.list_products_for_export(limit=limit)
            payload = {"items": [serializer(product) for product in products]}
            await pusher(payload)
            now = datetime.now(UTC)
            config.last_sync_at = now
            await self.repo.update_sync_log(
                str(log.id),
                status="completed",
                items_total=len(products),
                items_success=len(products),
                items_failed=0,
                error_detail=None,
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            detail = self._serialize_log(log, config)
            detail.update({"error_code": None, "retryable": False, "next_action": "monitor"})
            return detail
        except (OMSClientError, SCMClientError, SOMClientError, PDMClientError, WMSClientError, CRMClientError, FMSClientError, BIClientError, PaaSClientError) as e:
            now = datetime.now(UTC)
            await self.repo.update_sync_log(
                str(log.id),
                status="failed",
                items_total=0,
                items_success=0,
                items_failed=0,
                error_detail=f"{e.error_code}:{e}",
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            raise
        except Exception as e:
            now = datetime.now(UTC)
            await self.repo.update_sync_log(
                str(log.id),
                status="failed",
                items_total=0,
                items_success=0,
                items_failed=0,
                error_detail=str(e),
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            raise

    def _build_oms_client(self, config: Any) -> OMSClient:
        extra = config.extra_config or {}
        return OMSClient(
            api_endpoint=config.api_endpoint,
            api_key=getattr(config, "api_key", None),
            inbound_path=extra.get("inbound_path", "/products"),
            outbound_path=extra.get("outbound_path", "/products/bulk-upsert"),
            timeout_seconds=extra.get("timeout_seconds", 10),
        )

    def _build_scm_client(self, config: Any) -> SCMClient:
        extra = config.extra_config or {}
        return SCMClient(
            api_endpoint=config.api_endpoint,
            api_key=getattr(config, "api_key", None),
            secret_key=getattr(config, "secret_key", None),
            inbound_path=extra.get("inbound_path", "/supplier-products"),
            outbound_path=extra.get("outbound_path", "/product-plans/bulk-upsert"),
            timeout_seconds=extra.get("timeout_seconds", 10),
        )

    def _build_som_client(self, config: Any) -> SOMClient:
        extra = config.extra_config or {}
        return SOMClient(
            api_endpoint=config.api_endpoint,
            api_key=getattr(config, "api_key", None),
            secret_key=getattr(config, "secret_key", None),
            inbound_path=extra.get("inbound_path", "/listings"),
            outbound_path=extra.get("outbound_path", "/listing-drafts"),
            timeout_seconds=extra.get("timeout_seconds", 10),
        )

    def _build_pdm_client(self, config: Any) -> PDMClient:
        extra = config.extra_config or {}
        return PDMClient(
            api_endpoint=config.api_endpoint,
            api_key=getattr(config, "api_key", None),
            secret_key=getattr(config, "secret_key", None),
            inbound_path=extra.get("inbound_path", "/recommendations"),
            outbound_path=extra.get("outbound_path", "/recommendations"),
            timeout_seconds=extra.get("timeout_seconds", 10),
        )

    def _build_wms_client(self, config: Any) -> WMSClient:
        extra = config.extra_config or {}
        return WMSClient(
            api_endpoint=config.api_endpoint,
            api_key=getattr(config, "api_key", None),
            secret_key=getattr(config, "secret_key", None),
            inbound_path=extra.get("inbound_path", "/inventory-snapshots"),
            outbound_path=extra.get("outbound_path", "/replenishment-plans/bulk-upsert"),
            timeout_seconds=extra.get("timeout_seconds", 10),
        )

    def _build_crm_client(self, config: Any) -> CRMClient:
        extra = config.extra_config or {}
        return CRMClient(
            api_endpoint=config.api_endpoint,
            api_key=getattr(config, "api_key", None),
            inbound_path=extra.get("inbound_path", "/customer-feedbacks"),
            outbound_path=extra.get("outbound_path", "/followups/bulk-upsert"),
            timeout_seconds=extra.get("timeout_seconds", 10),
        )

    def _build_fms_client(self, config: Any) -> FMSClient:
        extra = config.extra_config or {}
        return FMSClient(
            api_endpoint=config.api_endpoint,
            api_key=getattr(config, "api_key", None),
            inbound_path=extra.get("inbound_path", "/finance-metrics"),
            outbound_path=extra.get("outbound_path", "/profit-plans/bulk-upsert"),
            timeout_seconds=extra.get("timeout_seconds", 10),
        )

    def _build_bi_client(self, config: Any) -> BIClient:
        extra = config.extra_config or {}
        return BIClient(
            api_endpoint=config.api_endpoint,
            api_key=getattr(config, "api_key", None),
            health_path=extra.get("health_path", "/health"),
            dataset_path=extra.get("dataset_path", "/datasets/push"),
            timeout_seconds=extra.get("timeout_seconds", 10),
        )

    def _build_paas_client(self, config: Any) -> PaaSClient:
        extra = config.extra_config or {}
        return PaaSClient(
            api_endpoint=config.api_endpoint,
            api_key=getattr(config, "api_key", None),
            health_path=extra.get("health_path", "/health"),
            trigger_path=extra.get("trigger_path", "/workflows/trigger"),
            status_path=extra.get("status_path", "/workflows/{run_id}"),
            timeout_seconds=extra.get("timeout_seconds", 10),
        )

    async def _fetch_oms_products(self, config: Any) -> list[dict[str, Any]]:
        return await self._build_oms_client(config).fetch_products()

    async def _push_oms_products(self, config: Any, payload: dict[str, Any]) -> None:
        await self._build_oms_client(config).push_products(payload)

    async def _fetch_scm_supplier_products(self, config: Any) -> list[dict[str, Any]]:
        return await self._build_scm_client(config).fetch_supplier_products()

    async def _push_scm_product_plan(self, config: Any, payload: dict[str, Any]) -> None:
        await self._build_scm_client(config).push_product_plan(payload)

    async def _fetch_wms_inventory(self, config: Any) -> list[dict[str, Any]]:
        return await self._build_wms_client(config).fetch_inventory_snapshots()

    async def _push_wms_replenishment_plan(self, config: Any, payload: dict[str, Any]) -> None:
        await self._build_wms_client(config).push_replenishment_plan(payload)

    async def _fetch_crm_feedbacks(self, config: Any) -> list[dict[str, Any]]:
        return await self._build_crm_client(config).fetch_customer_feedbacks()

    async def _push_crm_followups(self, config: Any, payload: dict[str, Any]) -> None:
        await self._build_crm_client(config).push_followups(payload)

    async def _fetch_fms_metrics(self, config: Any) -> list[dict[str, Any]]:
        return await self._build_fms_client(config).fetch_finance_metrics()

    async def _push_fms_profit_plan(self, config: Any, payload: dict[str, Any]) -> None:
        await self._build_fms_client(config).push_profit_plan(payload)

    async def _push_bi_datasets(self, config: Any, payload: dict[str, Any]) -> None:
        await self._build_bi_client(config).push_dataset(payload)

    async def _build_bi_datasets(self) -> list[dict[str, Any]]:
        datasets = [
            {
                "dataset_name": "selection_tasks_snapshot",
                "source": "data_lake_catalog",
                "consumer_group": "bi-selection-dashboard",
                "rows": [],
            },
            {
                "dataset_name": "data_sync_events_snapshot",
                "source": "data_lake_catalog",
                "consumer_group": "bi-event-dashboard",
                "rows": [],
            },
            {
                "dataset_name": "selection_task_metrics",
                "source": "selection_task_repository",
                "consumer_group": "bi-selection-metrics",
                "rows": [],
            },
        ]
        now = datetime.now(UTC).isoformat()
        for product in await self.repo.list_products_for_export(limit=100):
            datasets[0]["rows"].append(
                {
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "brand": product.brand,
                    "platform": product.platform,
                    "external_product_id": product.external_product_id,
                    "exported_at": now,
                }
            )
            datasets[1]["rows"].append(
                {
                    "aggregate_id": product.external_product_id,
                    "entity_type": product.platform,
                    "event_type": f"{product.platform}.snapshot_exported",
                    "exported_at": now,
                }
            )
        if self.selection_repo is not None:
            tasks, _ = await self.selection_repo.list_tasks(limit=100, offset=0)
            for task in tasks:
                row = self._serialize_selection_task_metrics(task)
                if row is not None:
                    datasets[2]["rows"].append(row)
        return datasets

    @staticmethod
    def _calculate_selection_cycle_days(task: Any) -> float | None:
        if task is None or task.created_at is None or task.completed_at is None:
            return None
        elapsed_seconds = (task.completed_at - task.created_at).total_seconds()
        return round(max(elapsed_seconds, 0.0) / 86400, 4)

    @classmethod
    def _build_daily_kpi_row(cls, task: Any) -> dict[str, Any] | None:
        config = task.config or {}
        adoption = config.get("adoption") if isinstance(config.get("adoption"), dict) else {}
        feedback_snapshot = config.get("execution_feedback_snapshot") if isinstance(config.get("execution_feedback_snapshot"), dict) else {}
        if not adoption or not feedback_snapshot:
            return None

        orders = (feedback_snapshot.get("sales") or {}).get("orders") or {}
        reviews = feedback_snapshot.get("reviews") or {}
        profit = feedback_snapshot.get("profit") or {}
        inventory = (feedback_snapshot.get("inventory") or {}).get("summary") or {}
        decision_output = ((config.get("execution_result") or {}).get("decision_output") or {}) if isinstance(config.get("execution_result"), dict) else {}

        units = int(orders.get("units") or 0)
        gross_profit_total = float(profit.get("gross_profit_total") or 0.0)
        total_amount = float(adoption.get("total_amount") or 0.0)
        avg_rating = cls._coerce_number(reviews.get("avg_rating"))
        review_count = int(reviews.get("review_count") or 0)
        available_inventory = int(inventory.get("available_quantity_total") or 0)
        roi_percent = round((gross_profit_total / total_amount) * 100, 4) if total_amount > 0 else 0.0
        hit_threshold = units >= 20 and gross_profit_total > 0 and (avg_rating or 0.0) >= 4.2
        cycle_days = cls._calculate_selection_cycle_days(task)

        return {
            "task_id": str(task.id),
            "query": task.title,
            "category": task.target_category,
            "target_market": task.target_market,
            "decision": ((decision_output.get("decision") or {}).get("decision") if isinstance(decision_output.get("decision"), dict) else None),
            "adopted_at": adoption.get("adopted_at") or adoption.get("executed_at"),
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "selection_cycle_days": cycle_days,
            "oms_units": units,
            "crm_avg_rating": avg_rating,
            "crm_review_count": review_count,
            "fms_gross_profit_total": round(gross_profit_total, 4),
            "fms_cost_total": round(float(profit.get("cost_total") or 0.0), 4),
            "actual_roi_percent": roi_percent,
            "inventory_available_total": available_inventory,
            "is_hot_hit": bool(hit_threshold),
            "feedback_synced_at": feedback_snapshot.get("synced_at"),
        }

    async def compute_daily_selection_kpis(self, *, day: str | None = None, limit: int = 200) -> dict[str, Any]:
        if self.selection_repo is None:
            raise ValueError("selection repository unavailable")
        tasks, _ = await self.selection_repo.list_tasks(limit=limit, offset=0)
        rows: list[dict[str, Any]] = []
        for task in tasks:
            row = self._build_daily_kpi_row(task)
            if row is None:
                continue
            kpi_day = str(row.get("completed_at") or row.get("adopted_at") or "").split("T", 1)[0]
            if day and kpi_day != day:
                continue
            row["kpi_date"] = kpi_day or day or datetime.now(UTC).date().isoformat()
            rows.append(row)

        kpi_date = day or (rows[0].get("kpi_date") if rows else datetime.now(UTC).date().isoformat())
        task_count = len(rows)
        hit_count = sum(1 for row in rows if row.get("is_hot_hit"))
        roi_values = [float(row.get("actual_roi_percent") or 0.0) for row in rows]
        cycle_values = [float(row.get("selection_cycle_days")) for row in rows if row.get("selection_cycle_days") is not None]
        review_values = [float(row.get("crm_avg_rating") or 0.0) for row in rows if row.get("crm_avg_rating") is not None]
        units_values = [int(row.get("oms_units") or 0) for row in rows]
        gross_profit_values = [float(row.get("fms_gross_profit_total") or 0.0) for row in rows]

        summary = {
            "kpi_date": kpi_date,
            "task_count": task_count,
            "hit_task_count": hit_count,
            "爆款命中率": round(hit_count / task_count, 4) if task_count else 0.0,
            "ROI": round(sum(roi_values) / len(roi_values), 4) if roi_values else 0.0,
            "选品周期": round(sum(cycle_values) / len(cycle_values), 4) if cycle_values else 0.0,
            "avg_review_rating": round(sum(review_values) / len(review_values), 4) if review_values else 0.0,
            "total_units": sum(units_values),
            "total_gross_profit": round(sum(gross_profit_values), 4),
        }
        return {
            "kpi_date": kpi_date,
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "selection_execution_feedback",
            "input_scope": {
                "task_limit": limit,
                "tenant_id": self.tenant_id,
                "day": day,
            },
            "summary": summary,
            "rows": rows,
        }

    async def get_latest_daily_selection_kpis(self, *, name: str = "default") -> dict[str, Any] | None:
        config = await self._get_required_config(ERPSystemType.BI, name, "BI 配置不存在")
        payload = await self._call_with_permission_context(self._build_bi_client(config).read_dataset)
        datasets = payload.get("datasets") if isinstance(payload, dict) else []
        if not isinstance(datasets, list):
            return None
        target = next((item for item in datasets if isinstance(item, dict) and item.get("dataset_name") == "selection_daily_kpis"), None)
        if not isinstance(target, dict):
            return None
        rows = target.get("rows") if isinstance(target.get("rows"), list) else []
        if not rows:
            return None
        return rows[-1]

    async def sync_daily_bi_kpis(self, *, name: str = "default", day: str | None = None, limit: int = 200) -> dict[str, Any]:
        config = await self._get_required_config(ERPSystemType.BI, name, "BI 配置不存在")
        log = await self.repo.create_sync_log(config_id=str(config.id), sync_type="export", entity_type="selection_daily_kpis")
        start = perf_counter()
        try:
            kpi_snapshot = await self.compute_daily_selection_kpis(day=day, limit=limit)
            client = self._build_bi_client(config)
            existing_payload = await client.read_dataset()
            existing_datasets = existing_payload.get("datasets") if isinstance(existing_payload, dict) and isinstance(existing_payload.get("datasets"), list) else []
            next_datasets: list[dict[str, Any]] = []
            replaced = False
            for dataset in existing_datasets:
                if not isinstance(dataset, dict):
                    continue
                if dataset.get("dataset_name") != "selection_daily_kpis":
                    next_datasets.append(dataset)
                    continue
                rows = dataset.get("rows") if isinstance(dataset.get("rows"), list) else []
                rows = [row for row in rows if isinstance(row, dict) and row.get("kpi_date") != kpi_snapshot.get("kpi_date")]
                rows.append(kpi_snapshot)
                next_datasets.append({
                    **dataset,
                    "source": "selection_execution_feedback",
                    "consumer_group": dataset.get("consumer_group") or "bi-selection-daily-kpi",
                    "rows": rows,
                })
                replaced = True
            if not replaced:
                next_datasets.append(
                    {
                        "dataset_name": "selection_daily_kpis",
                        "source": "selection_execution_feedback",
                        "consumer_group": "bi-selection-daily-kpi",
                        "rows": [kpi_snapshot],
                    }
                )
            await client.push_dataset({"datasets": next_datasets})
            now = datetime.now(UTC)
            config.last_sync_at = now
            await self.repo.update_sync_log(
                str(log.id),
                status="completed",
                items_total=len(kpi_snapshot.get("rows") or []),
                items_success=len(kpi_snapshot.get("rows") or []),
                items_failed=0,
                error_detail=None,
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            detail = self._serialize_log(log, config)
            detail.update(
                {
                    "kpi_date": kpi_snapshot.get("kpi_date"),
                    "kpi_summary": kpi_snapshot.get("summary"),
                    "generated_at": kpi_snapshot.get("generated_at"),
                    "input_scope": kpi_snapshot.get("input_scope"),
                }
            )
            return detail
        except BIClientError as e:
            now = datetime.now(UTC)
            await self.repo.update_sync_log(
                str(log.id),
                status="failed",
                items_total=0,
                items_success=0,
                items_failed=0,
                error_detail=f"{e.error_code}:{e}",
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            raise
        except Exception as e:
            now = datetime.now(UTC)
            await self.repo.update_sync_log(
                str(log.id),
                status="failed",
                items_total=0,
                items_success=0,
                items_failed=0,
                error_detail=str(e),
                finished_at=now,
                duration_seconds=round(perf_counter() - start, 4),
            )
            raise

    @staticmethod
    def _coerce_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").replace("%", "").strip()
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    @classmethod
    def _serialize_selection_task_metrics(cls, task: Any) -> dict[str, Any] | None:
        config = task.config or {}
        execution_result = config.get("execution_result") if isinstance(config, dict) else None
        if not isinstance(execution_result, dict):
            return None
        decision_output = execution_result.get("decision_output") if isinstance(execution_result.get("decision_output"), dict) else {}
        pricing = decision_output.get("pricing") if isinstance(decision_output.get("pricing"), dict) else {}
        profitability = decision_output.get("profitability") if isinstance(decision_output.get("profitability"), dict) else {}
        risks = decision_output.get("risks") if isinstance(decision_output.get("risks"), list) else []
        recommendation_reasons = decision_output.get("recommendation_reasons") if isinstance(decision_output.get("recommendation_reasons"), list) else []
        rescore_summary = decision_output.get("rescore_summary") if isinstance(decision_output.get("rescore_summary"), dict) else {}
        return {
            "task_id": str(task.id),
            "query": task.title,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "category": task.target_category,
            "target_market": task.target_market,
            "risk_count": len(risks),
            "risk_level": (risks[0].get("category") if risks and isinstance(risks[0], dict) else None),
            "recommendation_count": len(recommendation_reasons),
            "recommended_price": cls._coerce_number(pricing.get("recommended_price")),
            "roi_year1_percent": cls._coerce_number(profitability.get("roi_year1_percent") or profitability.get("expected_roi")),
            "payback_period_months": cls._coerce_number(profitability.get("payback_period_months")),
            "expected_margin": cls._coerce_number(profitability.get("expected_margin") or profitability.get("gross_margin_pct")),
            "decision": (decision_output.get("decision") or {}).get("decision") if isinstance(decision_output.get("decision"), dict) else None,
            "rescore_score": cls._coerce_number(rescore_summary.get("score")),
            "feedback_feature_asset_ready": bool(config.get("feedback_feature_asset_ready", False)),
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }

    async def get_bi_task_metrics(self, task_id: str) -> dict[str, Any] | None:
        if self.selection_repo is None:
            return None
        try:
            normalized_task_id: Any = UUID(str(task_id))
        except ValueError:
            normalized_task_id = task_id
        task = await self.selection_repo.get_task(normalized_task_id)
        if task is None:
            return None
        return self._serialize_selection_task_metrics(task)

    async def get_selection_feedback_loop_status(self, task_id: str, *, crm_name: str = "default", paas_name: str = "default") -> dict[str, Any]:
        metrics = await self.get_bi_task_metrics(task_id)
        if metrics is None:
            raise ValueError(f"选品任务不存在: {task_id}")

        selection_task = await self._get_selection_task(task_id)
        task_config = selection_task.config or {}
        feedback_state = {
            "auto_rescore_completed": bool(task_config.get("feedback_loop_rescored", False)),
            "feature_asset_ready": bool(task_config.get("feedback_feature_asset_ready", False)),
            "rescore_summary": ((task_config.get("execution_result") or {}).get("decision_output") or {}).get("rescore_summary") or task_config.get("feedback_loop_rescore"),
            "feature_asset": task_config.get("feedback_feature_asset"),
        }

        crm_logs = await self.list_crm_logs(limit=5, name=crm_name)
        bi_logs = await self.list_bi_logs(limit=5, name="default")
        paas_logs = await self.list_paas_logs(limit=5, name=paas_name)
        paas_status = await self.get_paas_run_status(name=paas_name, run_id=((paas_logs.get("logs", [{}])[0] or {}).get("run_id") or (paas_logs.get("logs", [{}])[0] or {}).get("log_id") or "log-paas-latest")) if paas_logs.get("logs") else {
            "system_type": "paas",
            "status": "not_started",
            "callback_expected": True,
            "retry_recommended": False,
        }

        latest_crm = (crm_logs.get("logs") or [None])[0]
        latest_bi = (bi_logs.get("logs") or [None])[0]
        latest_paas = (paas_logs.get("logs") or [None])[0]
        rescore_ready = bool(metrics.get("decision") and metrics.get("recommended_price") is not None)

        return {
            "task_id": task_id,
            "crm": {
                "config_name": crm_name,
                "customer_feedback_ready": latest_crm is not None and latest_crm.get("status") in {"completed", "partial_success"},
                "latest_log": latest_crm,
            },
            "bi": {
                "task_metrics_ready": metrics is not None,
                "task_metrics": metrics,
                "latest_log": latest_bi,
            },
            "paas": {
                "workflow_ready": latest_paas is not None,
                "latest_log": latest_paas,
                "run_status": paas_status,
            },
            "selection_feedback_loop": {
                "rescore_ready": rescore_ready,
                "auto_rescore_completed": feedback_state.get("auto_rescore_completed", False),
                "feature_asset_ready": feedback_state.get("feature_asset_ready", False),
                "rescore_summary": feedback_state.get("rescore_summary"),
                "feature_asset": feedback_state.get("feature_asset"),
                "recommended_actions": [
                    action
                    for action in [
                        None if latest_crm else "run_crm_sync",
                        None if latest_bi else "export_bi_assets",
                        None if latest_paas else "trigger_paas_workflow",
                        None if rescore_ready else "rescore_selection_task",
                    ]
                    if action is not None
                ],
            },
        }

    async def get_selection_profit_trace(self, task_id: str, *, crm_name: str = "default", fms_name: str = "default", wms_name: str = "default", paas_name: str = "default") -> dict[str, Any]:
        feedback_loop = await self.get_selection_feedback_loop_status(task_id, crm_name=crm_name, paas_name=paas_name)
        fms_status = await self.get_fms_operational_status(name=fms_name)
        wms_status = await self.get_wms_operational_status(name=wms_name)
        metrics = feedback_loop["bi"]["task_metrics"]
        trace_id = f"selection-profit-trace-{task_id}"
        return {
            "task_id": task_id,
            "trace_id": trace_id,
            "trace_chain": {
                "selection": {"task_id": task_id, "trace_id": trace_id, "decision": metrics.get("decision")},
                "crm": {"trace_id": trace_id, "feedback_ready": feedback_loop["crm"]["customer_feedback_ready"]},
                "wms": {"trace_id": trace_id, "inventory_summary": wms_status.get("inventory_summary")},
                "fms": {"trace_id": trace_id, "profit_summary": fms_status.get("profit_summary"), "profit_trace_ready": fms_status.get("profit_trace_ready")},
                "bi": {"trace_id": trace_id, "task_metrics": metrics},
                "paas": {"trace_id": trace_id, "workflow_status": (feedback_loop["paas"]["run_status"] or {}).get("status")},
            },
            "profit_contract": {
                "recommended_price": metrics.get("recommended_price"),
                "roi_year1_percent": metrics.get("roi_year1_percent"),
                "expected_margin": metrics.get("expected_margin"),
                "gross_profit_total": (fms_status.get("profit_summary") or {}).get("gross_profit_total"),
                "inventory_available": (wms_status.get("inventory_summary") or {}).get("available_quantity_total"),
            },
            "ready": bool(
                feedback_loop["selection_feedback_loop"]["rescore_ready"]
                and feedback_loop["selection_feedback_loop"]["auto_rescore_completed"]
                and feedback_loop["selection_feedback_loop"]["feature_asset_ready"]
                and fms_status.get("profit_trace_ready")
            ),
        }

    async def sync_selection_execution_feedback(
        self,
        task_id: str,
        *,
        oms_name: str = "default",
        crm_name: str = "default",
        fms_name: str = "default",
        wms_name: str = "default",
        auto_rescore: bool = True,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        adoption = config.get("adoption") if isinstance(config.get("adoption"), dict) else {}
        if not adoption:
            raise ValueError("该选品任务尚未采纳推荐，无法同步执行反馈")

        matched_keys = self._build_selection_feedback_match_keys(selection_task, adoption)

        oms_config = await self._get_required_config(ERPSystemType.OMS, oms_name, "OMS 配置不存在")
        crm_config = await self._get_required_config(ERPSystemType.CRM, crm_name, "CRM 配置不存在")
        fms_config = await self._get_required_config(ERPSystemType.FMS, fms_name, "FMS 配置不存在")
        wms_config = await self._get_required_config(ERPSystemType.WMS, wms_name, "WMS 配置不存在")

        orders = await self._call_with_permission_context(self._build_oms_client(oms_config).fetch_orders)
        feedbacks = await self._build_crm_client(crm_config).fetch_customer_feedbacks()
        profit_facts = await self._build_fms_client(fms_config).fetch_profit_facts()
        inventory_items = await self._build_wms_client(wms_config).fetch_inventory_snapshots()

        matched_orders = [item for item in orders if self._match_selection_feedback_item(item, matched_keys)]
        matched_feedbacks = [item for item in feedbacks if self._match_selection_feedback_item(item, matched_keys)]
        matched_profit_facts = [item for item in profit_facts if self._match_selection_feedback_item(item, matched_keys)]
        matched_inventory = [item for item in inventory_items if self._match_selection_feedback_item(item, matched_keys)]

        order_summary = self._summarize_oms_orders(matched_orders)
        sales_summary = self._summarize_oms_sales_metrics(matched_orders)
        feedback_summary = self._summarize_crm_feedbacks(matched_feedbacks)
        profit_summary = self._summarize_fms_profit_facts(matched_profit_facts)
        inventory_summary = self._summarize_wms_inventory(matched_inventory)
        fulfillment_status = self._build_fulfillment_status(inventory_summary)

        feedback_snapshot = {
            "task_id": task_id,
            "matched_keys": matched_keys,
            "sales": {
                "orders": order_summary,
                "metrics": sales_summary,
            },
            "reviews": feedback_summary,
            "profit": profit_summary,
            "inventory": {
                "summary": inventory_summary,
                "fulfillment_status": fulfillment_status,
            },
            "synced_at": datetime.now(UTC).isoformat(),
        }

        rescore_payload = {
            "sales_7d": int(order_summary.get("units") or 0),
            "review_rating": feedback_summary.get("avg_rating"),
            "review_count": int(feedback_summary.get("review_count") or 0),
            "gross_profit": float(profit_summary.get("gross_profit_total") or 0.0),
            "margin_rate": profit_summary.get("avg_margin_rate"),
            "available_inventory": int(inventory_summary.get("available_quantity_total") or 0),
            "stockout_risk": bool(fulfillment_status.get("backorder_risk", False)),
            "source": "erp_execution_feedback_sync",
            "notes": "按已采纳任务定向聚合 OMS/CRM/FMS/WMS 执行反馈",
        }

        config["execution_feedback_snapshot"] = feedback_snapshot
        adoption["feedback_sync"] = {
            "status": "synced",
            "oms_name": oms_name,
            "crm_name": crm_name,
            "fms_name": fms_name,
            "wms_name": wms_name,
            "matched_order_count": len(matched_orders),
            "matched_review_count": len(matched_feedbacks),
            "matched_profit_count": len(matched_profit_facts),
            "matched_inventory_count": len(matched_inventory),
            "last_synced_at": feedback_snapshot["synced_at"],
        }
        config["adoption"] = adoption
        config["status_reason"] = "已完成执行后销售/评价/利润/库存反馈同步"
        selection_task.config = config
        await self.session.flush()

        rescore_result: dict[str, Any] | None = None
        feature_asset: dict[str, Any] | None = None
        if auto_rescore:
            selection_service = SelectionTaskService(self.session, tenant_id=self.tenant_id, actor=self.actor)
            if self.selection_repo is not None:
                selection_service.repo = self.selection_repo
            rescore_result = await selection_service.rescore_task_from_execution_feedback(task_id, rescore_payload)
            feature_asset = await selection_service.export_feedback_feature_asset(task_id)

        return {
            "task_id": task_id,
            "matched_keys": matched_keys,
            "execution_feedback_snapshot": feedback_snapshot,
            "rescore_payload": rescore_payload,
            "auto_rescore": auto_rescore,
            "rescore_result": rescore_result,
            "feature_asset": feature_asset.get("feature_asset") if isinstance(feature_asset, dict) else None,
        }

    async def ingest_selection_review_cases(self, task_id: str, *, crm_name: str = "default", publish_events: bool = True) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        adoption = config.get("adoption") if isinstance(config.get("adoption"), dict) else {}
        if not adoption:
            raise ValueError("该选品任务尚未采纳推荐，无法沉淀CRM评价案例")

        matched_keys = self._build_selection_feedback_match_keys(selection_task, adoption)
        crm_config = await self._get_required_config(ERPSystemType.CRM, crm_name, "CRM 配置不存在")
        feedbacks = await self._build_crm_client(crm_config).fetch_customer_feedbacks()
        matched_feedbacks = [item for item in feedbacks if self._match_selection_feedback_item(item, matched_keys)]
        if not matched_feedbacks:
            raise ValueError("未找到与当前任务匹配的CRM评价数据")

        knowledge_service = (
            KnowledgeService(self.session, tenant_id=self.tenant_id, actor=self.actor)
            if self.session is not None
            else LocalKnowledgeService()
        )
        data_sync_service = DataSyncService(self.session, tenant_id=self.tenant_id, actor=self.actor) if self.session is not None else None

        ingested_cases: list[dict[str, Any]] = []
        published_events: list[dict[str, Any]] = []
        for feedback in matched_feedbacks:
            enriched_feedback = {
                **feedback,
                "task_id": str(selection_task.id),
                "task_query": selection_task.title,
            }
            ingested = await knowledge_service.ingest_review_case(enriched_feedback)
            ingested_cases.append(ingested)
            if publish_events and data_sync_service is not None:
                review_id = str(ingested.get("review_id") or feedback.get("id") or feedback.get("ticket_id") or feedback.get("product_id") or selection_task.id)
                event = await data_sync_service.publish_domain_event(
                    aggregate_id=review_id,
                    payload={
                        "task_id": str(selection_task.id),
                        "review_id": review_id,
                        "product_id": feedback.get("product_id"),
                        "asin": feedback.get("asin"),
                        "rating": feedback.get("customer_score") or feedback.get("rating"),
                        "review_count": feedback.get("review_count") or 1,
                        "feedback": feedback.get("feedback"),
                        "knowledge_doc_id": ingested.get("doc_id"),
                        "knowledge_case_type": ingested.get("case_type"),
                    },
                    event_type="review.updated",
                )
                published_events.append(event)

        config["review_case_ingest"] = {
            "status": "completed",
            "crm_name": crm_name,
            "matched_review_count": len(matched_feedbacks),
            "knowledge_case_count": len(ingested_cases),
            "published_event_count": len(published_events),
            "last_ingested_at": datetime.now(UTC).isoformat(),
            "case_type": "crm_review_case",
        }
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "crm_name": crm_name,
            "matched_keys": matched_keys,
            "matched_review_count": len(matched_feedbacks),
            "ingested_cases": ingested_cases,
            "published_events": published_events,
            "case_type": "crm_review_case",
        }

    async def get_adoption_status(self, task_id: str) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        adoption = config.get("adoption") if isinstance(config.get("adoption"), dict) else {}
        if not adoption:
            return {
                "task_id": task_id,
                "adopted": False,
                "status": "not_adopted",
                "message": "该选品任务尚未采纳推荐",
            }
        execution_status = adoption.get("execution_status") or {}
        scm_status = execution_status.get("scm") or {}
        wms_status = execution_status.get("wms") or {}
        oms_status = execution_status.get("oms") or {}
        scm_ok = scm_status.get("status") in {"pending_review", "approved", "ordered", "shipped", "completed"}
        wms_ok = wms_status.get("status") in {"reserved", "allocated", "confirmed"}
        oms_ok = oms_status.get("status") in {"draft_created", "published", "active"}
        all_ok = scm_ok and wms_ok and oms_ok
        overall = "executed" if all_ok else "partial"
        if adoption.get("status") == "executed" and all_ok:
            overall = "completed"
        return {
            "task_id": task_id,
            "adopted": True,
            "status": overall,
            "adopted_at": adoption.get("executed_at"),
            "quantity": adoption.get("quantity"),
            "supplier_code": adoption.get("supplier_code"),
            "supplier_name": adoption.get("supplier_name"),
            "purchase_order_id": adoption.get("purchase_order_id"),
            "scm": {
                "purchase_order_id": scm_status.get("purchase_order_id") or adoption.get("purchase_order_id"),
                "status": scm_status.get("status") or "unknown",
                "config_name": scm_status.get("config_name"),
                "log_id": scm_status.get("log_id"),
            },
            "wms": {
                "reservation_id": wms_status.get("reservation_id"),
                "location_code": wms_status.get("location_code"),
                "status": wms_status.get("status") or "unknown",
                "config_name": wms_status.get("config_name"),
                "log_id": wms_status.get("log_id"),
            },
            "oms": {
                "listing_draft_id": oms_status.get("listing_draft_id"),
                "status": oms_status.get("status") or "unknown",
                "config_name": oms_status.get("config_name"),
                "log_id": oms_status.get("log_id"),
            },
            "notes": adoption.get("notes"),
        }

    async def list_adoption_logs(
        self,
        task_id: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        adoption = config.get("adoption") if isinstance(config.get("adoption"), dict) else {}
        logs: list[dict[str, Any]] = []
        if adoption:
            logs.append({
                "task_id": task_id,
                "action": "adopt",
                "timestamp": adoption.get("executed_at"),
                "actor": self.actor.get("sub") or self.actor.get("user_id") or "system",
                "quantity": adoption.get("quantity"),
                "supplier_code": adoption.get("supplier_code"),
                "purchase_order_id": adoption.get("purchase_order_id"),
                "reservation_id": (adoption.get("warehouse_reservation") or {}).get("reservation_id"),
                "listing_draft_id": (adoption.get("listing_draft") or {}).get("listing_draft_id"),
                "notes": adoption.get("notes"),
            })
        feedback = config.get("feedback_loop_rescored")
        if feedback:
            logs.append({
                "task_id": task_id,
                "action": "rescore",
                "timestamp": config.get("feedback_loop_rescored_at"),
                "actor": "system",
                "detail": config.get("feedback_loop_rescore"),
            })
        feature_ready = config.get("feedback_feature_asset_ready")
        if feature_ready:
            logs.append({
                "task_id": task_id,
                "action": "feature_asset_export",
                "timestamp": config.get("feedback_feature_asset_exported_at"),
                "actor": "system",
                "detail": "feature asset exported",
            })
        return {
            "task_id": task_id,
            "total": len(logs),
            "logs": logs[:limit],
        }

    @staticmethod
    def _build_selection_feedback_match_keys(selection_task: Any, adoption: dict[str, Any]) -> dict[str, set[str]]:
        purchase_suggestion = adoption.get("purchase_suggestion") if isinstance(adoption.get("purchase_suggestion"), dict) else {}
        warehouse_reservation = adoption.get("warehouse_reservation") if isinstance(adoption.get("warehouse_reservation"), dict) else {}
        listing_draft = adoption.get("listing_draft") if isinstance(adoption.get("listing_draft"), dict) else {}
        keys: dict[str, set[str]] = {
            "task_ids": {str(selection_task.id)},
            "product_ids": {str(selection_task.id)},
            "skus": set(),
            "asins": set(),
            "listing_ids": set(),
        }
        for value in [
            purchase_suggestion.get("task_id"),
            purchase_suggestion.get("sku"),
            warehouse_reservation.get("sku"),
            listing_draft.get("sku"),
        ]:
            if value:
                keys["skus"].add(str(value))
        for value in [purchase_suggestion.get("asin"), listing_draft.get("asin")]:
            if value:
                keys["asins"].add(str(value))
        for value in [listing_draft.get("listing_draft_id")]:
            if value:
                keys["listing_ids"].add(str(value))
        return keys

    @staticmethod
    def _match_selection_feedback_item(item: dict[str, Any], matched_keys: dict[str, set[str]]) -> bool:
        candidate_values = {
            str(item.get("task_id") or ""),
            str(item.get("product_id") or ""),
            str(item.get("sku") or ""),
            str(item.get("asin") or ""),
            str(item.get("listing_draft_id") or ""),
            str(item.get("external_product_id") or ""),
        }
        candidate_values = {value for value in candidate_values if value}
        return bool(
            candidate_values.intersection(matched_keys.get("task_ids", set()))
            or candidate_values.intersection(matched_keys.get("product_ids", set()))
            or candidate_values.intersection(matched_keys.get("skus", set()))
            or candidate_values.intersection(matched_keys.get("asins", set()))
            or candidate_values.intersection(matched_keys.get("listing_ids", set()))
        )

    @staticmethod
    def _normalize_oms_product(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": item.get("name") or item.get("title") or f"OMS-{item.get('external_product_id') or item.get('id')}",
            "brand": item.get("brand"),
            "platform": "oms",
            "external_product_id": str(item.get("external_product_id") or item.get("id")),
            "asin": item.get("asin"),
            "price": item.get("price"),
            "rating": item.get("rating"),
            "review_count": item.get("review_count"),
            "sales_rank": item.get("sales_rank"),
            "image_url": item.get("image_url"),
            "product_url": item.get("product_url"),
            "attributes": item.get("attributes") or {},
        }

    @staticmethod
    def _normalize_scm_product(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": item.get("name") or item.get("title") or f"SCM-{item.get('external_product_id') or item.get('id')}",
            "brand": item.get("brand") or item.get("supplier_name"),
            "platform": "scm",
            "external_product_id": str(item.get("external_product_id") or item.get("id")),
            "asin": item.get("asin"),
            "price": item.get("procurement_price") or item.get("price"),
            "rating": item.get("rating"),
            "review_count": item.get("review_count"),
            "sales_rank": item.get("sales_rank"),
            "image_url": item.get("image_url"),
            "product_url": item.get("product_url"),
            "attributes": item.get("attributes") or {"supplier_code": item.get("supplier_code")},
        }

    @staticmethod
    def _summarize_oms_orders(items: list[dict[str, Any]]) -> dict[str, Any]:
        order_ids = {item.get("order_id") or item.get("id") for item in items if item.get("order_id") or item.get("id")}
        total_units = sum(int(item.get("quantity", item.get("units", 1)) or 0) for item in items)
        total_revenue = sum(float(item.get("revenue", item.get("gmv", item.get("sales_amount", 0))) or 0) for item in items)
        return {
            "orders": len(order_ids) if order_ids else len(items),
            "units": total_units,
            "revenue": round(total_revenue, 4),
        }

    @staticmethod
    def _summarize_oms_sales_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
        total_sales = sum(float(item.get("sales", item.get("sales_7d", item.get("sales_amount", 0))) or 0) for item in items)
        avg_conversion = 0.0
        conversion_values = [float(item.get("conversion_rate", item.get("conversion", 0)) or 0) for item in items if item.get("conversion_rate") is not None or item.get("conversion") is not None]
        if conversion_values:
            avg_conversion = round(sum(conversion_values) / len(conversion_values), 4)
        return {
            "items": len(items),
            "sales": round(total_sales, 4),
            "avg_conversion_rate": avg_conversion,
        }

    @staticmethod
    def _summarize_scm_quotes(items: list[dict[str, Any]]) -> dict[str, Any]:
        supplier_codes = {item.get("supplier_code") or item.get("supplier_name") for item in items if item.get("supplier_code") or item.get("supplier_name")}
        price_values = [float(item.get("procurement_price", item.get("quote_price", item.get("price", 0))) or 0) for item in items if item.get("procurement_price") is not None or item.get("quote_price") is not None or item.get("price") is not None]
        avg_quote = round(sum(price_values) / len(price_values), 4) if price_values else 0.0
        return {
            "items": len(items),
            "supplier_count": len(supplier_codes),
            "avg_quote_price": avg_quote,
        }

    @staticmethod
    def _summarize_wms_inventory(items: list[dict[str, Any]]) -> dict[str, Any]:
        warehouse_ids = {item.get("warehouse_id") for item in items if item.get("warehouse_id")}
        available_total = sum(int(item.get("available_quantity", 0) or 0) for item in items)
        safety_stock_total = sum(int(item.get("safety_stock", 0) or 0) for item in items)
        low_stock_count = sum(1 for item in items if int(item.get("available_quantity", 0) or 0) <= int(item.get("safety_stock", 0) or 0))
        return {
            "items": len(items),
            "warehouse_count": len(warehouse_ids),
            "available_quantity_total": available_total,
            "safety_stock_total": safety_stock_total,
            "low_stock_count": low_stock_count,
        }

    @staticmethod
    def _build_fulfillment_status(summary: dict[str, Any]) -> dict[str, Any]:
        low_stock = int(summary.get("low_stock_count", 0) or 0)
        if low_stock > 0:
            status = "attention_required"
        elif int(summary.get("available_quantity_total", 0) or 0) > 0:
            status = "healthy"
        else:
            status = "idle"
        return {
            "status": status,
            "warehouse_count": int(summary.get("warehouse_count", 0) or 0),
            "backorder_risk": low_stock > 0,
        }

    @staticmethod
    def _normalize_wms_inventory(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": item.get("product_name") or item.get("name") or f"WMS-{item.get('sku') or item.get('id')}",
            "brand": item.get("brand") or "WMS",
            "platform": "wms",
            "external_product_id": str(item.get("sku") or item.get("external_product_id") or item.get("id")),
            "asin": item.get("asin"),
            "price": item.get("inventory_value") or item.get("price"),
            "rating": item.get("stock_turnover_days"),
            "review_count": item.get("alert_count"),
            "sales_rank": item.get("storage_rank"),
            "image_url": item.get("image_url"),
            "product_url": item.get("product_url"),
            "attributes": {
                "warehouse_id": item.get("warehouse_id"),
                "total_quantity": item.get("total_quantity"),
                "available_quantity": item.get("available_quantity"),
                "in_transit_quantity": item.get("in_transit_quantity"),
                "safety_stock": item.get("safety_stock"),
                "days_no_sale": item.get("days_no_sale"),
            },
        }

    @staticmethod
    def _normalize_crm_feedback(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": item.get("product_name") or item.get("name") or f"CRM-{item.get('product_id') or item.get('id')}",
            "brand": item.get("brand") or "CRM",
            "platform": "crm",
            "external_product_id": str(item.get("product_id") or item.get("external_product_id") or item.get("id")),
            "asin": item.get("asin"),
            "price": item.get("price"),
            "rating": item.get("customer_score") or item.get("rating"),
            "review_count": item.get("review_count") or 1,
            "sales_rank": item.get("sales_rank"),
            "image_url": item.get("image_url"),
            "product_url": item.get("product_url"),
            "attributes": {
                "feedback": item.get("feedback"),
                "ticket_id": item.get("ticket_id"),
                "customer_id": item.get("customer_id"),
            },
        }

    @staticmethod
    def _summarize_crm_feedbacks(items: list[dict[str, Any]]) -> dict[str, Any]:
        review_count = sum(int(item.get("review_count") or 1) for item in items)
        rating_values = [float(item.get("customer_score", item.get("rating", 0)) or 0) for item in items if item.get("customer_score") is not None or item.get("rating") is not None]
        avg_rating = round(sum(rating_values) / len(rating_values), 4) if rating_values else 0.0
        complaint_count = sum(
            1
            for item in items
            if any(keyword in str(item.get("feedback") or "").lower() for keyword in ["refund", "complaint", "issue", "退货", "投诉", "问题"])
        )
        return {
            "items": len(items),
            "review_count": review_count,
            "avg_rating": avg_rating,
            "complaint_count": complaint_count,
        }

    @staticmethod
    def _summarize_crm_complaints(items: list[dict[str, Any]]) -> dict[str, Any]:
        reason_breakdown: dict[str, int] = {}
        for item in items:
            reason = str(item.get("reason") or item.get("category") or item.get("feedback") or "unknown").lower()
            if any(keyword in reason for keyword in ["logistics", "物流", "delivery", "shipping"]):
                key = "logistics"
            elif any(keyword in reason for keyword in ["refund", "退款", "return", "退货"]):
                key = "refund_return"
            elif any(keyword in reason for keyword in ["quality", "质量", "defect", "broken"]):
                key = "quality"
            else:
                key = "other"
            reason_breakdown[key] = reason_breakdown.get(key, 0) + 1
        return {
            "items": len(items),
            "reason_breakdown": reason_breakdown,
        }

    @staticmethod
    def _summarize_fms_ad_spending(items: list[dict[str, Any]]) -> dict[str, Any]:
        ad_spending_total = sum(float(item.get("ad_spending", item.get("advertising_spend", 0)) or 0) for item in items)
        ad_sales_total = sum(float(item.get("ad_sales", item.get("advertising_sales", 0)) or 0) for item in items)
        return {
            "items": len(items),
            "ad_spending_total": round(ad_spending_total, 4),
            "ad_sales_total": round(ad_sales_total, 4),
            "acos": round(ad_spending_total / ad_sales_total, 4) if ad_sales_total else 0.0,
        }

    @staticmethod
    def _summarize_fms_profit_facts(items: list[dict[str, Any]]) -> dict[str, Any]:
        gross_profit_total = sum(float(item.get("gross_profit", item.get("profit", 0)) or 0) for item in items)
        cost_total = sum(float(item.get("cost", 0) or 0) for item in items)
        margin_values = [float(item.get("margin_rate", item.get("margin", 0)) or 0) for item in items if item.get("margin_rate") is not None or item.get("margin") is not None]
        avg_margin = round(sum(margin_values) / len(margin_values), 4) if margin_values else 0.0
        return {
            "items": len(items),
            "gross_profit_total": round(gross_profit_total, 4),
            "cost_total": round(cost_total, 4),
            "avg_margin_rate": avg_margin,
        }

    @staticmethod
    def _normalize_fms_metric(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": item.get("product_name") or item.get("name") or f"FMS-{item.get('product_id') or item.get('id')}",
            "brand": item.get("brand") or "FMS",
            "platform": "fms",
            "external_product_id": str(item.get("product_id") or item.get("external_product_id") or item.get("id")),
            "asin": item.get("asin"),
            "price": item.get("gross_profit") or item.get("price"),
            "rating": item.get("margin_rate"),
            "review_count": item.get("review_count"),
            "sales_rank": item.get("sales_rank"),
            "image_url": item.get("image_url"),
            "product_url": item.get("product_url"),
            "attributes": {
                "gross_profit": item.get("gross_profit"),
                "cost": item.get("cost"),
                "expense": item.get("expense"),
            },
        }

    @staticmethod
    def _select_supplier_quote(quotes: list[dict[str, Any]], *, supplier_code: str | None = None) -> dict[str, Any]:
        normalized_quotes = [quote for quote in quotes if isinstance(quote, dict)]
        if supplier_code:
            for quote in normalized_quotes:
                if str(quote.get("supplier_code") or "").strip() == supplier_code:
                    return quote
            raise ValueError(f"未找到指定供应商报价: {supplier_code}")
        if not normalized_quotes:
            raise ValueError("SCM 未返回可用供应商报价")
        return min(
            normalized_quotes,
            key=lambda quote: float(
                quote.get("procurement_price")
                or quote.get("quote_price")
                or quote.get("price")
                or quote.get("cost")
                or 0
            ),
        )

    @classmethod
    def _build_pdm_recommendation_payload(
        cls,
        selection_task: Any,
        decision_output: dict[str, Any],
        *,
        notes: str | None,
        audit_context: PermissionContext,
    ) -> dict[str, Any]:
        pricing = decision_output.get("pricing") if isinstance(decision_output.get("pricing"), dict) else {}
        product_info = decision_output.get("product") if isinstance(decision_output.get("product"), dict) else {}
        decision_meta = decision_output.get("decision") if isinstance(decision_output.get("decision"), dict) else {}
        recommendation_name = product_info.get("name") or decision_meta.get("recommendation") or selection_task.title
        payload = {
            "task_id": str(selection_task.id),
            "recommendation_id": f"REC-{selection_task.id}",
            "query": selection_task.title,
            "product_name": recommendation_name,
            "target_category": selection_task.target_category,
            "target_market": selection_task.target_market,
            "decision": decision_meta.get("decision"),
            "confidence": decision_meta.get("confidence"),
            "recommended_price": cls._coerce_number(pricing.get("recommended_price")),
            "core_features": product_info.get("core_features") if isinstance(product_info.get("core_features"), list) else [],
            "status": "submitted",
            "notes": notes or "submitted-from-selection-adoption",
        }
        return cls._attach_audit_context(payload, audit_context)

    @classmethod
    def _build_purchase_suggestion_payload(
        cls,
        selection_task: Any,
        decision_output: dict[str, Any],
        *,
        quantity: int,
        supplier_code: str | None,
        quote: dict[str, Any],
        notes: str | None,
        audit_context: PermissionContext,
    ) -> dict[str, Any]:
        pricing = decision_output.get("pricing") if isinstance(decision_output.get("pricing"), dict) else {}
        product_info = decision_output.get("product") if isinstance(decision_output.get("product"), dict) else {}
        decision_meta = decision_output.get("decision") if isinstance(decision_output.get("decision"), dict) else {}
        recommended_price = cls._coerce_number(pricing.get("recommended_price"))
        unit_price = cls._coerce_number(
            quote.get("procurement_price") or quote.get("quote_price") or quote.get("price") or quote.get("cost")
        )
        if unit_price is None:
            raise ValueError("供应商报价缺少有效单价")
        resolved_supplier_code = supplier_code or quote.get("supplier_code") or quote.get("supplier_name") or "supplier-unknown"
        payload = {
            "task_id": str(selection_task.id),
            "query": selection_task.title,
            "product_name": product_info.get("name") or decision_meta.get("recommendation") or selection_task.title,
            "sku": f"SEL-{str(selection_task.id).split('-')[0].upper()}",
            "supplier_code": resolved_supplier_code,
            "supplier_name": quote.get("supplier_name"),
            "asin": quote.get("asin"),
            "quantity": int(quantity),
            "unit_price": unit_price,
            "total_amount": round(unit_price * int(quantity), 2),
            "target_market": selection_task.target_market,
            "target_procurement_price": recommended_price,
            "decision": decision_meta.get("decision"),
            "notes": notes or "adopted-from-selection-task",
        }
        return cls._attach_audit_context(payload, audit_context)

    @classmethod
    def _build_wms_reservation_payload(
        cls,
        selection_task: Any,
        decision_output: dict[str, Any],
        *,
        quantity: int,
        purchase_suggestion: dict[str, Any],
        audit_context: PermissionContext,
    ) -> dict[str, Any]:
        product_info = decision_output.get("product") if isinstance(decision_output.get("product"), dict) else {}
        volume_cbm = cls._coerce_number(product_info.get("volume_cbm")) or 0.018
        required_capacity = round(float(quantity) * float(volume_cbm), 4)
        payload = {
            "task_id": str(selection_task.id),
            "sku": purchase_suggestion.get("sku") or f"SEL-{str(selection_task.id).split('-')[0].upper()}",
            "product_name": purchase_suggestion.get("product_name") or selection_task.title,
            "quantity": int(quantity),
            "required_capacity_cbm": required_capacity,
            "warehouse_id": product_info.get("warehouse_id") or "default-warehouse",
            "reservation_id": f"RSV-{selection_task.id}",
            "location_code": product_info.get("location_code") or "WH-A-01",
            "status": "reserved",
        }
        return cls._attach_audit_context(payload, audit_context)

    @classmethod
    def _build_som_listing_draft_payload(
        cls,
        selection_task: Any,
        decision_output: dict[str, Any],
        *,
        purchase_suggestion: dict[str, Any],
        audit_context: PermissionContext,
    ) -> dict[str, Any]:
        pricing = decision_output.get("pricing") if isinstance(decision_output.get("pricing"), dict) else {}
        product_info = decision_output.get("product") if isinstance(decision_output.get("product"), dict) else {}
        listing_title = purchase_suggestion.get("product_name") or product_info.get("name") or selection_task.title
        description_parts = [
            f"选品任务: {selection_task.title}",
            f"目标市场: {selection_task.target_market}",
        ]
        core_features = product_info.get("core_features") if isinstance(product_info.get("core_features"), list) else []
        if core_features:
            description_parts.append("核心特性: " + " / ".join(str(item) for item in core_features[:5]))
        payload = {
            "task_id": str(selection_task.id),
            "sku": purchase_suggestion.get("sku") or f"SEL-{str(selection_task.id).split('-')[0].upper()}",
            "listing_draft_id": f"LST-{selection_task.id}",
            "title": listing_title,
            "description": "；".join(description_parts),
            "price": cls._coerce_number(pricing.get("recommended_price")) or purchase_suggestion.get("target_procurement_price") or 0,
            "image_url": product_info.get("image_url") or product_info.get("product_image") or "https://example.com/placeholder-product.png",
            "status": "pending_approval",
        }
        return cls._attach_audit_context(payload, audit_context)

    @staticmethod
    def _serialize_product(product: Any) -> dict[str, Any]:
        return {
            "id": str(product.id),
            "name": product.name,
            "brand": product.brand,
            "platform": product.platform,
            "external_product_id": product.external_product_id,
            "asin": product.asin,
            "price": product.price,
            "rating": product.rating,
            "review_count": product.review_count,
            "sales_rank": product.sales_rank,
        }

    @staticmethod
    def _serialize_product_plan(product: Any) -> dict[str, Any]:
        return {
            "product_id": str(product.id),
            "name": product.name,
            "brand": product.brand,
            "external_product_id": product.external_product_id,
            "target_procurement_price": product.price,
            "target_market": "US",
            "notes": "generated-from-selection-plan",
        }

    @staticmethod
    def _serialize_customer_followup(product: Any) -> dict[str, Any]:
        return {
            "product_id": str(product.id),
            "product_name": product.name,
            "customer_segment": "vip",
            "followup_type": "satisfaction-check",
            "notes": "generated-from-crm-plan",
        }

    @staticmethod
    def _serialize_replenishment_plan(product: Any) -> dict[str, Any]:
        inventory = (product.attributes or {}) if hasattr(product, "attributes") else {}
        current_stock = inventory.get("available_quantity") or 0
        safety_stock = inventory.get("safety_stock") or 10
        recommended = max(safety_stock * 2 - current_stock, safety_stock)
        return {
            "product_id": str(product.id),
            "product_name": product.name,
            "sku": product.external_product_id,
            "warehouse_id": inventory.get("warehouse_id") or "default-warehouse",
            "current_stock": current_stock,
            "safety_stock": safety_stock,
            "recommended_replenishment": recommended,
            "notes": "generated-from-wms-replenishment-plan",
        }

    @staticmethod
    def _serialize_profit_plan(product: Any) -> dict[str, Any]:
        return {
            "product_id": str(product.id),
            "product_name": product.name,
            "target_profit": product.price,
            "target_margin": product.rating,
            "notes": "generated-from-finance-plan",
        }

    @staticmethod
    def _serialize_config(config: Any) -> dict[str, Any]:
        return {
            "config_id": str(config.id),
            "system_type": config.system_type.value if hasattr(config.system_type, "value") else str(config.system_type),
            "name": config.name,
            "api_endpoint": config.api_endpoint,
            "is_active": config.is_active,
            "extra_config": config.extra_config or {},
        }

    @staticmethod
    def _serialize_log(log: Any, config: Any) -> dict[str, Any]:
        retryable = False
        error_code = None
        next_action = "monitor"
        run_id = None
        if log.error_detail:
            if log.error_detail.startswith("meta:"):
                try:
                    meta = json.loads(log.error_detail.split(":", 1)[1])
                    run_id = meta.get("run_id")
                except Exception:
                    run_id = None
            elif ":" in log.error_detail:
                error_code = log.error_detail.split(":", 1)[0]
                retryable = error_code in {"timeout", "transport_error", "upstream_5xx"}
                next_action = "retry" if retryable else "check_config"
        return {
            "log_id": str(log.id),
            "config_id": str(config.id),
            "system_type": config.system_type.value if hasattr(config.system_type, "value") else str(config.system_type),
            "config_name": config.name,
            "sync_type": log.sync_type,
            "entity_type": log.entity_type,
            "status": log.status,
            "items_total": log.items_total,
            "items_success": log.items_success,
            "items_failed": log.items_failed,
            "error_detail": log.error_detail,
            "error_code": error_code,
            "retryable": retryable,
            "next_action": next_action,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "finished_at": log.finished_at.isoformat() if log.finished_at else None,
            "duration_seconds": log.duration_seconds,
            "run_id": run_id,
        }
