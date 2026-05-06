from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.infrastructure.pdm_client import PDMClient
from src.models.enums import ERPSystemType
from src.repositories.erp_repository import ErpIntegrationRepository
from src.repositories.selection_repository import SelectionTaskRepository

logger = get_logger(__name__)


class MasterDataService:
    """
    MS 商品主数据领域服务。

    职责:
    - 选品结果转商品草稿
    - 商品主档 CRUD
    - 产品定义与 SKU 管理
    - 商品生命周期状态管理
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.repo = ErpIntegrationRepository(session, tenant_id=self.tenant_id) if session is not None else None
        self.selection_repo = SelectionTaskRepository(session, tenant_id=self.tenant_id) if session is not None else None

    async def create_product_from_selection(
        self,
        *,
        task_id: str,
        pdm_name: str = "default",
        product_name: str | None = None,
        category: str | None = None,
        target_market: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        execution_result = config.get("execution_result") if isinstance(config, dict) else {}
        decision_output = execution_result.get("decision_output") if isinstance(execution_result, dict) else {}
        product_planning = decision_output.get("product_planning") if isinstance(decision_output, dict) else {}

        product_data = {
            "task_id": task_id,
            "product_name": product_name or product_planning.get("product_name") or selection_task.title,
            "category": category or selection_task.target_category,
            "target_market": target_market or selection_task.target_market,
            "status": "draft",
            "lifecycle_state": "draft",
            "source": "selection",
            "tenant_id": self.tenant_id,
            "created_at": datetime.now(UTC).isoformat(),
            "product_definition": {
                "specifications": product_planning.get("specifications") or {},
                "differentiation": product_planning.get("differentiation"),
                "target_audience": product_planning.get("target_audience"),
            },
            "pricing": {
                "recommended_price": (decision_output.get("pricing") or {}).get("recommended_price") if isinstance(decision_output, dict) else None,
                "cost_estimate": (decision_output.get("supply_chain") or {}).get("estimated_cost") if isinstance(decision_output, dict) else None,
            },
            "sku_template": {
                "category": category or selection_task.target_category,
                "market": target_market or selection_task.target_market,
            },
            "notes": notes,
        }

        if self.repo is not None:
            pdm_config = await self.repo.get_config(ERPSystemType.PDM, name=pdm_name)
            if pdm_config is not None:
                pdm_client = self._build_pdm_client(pdm_config)
                audit_context = self._build_audit_context(
                    task_id=task_id,
                    domain="ms",
                    purpose="create_product_from_selection",
                )
                receipt = await pdm_client.submit_selection_recommendation(
                    product_data,
                    audit_context=audit_context,
                )
                product_data["pdm_receipt"] = receipt
                product_data["recommendation_id"] = receipt.get("recommendation_id")

        config.setdefault("ms", {})
        config["ms"]["product_draft"] = product_data
        config["ms"]["product_draft_created_at"] = datetime.now(UTC).isoformat()
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "product_id": product_data.get("recommendation_id") or f"PROD-{task_id[:8]}",
            "product_name": product_data["product_name"],
            "status": "draft",
            "lifecycle_state": "draft",
            "source": "selection",
            "category": product_data["category"],
            "target_market": product_data["target_market"],
        }

    async def get_product(self, task_id: str) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        ms_data = config.get("ms") if isinstance(config.get("ms"), dict) else {}
        product_draft = ms_data.get("product_draft") if isinstance(ms_data.get("product_draft"), dict) else None
        if product_draft is None:
            return {
                "task_id": task_id,
                "exists": False,
                "status": "not_created",
            }
        return {
            "task_id": task_id,
            "exists": True,
            "product_id": product_draft.get("recommendation_id") or f"PROD-{task_id[:8]}",
            "product_name": product_draft.get("product_name"),
            "status": product_draft.get("status"),
            "lifecycle_state": product_draft.get("lifecycle_state"),
            "category": product_draft.get("category"),
            "target_market": product_draft.get("target_market"),
            "created_at": product_draft.get("created_at"),
        }

    async def update_product_lifecycle(
        self,
        task_id: str,
        *,
        lifecycle_state: str,
    ) -> dict[str, Any]:
        valid_states = {"draft", "pending_review", "approved", "active", "discontinued", "archived"}
        if lifecycle_state not in valid_states:
            raise ValueError(f"无效的生命周期状态: {lifecycle_state}，有效值: {valid_states}")

        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        ms_data = config.get("ms") if isinstance(config.get("ms"), dict) else {}
        product_draft = ms_data.get("product_draft") if isinstance(ms_data.get("product_draft"), dict) else None
        if product_draft is None:
            raise ValueError("商品草稿不存在，请先创建商品")

        previous_state = product_draft.get("lifecycle_state")
        product_draft["lifecycle_state"] = lifecycle_state
        product_draft["lifecycle_updated_at"] = datetime.now(UTC).isoformat()
        product_draft["previous_lifecycle_state"] = previous_state
        config["ms"]["product_draft"] = product_draft
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "product_id": product_draft.get("recommendation_id") or f"PROD-{task_id[:8]}",
            "previous_state": previous_state,
            "current_state": lifecycle_state,
            "updated_at": product_draft["lifecycle_updated_at"],
        }

    async def create_product_definitions(
        self,
        task_id: str,
        *,
        definitions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        config.setdefault("ms", {})
        existing_definitions = config["ms"].get("product_definitions") or []
        created: list[dict[str, Any]] = []
        for definition in definitions:
            entry = {
                "definition_id": f"PD-{uuid4().hex[:12]}",
                "task_id": task_id,
                "sku_base": definition.get("sku_base"),
                "attributes": definition.get("attributes") or {},
                "variants": definition.get("variants") or [],
                "status": "draft",
                "created_at": datetime.now(UTC).isoformat(),
            }
            existing_definitions.append(entry)
            created.append(entry)
        config["ms"]["product_definitions"] = existing_definitions
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()
        return {
            "task_id": task_id,
            "created_count": len(created),
            "definitions": created,
        }

    async def _get_selection_task(self, task_id: str) -> Any:
        if self.selection_repo is None:
            raise ValueError("选品任务仓储未初始化")
        from uuid import UUID
        try:
            normalized_task_id: Any = UUID(str(task_id))
        except ValueError:
            normalized_task_id = task_id
        task = await self.selection_repo.get_task(normalized_task_id)
        if task is None:
            raise ValueError(f"选品任务不存在: {task_id}")
        return task

    @staticmethod
    def _build_pdm_client(config: Any) -> PDMClient:
        extra = config.extra_config or {}
        return PDMClient(
            api_endpoint=config.api_endpoint,
            api_key=config.api_key,
            secret_key=config.secret_key,
            inbound_path=extra.get("inbound_path", "/selection-recommendations"),
            outbound_path=extra.get("outbound_path", "/product-drafts"),
            timeout_seconds=float(extra.get("timeout_seconds", 10.0)),
        )

    @staticmethod
    def _build_audit_context(*, task_id: str, domain: str, purpose: str) -> dict[str, Any]:
        return {
            "tenant_id": "system",
            "actor_type": "service",
            "actor_id": "pms-ms-service",
            "domain": domain,
            "purpose": purpose,
            "trace_id": f"ms-{task_id}",
            "idempotency_key": f"ms-{purpose}-{task_id}",
        }
