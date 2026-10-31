from celery import Celery

from app.core.config import get_settings

settings = get_settings()

# Task modules are added to `include` as agents are implemented (Phase 3+).
celery_app = Celery("rei", broker=settings.redis_url, include=[])
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    timezone="UTC",
    beat_schedule={},
)
