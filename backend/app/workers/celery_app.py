"""Celery application.

Start a worker:
    celery -A app.workers.celery_app worker -l info --concurrency 2
Start a scheduler (only if you add periodic tasks):
    celery -A app.workers.celery_app beat -l info
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "vibespace",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_time_limit=60 * 60,
    task_soft_time_limit=55 * 60,
    result_expires=60 * 60 * 24,
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_default_retry_delay=30,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)