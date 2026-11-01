"""Celery tasks: thin wrappers around agents/services (docs/AGENT_ROLES.md)."""

import logging

from app.agents.orchestrator import orchestrate
from app.core.config import get_settings
from app.database.locks import advisory_lock
from app.database.session import SessionLocal
from app.models.enums import JobStatus
from app.services.collector import run_job
from app.services.dedup import apply_dedup
from app.tasks.celery_app import celery_app
from app.validators.transactions import validate_transactions

log = logging.getLogger(__name__)


@celery_app.task(name="agents.orchestrate")
def orchestrate_task() -> dict | None:
    with advisory_lock("orchestrator") as acquired:
        if not acquired:
            log.info("orchestrator cycle skipped: previous cycle still running")
            return None
        settings = get_settings()
        with SessionLocal() as db:
            return orchestrate(
                db,
                dispatch=lambda job_id: collect_job_task.delay(job_id),
                expansion=settings.orchestrator_expansion,
            )


@celery_app.task(name="agents.collect_job")
def collect_job_task(job_id: int) -> str:
    with SessionLocal() as db:
        job = run_job(db, job_id)
        if job.status == JobStatus.COMPLETED and job.new_listings:
            process_source_task.delay(job.source_id)
        return str(job.status)


@celery_app.task(name="agents.process_source", bind=True, max_retries=10)
def process_source_task(self, source_id: int) -> dict:
    """Validation then deduplication; one run per source at a time."""
    with advisory_lock(f"process_source:{source_id}") as acquired:
        if not acquired:
            raise self.retry(countdown=60)
        with SessionLocal() as db:
            return {
                "validation": validate_transactions(db, source_id),
                "dedup": apply_dedup(db, source_id),
            }
