from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.infrastructure.bi_client import BIClient
from src.models.enums import ERPSystemType
from src.repositories.erp_repository import ErpIntegrationRepository
from src.repositories.selection_repository import SelectionTaskRepository

logger = get_logger(__name__)


class BIDomainService:
    """
    BI 商业智能领域服务。

    职责:
    - 数据集推送（选品结果/执行反馈回流至BI）
    - 数据集读取（KPI/报表/仪表盘数据）
    - 日常KPI快照
    - 数据分析结果回流
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.repo = ErpIntegrationRepository(session, tenant_id=self.tenant_id) if session is not None else None
        self.selection_repo = SelectionTaskRepository(session, tenant_id=self.tenant_id) if session is not None else None

    async def push_selection_result(
        self,
        *,
        task_id: str,
        bi_name: str = "default",
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}

        dataset_payload: dict[str, Any] = {
            "task_id": task_id,
            "dataset_type": "selection_result",
            "title": selection_task.title,
            "status": selection_task.status,
            "config_snapshot": config,
            "pushed_at": datetime.now(UTC).isoformat(),
        }

        push_result: dict[str, Any] = {"status": "pending"}
        if self.repo is not None:
            try:
                bi_config = await self.repo.get_config(ERPSystemType.BI, name=bi_name)
                if bi_config is not None:
                    bi_client = self._build_bi_client(bi_config)
                    await bi_client.push_dataset(dataset_payload)
                    push_result = {"status": "pushed"}
            except Exception as e:
                logger.warning("BI选品结果推送失败: %s", e)
                push_result = {"status": "error", "error": str(e)}

        bi_data = config.get("bi") if isinstance(config.get("bi"), dict) else {}
        bi_data.setdefault("push_history", [])
        bi_data["push_history"].append({
            "dataset_type": "selection_result",
            "result": push_result,
            "pushed_at": dataset_payload["pushed_at"],
        })
        config["bi"] = bi_data
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "dataset_type": "selection_result",
            "push_status": push_result["status"],
        }

    async def push_execution_feedback(
        self,
        *,
        task_id: str,
        bi_name: str = "default",
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}

        execution_result = config.get("execution_result") if isinstance(config.get("execution_result"), dict) else {}
        dataset_payload: dict[str, Any] = {
            "task_id": task_id,
            "dataset_type": "execution_feedback",
            "execution_result": execution_result,
            "workflow_state": config.get("erp_workflow_state"),
            "pushed_at": datetime.now(UTC).isoformat(),
        }

        push_result: dict[str, Any] = {"status": "pending"}
        if self.repo is not None:
            try:
                bi_config = await self.repo.get_config(ERPSystemType.BI, name=bi_name)
                if bi_config is not None:
                    bi_client = self._build_bi_client(bi_config)
                    await bi_client.push_dataset(dataset_payload)
                    push_result = {"status": "pushed"}
            except Exception as e:
                logger.warning("BI执行反馈推送失败: %s", e)
                push_result = {"status": "error", "error": str(e)}

        bi_data = config.get("bi") if isinstance(config.get("bi"), dict) else {}
        bi_data.setdefault("push_history", [])
        bi_data["push_history"].append({
            "dataset_type": "execution_feedback",
            "result": push_result,
            "pushed_at": dataset_payload["pushed_at"],
        })
        config["bi"] = bi_data
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return {
            "task_id": task_id,
            "dataset_type": "execution_feedback",
            "push_status": push_result["status"],
        }

    async def read_kpi_dataset(
        self,
        *,
        task_id: str,
        bi_name: str = "default",
    ) -> dict[str, Any]:
        if self.repo is None:
            return {"task_id": task_id, "dataset": None, "error": "仓储未初始化"}

        try:
            bi_config = await self.repo.get_config(ERPSystemType.BI, name=bi_name)
            if bi_config is None:
                return {"task_id": task_id, "dataset": None, "error": "BI配置不存在"}

            bi_client = self._build_bi_client(bi_config)
            dataset = await bi_client.read_dataset()
            return {"task_id": task_id, "dataset": dataset}
        except Exception as e:
            logger.warning("BI KPI数据集读取失败: %s", e)
            return {"task_id": task_id, "dataset": None, "error": str(e)}

    async def get_bi_summary(self, task_id: str) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        bi_data = config.get("bi") if isinstance(config.get("bi"), dict) else {}

        push_history = bi_data.get("push_history") or []
        selection_pushes = [p for p in push_history if p.get("dataset_type") == "selection_result"]
        feedback_pushes = [p for p in push_history if p.get("dataset_type") == "execution_feedback"]

        return {
            "task_id": task_id,
            "total_pushes": len(push_history),
            "selection_result_pushes": len(selection_pushes),
            "execution_feedback_pushes": len(feedback_pushes),
            "last_push_at": push_history[-1].get("pushed_at") if push_history else None,
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
    def _build_bi_client(config: Any) -> BIClient:
        extra = config.extra_config or {}
        return BIClient(
            api_endpoint=config.api_endpoint,
            api_key=config.api_key,
            secret_key=config.secret_key,
            inbound_path=extra.get("inbound_path", "/datasets"),
            outbound_path=extra.get("outbound_path", "/kpis"),
            timeout_seconds=float(extra.get("timeout_seconds", 10.0)),
        )
