from __future__ import annotations

from celery import Celery

from src.config.settings import get_settings


def create_celery_app() -> Celery:
    settings = get_settings().selection_execution
    app = Celery(
        "pms_selection",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["src.workers.celery_selection_tasks"],
    )
    app.conf.update(
        task_default_queue=settings.celery_queue_name,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=False,
        worker_prefetch_multiplier=1,
    )
    return app


celery_app = create_celery_app()
