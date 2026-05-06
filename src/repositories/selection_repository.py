"""
选品任务 Repository
===================

提供 SelectionTask / AgentRun 的异步 CRUD 操作，
封装 SQLAlchemy 查询细节，供 API 层直接调用。

使用方式:
    from src.repositories.selection_repository import SelectionTaskRepository

    async with get_async_session() as session:
        repo = SelectionTaskRepository(session)
        task = await repo.create_task(title="分析蓝牙耳机", category="bluetooth_earbuds")
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.enums import TaskPriority, TaskStatus
from src.repositories.base import TenantScopedRepository

logger = get_logger(__name__)


class SelectionTaskRepository(TenantScopedRepository):
    """
    选品任务数据访问层。

    封装 SelectionTask 和 AgentRun 的所有数据库操作:
        - create_task: 创建选品任务
        - get_task: 按 ID 获取任务
        - list_tasks: 分页查询任务列表
        - update_task_status: 更新任务状态
        - save_task_result: 保存任务执行结果
        - create_agent_run: 创建 Agent 运行记录
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None):
        super().__init__(session, tenant_id=tenant_id, require_tenant=True)

    @staticmethod
    def _is_transition_allowed(current_status: TaskStatus, next_status: TaskStatus) -> bool:
        """校验任务状态流转是否合法(V11 6态)。"""
        allowed_transitions: dict[TaskStatus, set[TaskStatus]] = {
            TaskStatus.PENDING: {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
            TaskStatus.RUNNING: {TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
            TaskStatus.PAUSED: {TaskStatus.PAUSED, TaskStatus.RUNNING, TaskStatus.CANCELLED},
            TaskStatus.COMPLETED: {TaskStatus.COMPLETED},
            TaskStatus.FAILED: {TaskStatus.FAILED},
            TaskStatus.CANCELLED: {TaskStatus.CANCELLED},
        }
        return next_status in allowed_transitions.get(current_status, {current_status})

    async def create_task(
        self,
        title: str,
        category: str,
        target_market: str = "US",
        budget_min: float | None = None,
        budget_max: float | None = None,
        description: str | None = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        config: dict | None = None,
        created_by: uuid.UUID | None = None,
        tenant_id: str | None = None,
    ) -> Any:
        """
        创建选品任务。

        Returns:
            SelectionTask: 新创建的任务 ORM 实例
        """
        from src.models.models import SelectionTask

        tenant_id = tenant_id or self.tenant_id
        if tenant_id is None:
            raise ValueError("tenant_id 不能为空")

        task = SelectionTask(
            tenant_id=uuid.UUID(str(tenant_id)),
            title=title,
            description=description or f"选品分析: {category} ({target_market})",
            status=TaskStatus.PENDING,
            priority=priority,
            target_market=target_market,
            target_category=category,
            budget_min=budget_min,
            budget_max=budget_max,
            config=config or {},
            created_by=created_by,
        )
        self.session.add(task)
        await self.session.flush()
        logger.info(f"✅ 创建选品任务: {task.id} - {title}")
        return task

    async def get_task(self, task_id: uuid.UUID, tenant_id: str | None = None) -> Any | None:
        """按 ID 获取选品任务。"""
        from src.models.models import SelectionTask

        tenant_id = tenant_id or self.tenant_id
        query = select(SelectionTask).where(
            SelectionTask.id == task_id,
            SelectionTask.is_deleted == False,  # noqa: E712
        )
        if tenant_id is not None:
            query = query.where(SelectionTask.tenant_id == uuid.UUID(str(tenant_id)))

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        limit: int = 20,
        offset: int = 0,
        cursor: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[list[Any], int]:
        """
        分页查询任务列表。

        支持两种分页模式:
            - 游标分页 (cursor): 传入上一页最后一条记录的 created_at ISO 字符串，
              使用 WHERE created_at < cursor 实现高效翻页。
            - OFFSET 分页 (offset): 兼容旧接口，不推荐用于大数据集。

        Args:
            status: 按状态过滤
            limit: 每页数量
            offset: 偏移量（游标模式下忽略）
            cursor: 游标值（上一页最后一条的 created_at ISO 字符串）

        Returns:
            (tasks, total_count) 元组
        """
        from src.models.models import SelectionTask

        query = select(SelectionTask).where(
            SelectionTask.is_deleted == False  # noqa: E712
        )
        count_query = select(func.count()).select_from(SelectionTask).where(
            SelectionTask.is_deleted == False  # noqa: E712
        )

        tenant_id = tenant_id or self.tenant_id
        if tenant_id is not None:
            tenant_uuid = uuid.UUID(str(tenant_id))
            query = query.where(SelectionTask.tenant_id == tenant_uuid)
            count_query = count_query.where(SelectionTask.tenant_id == tenant_uuid)

        if status is not None:
            query = query.where(SelectionTask.status == status)
            count_query = count_query.where(SelectionTask.status == status)

        if cursor is not None:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
                query = query.where(SelectionTask.created_at < cursor_dt)
            except (ValueError, TypeError):
                pass

        query = query.order_by(SelectionTask.created_at.desc())

        if cursor is None:
            query = query.limit(limit).offset(offset)
        else:
            query = query.limit(limit)

        result = await self.session.execute(query)
        tasks = list(result.scalars().all())

        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        return tasks, total

    async def list_tasks_stream(
        self,
        status: TaskStatus | None = None,
        batch_size: int = 100,
        tenant_id: str | None = None,
    ):
        """
        流式加载任务列表（大数据集优化）。

        使用 yield_per() 避免一次加载全部记录到内存。

        Args:
            status: 按状态过滤
            batch_size: 每批加载数量
            tenant_id: 可选租户ID，默认使用仓储上下文租户

        Yields:
            SelectionTask 实例
        """
        from src.models.models import SelectionTask

        query = select(SelectionTask).where(
            SelectionTask.is_deleted == False  # noqa: E712
        )
        tenant_id = tenant_id or self.tenant_id
        if tenant_id is not None:
            query = query.where(SelectionTask.tenant_id == uuid.UUID(str(tenant_id)))
        if status is not None:
            query = query.where(SelectionTask.status == status)
        query = query.order_by(SelectionTask.created_at.desc())

        result = await self.session.stream(query)
        async for row in result.scalars().yield_per(batch_size):
            yield row

    async def count_running_tasks_by_tenant(self, tenant_id: str | None = None) -> int:
        from src.models.models import SelectionTask

        tenant_uuid = self.tenant_uuid(tenant_id)
        stmt = select(func.count()).select_from(SelectionTask).where(
            SelectionTask.is_deleted == False,  # noqa: E712
            SelectionTask.tenant_id == tenant_uuid,
            SelectionTask.status == TaskStatus.RUNNING,
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def count_backlog_tasks_by_tenant(self, tenant_id: str | None = None) -> int:
        from src.models.models import SelectionTask

        tenant_uuid = self.tenant_uuid(tenant_id)
        stmt = select(func.count()).select_from(SelectionTask).where(
            SelectionTask.is_deleted == False,  # noqa: E712
            SelectionTask.tenant_id == tenant_uuid,
            SelectionTask.status == TaskStatus.PENDING,
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def claim_pending_tasks(self, limit: int = 1, *, tenant_id: str | None = None) -> list[Any]:
        """领取待执行任务并原子更新为 RUNNING。"""
        from src.models.models import SelectionTask

        tenant_uuid = self.tenant_uuid(tenant_id) if (tenant_id or self.tenant_id) is not None else None
        query = (
            select(SelectionTask)
            .where(
                SelectionTask.is_deleted == False,  # noqa: E712
                SelectionTask.status == TaskStatus.PENDING,
            )
            .order_by(SelectionTask.priority.desc(), SelectionTask.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        if tenant_uuid is not None:
            query = query.where(SelectionTask.tenant_id == tenant_uuid)

        result = await self.session.execute(query)
        tasks = list(result.scalars().all())
        now = datetime.now(UTC)
        for task in tasks:
            config = task.config or {}
            history = list(config.get("status_history", []))
            history.append(
                {
                    "from": task.status.value if task.status else None,
                    "to": TaskStatus.RUNNING.value,
                    "phase": "queued",
                    "reason": "worker claimed",
                    "timestamp": now.isoformat(),
                }
            )
            config["status_history"] = history[-100:]
            config["phase"] = "queued"
            config["status_reason"] = "Worker 已领取，等待执行"
            config["updated_at"] = now.isoformat()
            task.status = TaskStatus.RUNNING
            task.result_summary = "Worker 已领取，等待执行"
            task.config = config
        await self.session.flush()
        return tasks

    async def requeue_task(self, task_id: uuid.UUID, reason: str, *, reset_dead_letter: bool = False) -> bool:
        """将失败/死信任务重新入队为 pending。"""
        task = await self.get_task(task_id)
        if task is None:
            return False

        current_status = task.status or TaskStatus.PENDING
        now = datetime.now(UTC)
        config = task.config or {}
        history = list(config.get("status_history", []))
        history.append(
            {
                "from": current_status.value if current_status else None,
                "to": TaskStatus.PENDING.value,
                "phase": "requeued",
                "reason": reason,
                "timestamp": now.isoformat(),
            }
        )
        config["status_history"] = history[-100:]
        config["phase"] = "pending"
        config["status_reason"] = reason
        config["updated_at"] = now.isoformat()
        config["last_error"] = None
        config["timed_out"] = False
        if reset_dead_letter:
            config["dead_letter"] = False
            config["dead_letter_reason"] = None
            config["dead_lettered_at"] = None
        task.status = TaskStatus.PENDING
        task.result_summary = reason
        task.config = config
        await self.session.flush()
        return True

    async def list_dead_letter_tasks(self, limit: int = 20, offset: int = 0) -> tuple[list[Any], int]:
        """查询当前租户下已进入死信队列的任务。"""
        from src.models.models import SelectionTask

        query = select(SelectionTask).where(
            SelectionTask.is_deleted == False,  # noqa: E712
            SelectionTask.tenant_id == self.tenant_uuid(),
            SelectionTask.status == TaskStatus.FAILED,
            SelectionTask.config["dead_letter"].astext == "true",
        )
        count_query = select(func.count()).select_from(SelectionTask).where(
            SelectionTask.is_deleted == False,  # noqa: E712
            SelectionTask.tenant_id == self.tenant_uuid(),
            SelectionTask.status == TaskStatus.FAILED,
            SelectionTask.config["dead_letter"].astext == "true",
        )
        query = query.order_by(SelectionTask.updated_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        tasks = list(result.scalars().all())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0
        return tasks, total

    async def update_task_status(
        self,
        task_id: uuid.UUID,
        status: TaskStatus,
        result_summary: str | None = None,
        phase: str | None = None,
        reason: str | None = None,
    ) -> bool:
        """
        更新任务状态。

        Returns:
            bool: 是否更新成功
        """
        task = await self.get_task(task_id)
        if task is None:
            return False

        current_status = task.status or TaskStatus.PENDING
        if not self._is_transition_allowed(current_status, status):
            raise ValueError(f"非法状态流转: {current_status.value} -> {status.value}")

        now = datetime.now(UTC)
        task.status = status
        if result_summary is not None:
            task.result_summary = result_summary
        if status == TaskStatus.COMPLETED:
            task.completed_at = now

        config = task.config or {}
        history = list(config.get("status_history", []))
        history.append(
            {
                "from": current_status.value if current_status else None,
                "to": status.value,
                "phase": phase,
                "reason": reason or result_summary,
                "timestamp": now.isoformat(),
            }
        )
        config["status_history"] = history[-100:]
        if phase is not None:
            config["phase"] = phase
        if reason is not None:
            config["status_reason"] = reason
        config["updated_at"] = now.isoformat()
        task.config = config

        await self.session.flush()
        return True

    async def save_task_result(
        self,
        task_id: uuid.UUID,
        result_data: dict[str, Any],
    ) -> bool:
        """
        保存任务执行结果到 config 字段（JSONB）。

        Returns:
            bool: 是否保存成功
        """
        task = await self.get_task(task_id)
        if task is None:
            return False

        existing_config = task.config or {}
        existing_config["execution_result"] = result_data
        existing_config["updated_at"] = datetime.now(UTC).isoformat()
        task.config = existing_config
        await self.session.flush()
        return True

    async def delete_task(self, task_id: uuid.UUID) -> bool:
        """
        软删除选品任务。

        Returns:
            bool: 是否删除成功
        """
        task = await self.get_task(task_id)
        if task is None:
            return False

        task.is_deleted = True
        await self.session.flush()
        logger.info(f"🗑️ 选品任务已软删除: {task_id}")
        return True

    async def create_agent_run(
        self,
        task_id: uuid.UUID,
        agent_type: str,
        input_data: dict | None = None,
        output_data: dict | None = None,
        status: str = "completed",
        duration_seconds: float | None = None,
        error_message: str | None = None,
    ) -> Any:
        """
        创建 Agent 运行记录。

        Returns:
            AgentRun: 新创建的运行记录
        """
        from src.models.enums import AgentStatus
        from src.models.enums import AgentType as AgentTypeEnum
        from src.models.models import AgentRun

        type_map = {
            "data_collection": AgentTypeEnum.DATA_COLLECTOR,
            "market_insight": AgentTypeEnum.MARKET_INSIGHT,
            "product_planner": AgentTypeEnum.PRODUCT_PLANNER,
            "commercial": AgentTypeEnum.COMMERCIALIZATION,
        }
        status_map = {
            "completed": AgentStatus.COMPLETED,
            "failed": AgentStatus.ERROR,
            "running": AgentStatus.PROCESSING,
            "pending": AgentStatus.IDLE,
        }

        task = await self.get_task(task_id, tenant_id=self.tenant_id)
        if task is None:
            raise ValueError(f"任务不存在或不属于当前租户: {task_id}")

        run = AgentRun(
            tenant_id=task.tenant_id,
            task_id=task_id,
            agent_type=type_map.get(agent_type, AgentTypeEnum.DATA_COLLECTOR),
            status=status_map.get(status, AgentStatus.COMPLETED),
            input_data=input_data or {},
            output_data=output_data or {},
            error_message=error_message,
            duration_seconds=duration_seconds,
        )
        self.session.add(run)
        await self.session.flush()
        logger.info(f"📝 Agent运行记录: task={task_id}, agent={agent_type}, status={status}")
        return run
