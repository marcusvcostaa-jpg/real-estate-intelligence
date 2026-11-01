from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("rei", broker=settings.redis_url, include=["app.tasks.agents"])
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_routes={
        "agents.collect_job": {"queue": "collect"},
        "agents.process_source": {"queue": "process"},
    },
    timezone="UTC",
    beat_schedule={
        "orchestrate": {
            "task": "agents.orchestrate",
            "schedule": settings.orchestrator_interval_seconds,
        },
    },
)
