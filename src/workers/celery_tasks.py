"""
Celery异步任务定义
==================

定义所有异步任务:
    - execute_selection_task: 选品任务异步执行
    - execute_adoption_task: 采纳推荐异步编排
    - process_feedback_data: 数据回流异步处理
    - generate_report_task: 报告异步生成
    - update_feature_store: 特征库异步更新
    - update_vector_store: 向量库异步更新
    - update_knowledge_base: 知识库异步更新

每个任务都是独立可追踪的Celery Task，支持重试、超时和结果存储。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from src.core.logging import get_logger
from src.workers.celery_app import celery_app
from src.workers.celery_schedule_monitor import record_schedule_run

logger = get_logger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="src.workers.celery_tasks.execute_selection_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def execute_selection_task(self, task_id: str, tenant_id: str, query: str, category: str = "electronics", target_market: str = "US", investment_budget: float = 0.0, priority: str = "normal") -> dict[str, Any]:
    logger.info(f"[Celery] 开始执行选品任务: task_id={task_id}, tenant_id={tenant_id}")

    async def _execute():
        from src.infrastructure.database import get_async_session_factory
        from src.services.selection_service import SelectionTaskExecutionContext, SelectionTaskService

        factory = get_async_session_factory()
        async with factory() as session:
            service = SelectionTaskService(
                session,
                tenant_id=tenant_id,
                actor={"tenant_id": tenant_id, "roles": ["operator"]},
            )
            context = SelectionTaskExecutionContext(
                task_id=task_id,
                tenant_id=tenant_id,
                query=query,
                category=category,
                investment_budget=investment_budget,
                target_market=target_market,
                auto_approve=False,
                priority=priority,
            )
            await service.execute_task(context)
            await session.commit()
        return {"task_id": task_id, "status": "completed", "completed_at": datetime.now(UTC).isoformat()}

    try:
        result = _run_async(_execute())
        record_schedule_run(
            entry_name="scheduled-selection-hourly",
            task_name="src.workers.celery_tasks.execute_selection_task",
            queue_name="selection",
            status="success",
            detail={"task_id": task_id, "tenant_id": tenant_id, "query": query},
        )
        logger.info(f"[Celery] 选品任务完成: task_id={task_id}")
        return result
    except Exception as exc:
        record_schedule_run(
            entry_name="scheduled-selection-hourly",
            task_name="src.workers.celery_tasks.execute_selection_task",
            queue_name="selection",
            status="failed",
            detail={"task_id": task_id, "tenant_id": tenant_id, "error": str(exc)},
        )
        logger.error(f"[Celery] 选品任务失败: task_id={task_id}, error={exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.workers.celery_tasks.execute_adoption_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def execute_adoption_task(self, task_id: str, tenant_id: str, scm_name: str = "default", wms_name: str = "default", oms_name: str = "default", quantity: int = 200, supplier_code: str = "", notes: str = "") -> dict[str, Any]:
    logger.info(f"[Celery] 开始执行采纳推荐: task_id={task_id}, tenant_id={tenant_id}")

    async def _execute():
        from src.infrastructure.database import get_async_session_factory
        from src.services.erp_integration_service import ErpIntegrationService

        factory = get_async_session_factory()
        async with factory() as session:
            service = ErpIntegrationService(
                session,
                tenant_id=tenant_id,
                actor={"tenant_id": tenant_id, "roles": ["operator"]},
            )
            result = await service.execute_selection_adoption(
                task_id=task_id,
                scm_name=scm_name,
                wms_name=wms_name,
                oms_name=oms_name,
                quantity=quantity,
                supplier_code=supplier_code or None,
                notes=notes or None,
            )
            await session.commit()
        return result

    try:
        result = _run_async(_execute())
        logger.info(f"[Celery] 采纳推荐完成: task_id={task_id}")
        return result
    except Exception as exc:
        logger.error(f"[Celery] 采纳推荐失败: task_id={task_id}, error={exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.workers.celery_tasks.process_feedback_data",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
    acks_late=True,
)
def process_feedback_data(self, task_id: str, tenant_id: str, feedback_type: str = "all", limit: int = 100) -> dict[str, Any]:
    logger.info(f"[Celery] 开始处理数据回流: task_id={task_id}, type={feedback_type}")

    async def _execute():
        from src.infrastructure.database import get_async_session_factory
        from src.services.erp_integration_service import ErpIntegrationService

        factory = get_async_session_factory()
        async with factory() as session:
            service = ErpIntegrationService(
                session,
                tenant_id=tenant_id,
                actor={"tenant_id": tenant_id, "roles": ["system"]},
            )
            result = await service.close_selection_loop(
                task_id=task_id,
                oms_name="default",
                scm_name="default",
                wms_name="default",
                crm_name="default",
                fms_name="default",
                limit=limit,
            )
            await session.commit()
        return result

    try:
        result = _run_async(_execute())
        logger.info(f"[Celery] 数据回流完成: task_id={task_id}")
        return result
    except Exception as exc:
        logger.error(f"[Celery] 数据回流失败: task_id={task_id}, error={exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.workers.celery_tasks.run_local_feedback_loop_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def run_local_feedback_loop_task(self, task_id: str, tenant_id: str = "default") -> dict[str, Any]:
    logger.info(f"[Celery] 开始本地反馈闭环: task_id={task_id}, tenant_id={tenant_id}")

    async def _execute():
        from src.services.local_feedback_loop_service import LocalFeedbackLoopService

        service = LocalFeedbackLoopService(topic="pms-agent-event")
        return await service.run_local_loop(task_id=task_id)

    try:
        result = _run_async(_execute())
        record_schedule_run(
            entry_name="local-feedback-loop-every-30-minutes",
            task_name="src.workers.celery_tasks.run_local_feedback_loop_task",
            queue_name="feedback",
            status="success",
            detail={"task_id": task_id, "tenant_id": tenant_id},
        )
        logger.info(f"[Celery] 本地反馈闭环完成: task_id={task_id}")
        return result
    except Exception as exc:
        record_schedule_run(
            entry_name="local-feedback-loop-every-30-minutes",
            task_name="src.workers.celery_tasks.run_local_feedback_loop_task",
            queue_name="feedback",
            status="failed",
            detail={"task_id": task_id, "tenant_id": tenant_id, "error": str(exc)},
        )
        logger.error(f"[Celery] 本地反馈闭环失败: task_id={task_id}, error={exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.workers.celery_tasks.compute_bi_kpi_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def compute_bi_kpi_task(self, tenant_id: str = "default", day: str | None = None) -> dict[str, Any]:
    logger.info(f"[Celery] 开始BI KPI定时计算: tenant_id={tenant_id}, day={day}")

    async def _execute():
        from src.workers.bi_kpi_worker import BIDailyKpiWorker

        worker = BIDailyKpiWorker(interval_seconds=86400.0, bootstrap_delay_seconds=0.0)
        return await worker.run_once(day=day)

    try:
        result = _run_async(_execute())
        record_schedule_run(
            entry_name="bi-kpi-daily",
            task_name="src.workers.celery_tasks.compute_bi_kpi_task",
            queue_name="feedback",
            status="success",
            detail={"tenant_id": tenant_id, "day": day},
        )
        logger.info("[Celery] BI KPI定时计算完成")
        return result
    except Exception as exc:
        record_schedule_run(
            entry_name="bi-kpi-daily",
            task_name="src.workers.celery_tasks.compute_bi_kpi_task",
            queue_name="feedback",
            status="failed",
            detail={"tenant_id": tenant_id, "day": day, "error": str(exc)},
        )
        logger.error(f"[Celery] BI KPI定时计算失败: error={exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.workers.celery_tasks.generate_report_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def generate_report_task(self, task_id: str, tenant_id: str, query: str, category: str = "", target_market: str = "US", report_format: str = "json") -> dict[str, Any]:
    logger.info(f"[Celery] 开始生成报告: task_id={task_id}")

    async def _execute():
        from src.agents.report_generator import ReportGeneratorAgent

        agent = ReportGeneratorAgent(config={"tenant_id": tenant_id})
        agent_result = await agent.run({
            "query": query,
            "category": category,
            "target_market": target_market,
            "task_id": task_id,
            "format": report_format,
        })
        return agent_result.output if hasattr(agent_result, "output") else agent_result

    try:
        result = _run_async(_execute())
        logger.info(f"[Celery] 报告生成完成: task_id={task_id}")
        return result
    except Exception as exc:
        logger.error(f"[Celery] 报告生成失败: task_id={task_id}, error={exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.workers.celery_tasks.update_feature_store",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def update_feature_store(self, task_id: str, tenant_id: str, feature_data: dict[str, Any] | None = None) -> dict[str, Any]:
    logger.info(f"[Celery] 开始更新特征库: task_id={task_id}")

    async def _execute():
        from src.infrastructure.database import get_async_session_factory
        from src.services.erp_integration_service import ErpIntegrationService

        factory = get_async_session_factory()
        async with factory() as session:
            service = ErpIntegrationService(
                session,
                tenant_id=tenant_id,
                actor={"tenant_id": tenant_id, "roles": ["system"]},
            )
            result = await service.export_feature_asset(task_id=task_id)
            await session.commit()
        return result

    try:
        result = _run_async(_execute())
        logger.info(f"[Celery] 特征库更新完成: task_id={task_id}")
        return result
    except Exception as exc:
        logger.error(f"[Celery] 特征库更新失败: task_id={task_id}, error={exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.workers.celery_tasks.update_vector_store",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def update_vector_store(self, task_id: str, tenant_id: str, documents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    logger.info(f"[Celery] 开始更新向量库: task_id={task_id}")

    async def _execute():
        from src.infrastructure.qdrant import get_qdrant_client

        client = get_qdrant_client()
        collection_name = f"pms_{tenant_id}_selection"

        if documents:
            from src.services.embedding import EmbeddingService
            embedder = EmbeddingService()
            points = []
            for i, doc in enumerate(documents):
                text = doc.get("content", "")
                if not text:
                    continue
                vector = await embedder.embed_text(text)
                points.append({
                    "id": doc.get("id", f"vec-{task_id}-{i}"),
                    "vector": vector,
                    "payload": {
                        "task_id": task_id,
                        "source": doc.get("source", "feedback"),
                        "content": text[:500],
                        "created_at": datetime.now(UTC).isoformat(),
                    },
                })
            if points:
                await client.upsert(collection_name=collection_name, points=points)

        return {"task_id": task_id, "status": "vector_updated", "documents_count": len(documents or [])}

    try:
        result = _run_async(_execute())
        logger.info(f"[Celery] 向量库更新完成: task_id={task_id}")
        return result
    except Exception as exc:
        logger.error(f"[Celery] 向量库更新失败: task_id={task_id}, error={exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.workers.celery_tasks.update_knowledge_base",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def update_knowledge_base(self, task_id: str, tenant_id: str, knowledge_entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    logger.info(f"[Celery] 开始更新知识库: task_id={task_id}")

    async def _execute():
        from src.infrastructure.database import get_async_session_factory
        from src.services.knowledge_service import KnowledgeService

        factory = get_async_session_factory()
        async with factory() as session:
            service = KnowledgeService(session, tenant_id=tenant_id)
            created_count = 0
            if knowledge_entries:
                for entry in knowledge_entries:
                    try:
                        if entry.get("case_type") == "crm_review_case":
                            await service.ingest_review_case(entry)
                        else:
                            filename = entry.get("filename") or f"knowledge_{task_id}_{created_count + 1}.md"
                            content = str(entry.get("content") or "").encode("utf-8")
                            await service.upload_document(filename, content)
                        created_count += 1
                    except Exception as e:
                        logger.warning(f"知识条目创建失败: {e}")
            await session.commit()
        return {"task_id": task_id, "status": "knowledge_updated", "entries_created": created_count}

    try:
        result = _run_async(_execute())
        logger.info(f"[Celery] 知识库更新完成: task_id={task_id}")
        return result
    except Exception as exc:
        logger.error(f"[Celery] 知识库更新失败: task_id={task_id}, error={exc}")
        raise self.retry(exc=exc)
