"""Operational visibility and recovery: jobs, agent executions, sources, manual retry and
manual collection requests for places an approved source covers."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_role
from app.database.session import get_db
from app.models import Region, SearchCoverage, SearchJob, Source, User
from app.models.enums import JobStatus, UserRole
from app.services.collector import create_job, filters_hash, gate_refusal, remaining_budget

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


_PLACES = text(
    """
    SELECT r.id AS region_id, r.name AS region, co.iso2 AS country, s.code AS source,
           s.name AS source_name, COALESCE(sc.status::text, 'NOT_STARTED') AS status,
           sc.last_completed_at, sc.next_due_at,
           CASE WHEN sc.last_completed_at + s.min_refresh_interval > now()
                THEN sc.last_completed_at + s.min_refresh_interval END AS manual_blocked_until,
           COALESCE(sc.listings_found, 0) AS records, j.id AS active_job_id,
           j.status AS active_job_status
    FROM regions r
    JOIN cities ci ON ci.id = r.city_id
    JOIN countries co ON co.id = ci.country_id
    JOIN sources s ON r.source_location_ids ? s.code
    LEFT JOIN search_coverage sc ON sc.region_id = r.id AND sc.source_id = s.id
                                AND sc.filters_hash = :fhash
    LEFT JOIN LATERAL (SELECT id, status FROM search_jobs
                       WHERE region_id = r.id AND source_id = s.id
                         AND status IN ('QUEUED', 'IN_PROGRESS')
                       ORDER BY id DESC LIMIT 1) j ON true
    WHERE CAST(:country AS text) IS NULL OR co.iso2 = CAST(:country AS text)
    ORDER BY co.iso2, r.name
    """
)


@router.get("/collection/places", dependencies=[Depends(current_user)])
def collection_places(country: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    """Every place an approved-or-pending source can search, with its coverage and active job."""
    rows = db.execute(_PLACES, {"country": country, "fhash": filters_hash({})})
    return [dict(r._mapping) for r in rows]


class CollectionRequest(BaseModel):
    region_id: int
    source: str


MANUAL_PRIORITY = 10  # ahead of scheduled refreshes and expansion (default 100)


@router.post("/collection/requests", status_code=201, dependencies=[Depends(admin)])
def request_collection(body: CollectionRequest, db: Session = Depends(get_db)) -> dict:
    """Queue a collection now for a place the source covers. Never contacts a source the gate
    refuses, and respects the source's minimum refresh interval (politeness agreed in its
    permission). The orchestrator dispatches it in its next cycle (<= 5 min)."""
    source = db.scalar(select(Source).where(Source.code == body.source))
    region = db.get(Region, body.region_id)
    if source is None or region is None:
        raise HTTPException(404, "Source or place not found")
    if source.code not in region.source_location_ids:
        raise HTTPException(422, f"{source.code} does not cover {region.name}")
    if refusal := gate_refusal(db, source):
        raise HTTPException(409, f"Source cannot be contacted: {refusal}")
    coverage = db.scalar(
        select(SearchCoverage).where(
            SearchCoverage.region_id == region.id,
            SearchCoverage.source_id == source.id,
            SearchCoverage.filters_hash == filters_hash({}),
        )
    )
    now = datetime.now(UTC)
    if coverage and coverage.last_completed_at:
        allowed = coverage.last_completed_at + source.min_refresh_interval
        if allowed > now:
            raise HTTPException(
                409, f"Collected recently; next collection allowed from {allowed:%Y-%m-%d %H:%M}"
            )
    job = create_job(db, region.id, source.id, {}, "MANUAL")  # or the already active one
    if job.status == JobStatus.QUEUED:
        job.priority = MANUAL_PRIORITY  # scheduled_for kept: a budget wait stays a wait
        db.commit()
    return {"id": job.id, "status": job.status, "triggered_by": job.triggered_by}
