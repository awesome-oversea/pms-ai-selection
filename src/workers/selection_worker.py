"""
选品任务 Worker（Phase 6 最小基线）
=================================

提供独立于 API 进程的待执行任务轮询与执行能力。
当前目标：
- 轮询 pending 任务
- 原子领取为 running
- 复用 SelectionTaskService.execute_task 执行
"""

from __future__ import annotations

import asyncio

from sqlalchemy import distinct, select
from src.config.settings import get_settings
from src.core.logging import get_logger
from src.core.metrics import (
    SELECTION_TASK_BACKLOG_GAUGE,
    SELECTION_TASK_RUNNING_GAUGE,
    SELECTION_TASK_THROTTLED_TOTAL,
)
from src.infrastructure.database import get_async_session_factory
from src.services.selection_service import SelectionTaskExecutionContext, SelectionTaskService

logger = get_logger(__name__)


async def run_worker(*, poll_interval_seconds: float | None = None, batch_size: int | None = None) -> None:
    """独立运行 Worker 的入口函数。"""
    worker = SelectionTaskWorker(poll_interval_seconds=poll_interval_seconds, batch_size=batch_size)
    await worker.run_forever()


class SelectionTaskWorker:
    """最小选品任务 Worker。"""

    def __init__(self, *, poll_interval_seconds: float | None = None, batch_size: int | None = None):
        settings = get_settings().selection_execution
        self.poll_interval_seconds = poll_interval_seconds or settings.worker_poll_interval_seconds
        self.batch_size = batch_size or settings.worker_batch_size
        self._running = False

    async def poll_and_run_once(self) -> int:
        """轮询一次并执行领取到的任务，返回处理数量。"""
        settings = get_settings().selection_execution
        factory = get_async_session_factory()
        claimed = []

        async with factory() as session:
            from src.models.models import SelectionTask

            tenant_rows = await session.execute(
                select(distinct(SelectionTask.tenant_id)).where(
                    SelectionTask.is_deleted == False,  # noqa: E712
                    SelectionTask.status == "pending",
                )
            )
            tenant_ids = [str(row[0]) for row in tenant_rows.fetchall() if row[0] is not None]
            remaining = self.batch_size

            for tenant_id in tenant_ids:
                repo_service = SelectionTaskService(session, tenant_id=tenant_id, actor={"roles": ["operator"], "tenant_id": tenant_id})
                running = await repo_service.repo.count_running_tasks_by_tenant(tenant_id)
                backlog = await repo_service.repo.count_backlog_tasks_by_tenant(tenant_id)
                SELECTION_TASK_RUNNING_GAUGE.labels(tenant_id=tenant_id).set(running)
                SELECTION_TASK_BACKLOG_GAUGE.labels(tenant_id=tenant_id).set(backlog)

                if backlog >= settings.queue_backlog_warning_threshold:
                    logger.warning(f"Selection backlog high: tenant={tenant_id} backlog={backlog}")

                if running >= settings.tenant_max_parallelism:
                    SELECTION_TASK_THROTTLED_TOTAL.labels(tenant_id=tenant_id, reason="tenant_parallelism").inc()
                    continue

                tenant_allowance = min(settings.tenant_max_parallelism - running, settings.task_type_max_parallelism, remaining)
                if tenant_allowance <= 0:
                    continue

                tenant_claimed = await repo_service.repo.claim_pending_tasks(limit=tenant_allowance, tenant_id=tenant_id)
                claimed.extend(tenant_claimed)
                remaining -= len(tenant_claimed)
                if remaining <= 0:
                    break

            await session.commit()

        processed = 0
        for task in claimed:
            config = task.config or {}
            context = SelectionTaskExecutionContext(
                task_id=str(task.id),
                tenant_id=str(task.tenant_id),
                query=task.title,
                category=task.target_category or "electronics",
                investment_budget=float(task.budget_max or 0.0),
                target_market=task.target_market or "US",
                auto_approve=bool(config.get("auto_approve", False)),
                priority=(task.priority.value if task.priority else "normal"),
            )
            factory = get_async_session_factory()
            async with factory() as execution_session:
                exec_service = SelectionTaskService(
                    execution_session,
                    tenant_id=context.tenant_id,
                    actor={"tenant_id": context.tenant_id, "roles": ["operator"]},
                )
                await exec_service.execute_task(context)
            processed += 1
        return processed

    async def run_forever(self) -> None:
        """持续运行 Worker。"""
        self._running = True
        logger.info(
            f"Selection worker started (poll={self.poll_interval_seconds}s, batch={self.batch_size})"
        )
        while self._running:
            processed = await self.poll_and_run_once()
            if processed == 0:
                await asyncio.sleep(self.poll_interval_seconds)

    def stop(self) -> None:
        self._running = False


def main() -> None:
    """命令行入口：python -m src.workers.selection_worker"""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
