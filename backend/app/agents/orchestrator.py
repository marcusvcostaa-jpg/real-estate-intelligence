"""Master Orchestrator (agent 01). One cycle, run by Celery Beat every few minutes:

  1. recover jobs stuck IN_PROGRESS (worker died)          -> back to the queue, or FAILED
  2. retry transient failures with exponential backoff      -> blocked/gate refusals never
  3. ask the Coverage Monitor for new jobs, within each source's remaining daily budget
  4. dispatch due QUEUED jobs, highest priority first

Everything is recorded in agent_executions; failures stay visible in search_jobs/crawl_logs.
Blocked sources and permission refusals need a human (CLI set-source-status / approval)."""

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.coverage_monitor import plan_jobs
from app.models import AgentExecution, SearchJob, Source
from app.models.enums import JobStatus, SourceStatus
from app.services.collector import remaining_budget

STUCK_AFTER = timedelta(minutes=30)
MAX_ATTEMPTS = 3
BACKOFF_BASE = timedelta(minutes=10)
MAX_NEW_JOBS_PER_SOURCE = 3
DISPATCH_LIMIT = 10


def _requeue(db: Session, job: SearchJob, when: datetime) -> bool:
    """Back to QUEUED unless another active job for the same search exists (DB-enforced)."""
    job.status, job.scheduled_for = JobStatus.QUEUED, when
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        job = db.get(SearchJob, job.id)
        job.status = JobStatus.CANCELLED
        job.last_error = "superseded by another active job for the same search"
        db.commit()
        return False


def recover_stuck(db: Session, now: datetime) -> dict[str, int]:
    stats = {"requeued": 0, "failed": 0}
    stuck = db.scalars(
        select(SearchJob).where(
            SearchJob.status == JobStatus.IN_PROGRESS, SearchJob.started_at < now - STUCK_AFTER
        )
    ).all()
    for job in stuck:
        note = f"stuck IN_PROGRESS since {job.started_at:%Y-%m-%d %H:%M} UTC"
        if job.attempt >= MAX_ATTEMPTS:
            job.status, job.finished_at = JobStatus.FAILED, now
            job.last_error = f"{note}; gave up after {job.attempt} attempts"
            db.commit()
            stats["failed"] += 1
        else:
            job.last_error = f"{note}; requeued"
            stats["requeued"] += _requeue(db, job, now)
    return stats


def is_retriable(job: SearchJob) -> bool:
    error = job.last_error or ""
    return (
        job.status == JobStatus.FAILED
        and job.attempt < MAX_ATTEMPTS
        and not error.startswith("blocked")
        and "gave up" not in error
    )


def retry_failed(db: Session, now: datetime) -> int:
    retried = 0
    for job in db.scalars(select(SearchJob).where(SearchJob.status == JobStatus.FAILED)).all():
        backoff = BACKOFF_BASE * (2 ** max(job.attempt - 1, 0))
        source = db.get(Source, job.source_id)
        if (
            is_retriable(job)
            and source.status == SourceStatus.ACTIVE
            and job.finished_at
            and job.finished_at + backoff <= now
        ):
            retried += _requeue(db, job, now)
    return retried


def plan_new_jobs(db: Session) -> int:
    planned = 0
    for source in db.scalars(select(Source).where(Source.status == SourceStatus.ACTIVE)).all():
        budget = remaining_budget(db, source)
        limit = MAX_NEW_JOBS_PER_SOURCE if budget is None else min(budget, MAX_NEW_JOBS_PER_SOURCE)
        if limit > 0:
            planned += len(plan_jobs(db, source, limit))
    return planned


def due_job_ids(db: Session, now: datetime, limit: int = DISPATCH_LIMIT) -> list[int]:
    return list(
        db.scalars(
            select(SearchJob.id)
            .join(Source, Source.id == SearchJob.source_id)
            .where(
                SearchJob.status == JobStatus.QUEUED,
                Source.status == SourceStatus.ACTIVE,
                or_(SearchJob.scheduled_for.is_(None), SearchJob.scheduled_for <= now),
            )
            .order_by(SearchJob.priority, SearchJob.created_at)
            .limit(limit)
        )
    )


def orchestrate(db: Session, dispatch: Callable[[int], None], *, expansion: bool = True) -> dict:
    started = time.perf_counter()
    now = datetime.now(UTC)
    stats: dict = {"stuck": recover_stuck(db, now), "retried": retry_failed(db, now)}
    stats["planned"] = plan_new_jobs(db) if expansion else 0
    due = due_job_ids(db, now)
    for job_id in due:
        dispatch(job_id)
    stats["dispatched"] = due
    elapsed = time.perf_counter() - started
    db.add(
        AgentExecution(
            agent="orchestrator",
            status="COMPLETED",
            input={"expansion": expansion},
            output=stats,
            started_at=now,
            finished_at=datetime.now(UTC),
            duration_ms=int(elapsed * 1000),
        )
    )
    db.commit()
    return stats
