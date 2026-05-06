from __future__ import annotations

import asyncio
from typing import Any

from src.core.logging import get_logger
from src.infrastructure.celery_app import celery_app
from src.infrastructure.database import get_async_session_factory
from src.services.selection_service import SelectionTaskExecutionContext, SelectionTaskService

logger = get_logger(__name__)


async def _run_selection_task_async(payload: dict[str, Any]) -> dict[str, Any]:
    context = SelectionTaskExecutionContext(**payload)
    factory = get_async_session_factory()
    async with factory() as session:
        service = SelectionTaskService(
            session=session,
            tenant_id=context.tenant_id,
            actor={"tenant_id": context.tenant_id, "roles": ["operator"]} if context.tenant_id else None,
        )
        await service.execute_task(context)
        await session.commit()
    return {
        "task_id": context.task_id,
        "tenant_id": context.tenant_id,
        "status": "submitted_to_execution",
    }


@celery_app.task(name="selection.execute_task")
def execute_selection_task(payload: dict[str, Any]) -> dict[str, Any]:
    logger.info(f"Celery received selection task: {payload.get('task_id')}")
    return asyncio.run(_run_selection_task_async(payload))
