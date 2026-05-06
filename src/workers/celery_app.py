"""
Celery异步任务队列配置
=====================

基于Celery + Redis Broker实现异步任务处理:
    - 选品任务异步执行
    - 采纳推荐异步编排
    - 数据回流异步处理
    - 报告异步生成

设计文档要求: Celery + Redis Broker + 多Worker并发

启动方式:
    celery -A src.workers.celery_app worker --loglevel=info --pool=solo -Q selection,adoption,feedback,report
"""

from __future__ import annotations

from celery import Celery
from kombu import Queue
from src.config.business_defaults import (
    get_feedback_schedule_config,
    get_kpi_schedule_config,
    get_scheduled_selection_config,
)
from src.config.settings import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


DEFAULT_SCHEDULED_SELECTION = get_scheduled_selection_config()
DEFAULT_SCHEDULED_FEEDBACK = get_feedback_schedule_config()
DEFAULT_SCHEDULED_KPI = get_kpi_schedule_config()


def _build_celery_app() -> Celery:
    settings = get_settings()
    broker_url = settings.redis.url
    result_backend = settings.redis.url

    app = Celery(
        "pms_selection",
        broker=broker_url,
        backend=result_backend,
    )

    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        result_expires=3600,
        task_soft_time_limit=600,
        task_time_limit=900,
        task_queues=(
            Queue("selection", routing_key="selection"),
            Queue("adoption", routing_key="adoption"),
            Queue("feedback", routing_key="feedback"),
            Queue("report", routing_key="report"),
            Queue("default", routing_key="default"),
        ),
        task_default_queue="default",
        task_default_routing_key="default",
        task_routes={
            "src.workers.celery_tasks.execute_selection_task": {"queue": "selection"},
            "src.workers.celery_tasks.execute_adoption_task": {"queue": "adoption"},
            "src.workers.celery_tasks.process_feedback_data": {"queue": "feedback"},
            "src.workers.celery_tasks.run_local_feedback_loop_task": {"queue": "feedback"},
            "src.workers.celery_tasks.compute_bi_kpi_task": {"queue": "feedback"},
            "src.workers.celery_tasks.generate_report_task": {"queue": "report"},
        },
        beat_schedule={
            "scheduled-selection-hourly": {
                "task": "src.workers.celery_tasks.execute_selection_task",
                "schedule": 3600.0,
                "args": [
                    DEFAULT_SCHEDULED_SELECTION["task_id"],
                    DEFAULT_SCHEDULED_SELECTION["tenant_id"],
                    DEFAULT_SCHEDULED_SELECTION["query"],
                    DEFAULT_SCHEDULED_SELECTION["category"],
                    DEFAULT_SCHEDULED_SELECTION["market"],
                    DEFAULT_SCHEDULED_SELECTION["budget"],
                    "normal",
                ],
            },
            "local-feedback-loop-every-30-minutes": {
                "task": "src.workers.celery_tasks.run_local_feedback_loop_task",
                "schedule": 1800.0,
                "args": [DEFAULT_SCHEDULED_FEEDBACK["task_id"], DEFAULT_SCHEDULED_SELECTION["tenant_id"]],
            },
            "bi-kpi-daily": {
                "task": "src.workers.celery_tasks.compute_bi_kpi_task",
                "schedule": 86400.0,
                "args": [DEFAULT_SCHEDULED_KPI["tenant_id"]],
            },
        },
    )

    app.autodiscover_tasks(["src.workers"])

    return app


celery_app = _build_celery_app()
