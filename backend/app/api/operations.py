"""Operational visibility and recovery: jobs, agent executions, sources, manual retry."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_role
from app.database.session import get_db
from app.models import SearchJob, Source, User
from app.models.enums import JobStatus, UserRole
from app.services.collector import remaining_budget

router = APIRouter(tags=["operations"])
analyst = require_role(UserRole.ANALYST, UserRole.ADMIN)
admin = require_role(UserRole.ADMIN)

_JOBS = text(
    """
    SELECT j.id, r.name AS region, s.code AS source, j.status, j.triggered_by, j.attempt,
           j.priority, j.scheduled_for, j.started_at, j.finished_at, j.pages_processed,
           j.listings_found AS records, j.new_listings AS new_records, j.duplicates,
           j.errors_count, j.last_error
    FROM search_jobs j
    JOIN regions r ON r.id = j.region_id
    JOIN sources s ON s.id = j.source_id
    WHERE CAST(:status AS job_status) IS NULL OR j.status = CAST(:status AS job_status)
    ORDER BY j.id DESC
    LIMIT :limit
    """
)


@router.get("/jobs", dependencies=[Depends(analyst)])
def list_jobs(
    status: JobStatus | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.execute(_JOBS, {"status": status, "limit": limit})
    return [dict(r._mapping) for r in rows]


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(admin)) -> dict:
    """Requeue a FAILED, SKIPPED or CANCELLED job now (e.g. after a permission is approved or
    a blocked source was reviewed). The Collector re-applies every check when it runs."""
    job = db.get(SearchJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status not in (JobStatus.FAILED, JobStatus.SKIPPED, JobStatus.CANCELLED):
        raise HTTPException(409, f"Job is {job.status}; only finished failures can be retried")
    job.status, job.scheduled_for = JobStatus.QUEUED, datetime.now(UTC)
    job.last_error = f"manual retry by {user.email} (previous: {job.last_error})"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Another active job exists for the same search") from None
    return {"id": job.id, "status": job.status}


@router.get("/agents/executions", dependencies=[Depends(analyst)])
def list_executions(
    agent: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT id, agent, status, job_id, started_at, finished_at, duration_ms, output, error
            FROM agent_executions
            WHERE CAST(:agent AS text) IS NULL OR agent = CAST(:agent AS text)
            ORDER BY id DESC LIMIT :limit
            """
        ),
        {"agent": agent, "limit": limit},
    )
    return [dict(r._mapping) for r in rows]


@router.get("/sources", dependencies=[Depends(current_user)])
def list_sources(db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for source in db.scalars(select(Source).order_by(Source.code)):
        permission = db.execute(
            text(
                """
                SELECT status, license_name, attribution_text, granted_at, expires_at
                FROM source_permissions WHERE source_id = :id ORDER BY id DESC LIMIT 1
                """
            ),
            {"id": source.id},
        ).first()
        out.append(
            {
                "code": source.code,
                "name": source.name,
                "status": source.status,
                "integration_type": source.integration_type,
                "rate_limit_per_minute": source.rate_limit_per_minute,
                "daily_request_budget": source.daily_request_budget,
                "requests_left_today": remaining_budget(db, source),
                "min_refresh_interval_days": source.min_refresh_interval.days,
                "last_success_at": source.last_success_at,
                "last_error_at": source.last_error_at,
                "permission": dict(permission._mapping) if permission else None,
            }
        )
    return out
