"""Property Collector (agent 04): runs one search job end to end.

Enforced here, outside connectors: permission gate, source status, rate limit / daily budget,
crawl logs, stop-on-block, coverage and region status. See docs/AGENT_ROLES.md."""

import hashlib
import importlib
import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta

import httpx
import redis
from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.crawlers.base import RegionRef, SourceBlocked, TransactionRecord
from app.models import (
    AgentExecution,
    CrawlLog,
    PropertyTransaction,
    Region,
    SearchCoverage,
    SearchJob,
    Source,
    SourcePermission,
)
from app.models.enums import (
    IntegrationType,
    JobStatus,
    PermissionStatus,
    RegionStatus,
    SourceStatus,
)
from app.services.coverage import refresh_region_status

log = logging.getLogger(__name__)
_INSERT_BATCH = 1000


class RateLimited(Exception):
    def __init__(self, retry_at: datetime) -> None:
        super().__init__(f"rate limited until {retry_at.isoformat()}")
        self.retry_at = retry_at


def filters_hash(filters: dict) -> str:
    return hashlib.sha256(json.dumps(filters, sort_keys=True).encode()).hexdigest()


def approved_permission(db: Session, source_id: int) -> SourcePermission | None:
    return db.scalar(
        select(SourcePermission)
        .where(
            SourcePermission.source_id == source_id,
            SourcePermission.status == PermissionStatus.APPROVED,
            or_(
                SourcePermission.expires_at.is_(None),
                SourcePermission.expires_at > datetime.now(UTC),
            ),
        )
        .limit(1)
    )


def gate_refusal(db: Session, source: Source) -> str | None:
    """Reason this source must not be contacted, or None if collection is allowed."""
    if approved_permission(db, source.id) is None:
        return "no APPROVED, unexpired source_permissions row"
    if source.status != SourceStatus.ACTIVE:
        return f"source status is {source.status}"
    if source.integration_type == IntegrationType.CRAWLER:
        # ponytail: robots.txt enforcement is not built yet; refuse crawlers until it is.
        return "CRAWLER sources need robots.txt enforcement (not implemented)"
    return None


def requests_today(db: Session, source: Source) -> int:
    """Requests made to the source today (UTC), counted from crawl_logs in Postgres — the
    source of truth, so the daily budget survives a Redis restart. Failure rows count too
    (conservative)."""
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(
        select(func.count())
        .select_from(CrawlLog)
        .where(CrawlLog.source_id == source.id, CrawlLog.created_at >= today)
    )


def remaining_budget(db: Session, source: Source) -> int | None:
    """Requests left today for the source, or None if it has no daily budget."""
    if not source.daily_request_budget:
        return None
    return max(0, source.daily_request_budget - requests_today(db, source))


def take_request_slot(r: redis.Redis, db: Session, source: Source) -> None:
    """Daily budget from Postgres; per-minute limit as a fixed window in Redis.

    ponytail: fixed windows allow two requests a few seconds apart across a minute boundary,
    and two concurrent jobs of one source can overshoot the daily budget by one; switch to a
    sliding window / per-source lock if a source needs strict spacing."""
    now = datetime.now(UTC)
    if remaining_budget(db, source) == 0:
        raise RateLimited(
            (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        )
    minute_key = f"rl:{source.code}:m:{now:%Y%m%d%H%M}"
    pipe = r.pipeline()
    pipe.incr(minute_key)
    pipe.expire(minute_key, 120)
    per_minute, _ = pipe.execute()
    if per_minute > source.rate_limit_per_minute:
        r.decr(minute_key)  # a refused attempt makes no request
        raise RateLimited(now.replace(second=0, microsecond=0) + timedelta(minutes=1))


def create_job(
    db: Session, region_id: int, source_id: int, filters: dict, triggered_by: str
) -> SearchJob:
    """Create a QUEUED job, or return the active one for the same search (DB-enforced)."""
    fhash = filters_hash(filters)
    job = SearchJob(
        region_id=region_id,
        source_id=source_id,
        filters=filters,
        filters_hash=fhash,
        triggered_by=triggered_by,
    )
    db.add(job)
    try:
        db.commit()
        return job
    except IntegrityError:
        db.rollback()
        return db.scalar(
            select(SearchJob).where(
                SearchJob.region_id == region_id,
                SearchJob.source_id == source_id,
                SearchJob.filters_hash == fhash,
                SearchJob.status.in_([JobStatus.QUEUED, JobStatus.IN_PROGRESS]),
            )
        )


def store_transactions(
    db: Session, source_id: int, region_id: int, items: list[TransactionRecord]
) -> int:
    """Insert new transactions; already-known (source_id, external_id) are left untouched."""
    new = 0
    for start in range(0, len(items), _INSERT_BATCH):
        rows = [
            {
                "source_id": source_id,
                "region_id": region_id,
                "external_id": r.external_id,
                "transaction_date": r.transaction_date,
                "price": r.price,
                "currency": r.currency,
                "is_full_market_price": r.is_full_market_price,
                "vat_exclusive": r.vat_exclusive,
                "address_original": r.address_original,
                "postal_code": r.postal_code,
                "description_original": r.description_original,
                "raw_payload": r.raw_payload,
            }
            for r in items[start : start + _INSERT_BATCH]
        ]
        stmt = (
            pg_insert(PropertyTransaction)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["source_id", "external_id"])
            .returning(PropertyTransaction.id)
        )
        new += len(db.execute(stmt).all())
    return new


def load_connector(code: str):
    if not re.fullmatch(r"[a-z0-9_]+", code):
        raise ValueError(f"invalid source code {code!r}")
    return importlib.import_module(f"app.crawlers.{code}").Connector


def _coverage(db: Session, job: SearchJob, source: Source) -> SearchCoverage:
    coverage = db.scalar(
        select(SearchCoverage).where(
            SearchCoverage.region_id == job.region_id,
            SearchCoverage.source_id == job.source_id,
            SearchCoverage.filters_hash == job.filters_hash,
        )
    )
    if coverage is None:
        coverage = SearchCoverage(
            region_id=job.region_id,
            source_id=job.source_id,
            filters=job.filters,
            filters_hash=job.filters_hash,
            refresh_interval=source.min_refresh_interval,
        )
        db.add(coverage)
    return coverage


def run_job(
    db: Session,
    job_id: int,
    *,
    redis_client: redis.Redis | None = None,
    http_client: httpx.Client | None = None,
) -> SearchJob:
    claimed = db.execute(
        update(SearchJob)
        .where(SearchJob.id == job_id, SearchJob.status == JobStatus.QUEUED)
        .values(
            status=JobStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
            attempt=SearchJob.attempt + 1,
        )
    ).rowcount
    db.commit()
    job = db.get(SearchJob, job_id)
    if not claimed:
        return job  # someone else has it, or it is not runnable

    started = time.perf_counter()
    source = db.get(Source, job.source_id)
    region = db.get(Region, job.region_id)

    refusal = gate_refusal(db, source)
    if refusal:
        job.status, job.last_error, job.finished_at = JobStatus.SKIPPED, refusal, datetime.now(UTC)
        _record_execution(db, job, started, "SKIPPED", error=refusal)
        db.commit()
        log.warning("job %s skipped: %s", job.id, refusal)
        return job

    settings = get_settings()
    r = redis_client or redis.Redis.from_url(settings.redis_url)
    client = http_client or httpx.Client(
        headers={"User-Agent": settings.scraper_user_agent}, timeout=120
    )
    coverage = _coverage(db, job, source)
    coverage.status, coverage.last_started_at = RegionStatus.IN_PROGRESS, datetime.now(UTC)
    refresh_region_status(db, region.id)
    db.commit()

    region_ref = RegionRef(region.id, region.name, region.source_location_ids.get(source.code))
    error = None
    try:
        connector = load_connector(source.code)(client)
        cursor = job.next_cursor
        while True:
            take_request_slot(r, db, source)
            page_started = time.perf_counter()
            page = connector.search(region_ref, job.filters, cursor)
            new = store_transactions(db, source.id, region.id, page.items)
            job.pages_processed += 1
            job.listings_found += len(page.items)
            job.new_listings += new
            job.duplicates += len(page.items) - new
            db.add(
                CrawlLog(
                    job_id=job.id,
                    source_id=source.id,
                    page=job.pages_processed,
                    request_url=page.request_url,
                    http_status=page.http_status,
                    items_count=len(page.items),
                    duration_ms=int((time.perf_counter() - page_started) * 1000),
                )
            )
            cursor = job.next_cursor = page.next_cursor
            db.commit()
            if cursor is None:
                break
        now = datetime.now(UTC)
        job.status, job.finished_at = JobStatus.COMPLETED, now
        coverage.status, coverage.last_completed_at = RegionStatus.COMPLETED, now
        coverage.pages_processed, coverage.listings_found = job.pages_processed, job.listings_found
        coverage.next_due_at = now + coverage.refresh_interval
        job.next_run_at = coverage.next_due_at
        source.last_success_at = now
    except RateLimited as exc:
        db.rollback()
        job.status, job.scheduled_for = JobStatus.QUEUED, exc.retry_at
        coverage.status = RegionStatus.QUEUED
        error = str(exc)
    except SourceBlocked as exc:
        db.rollback()
        error = f"blocked: {exc}"
        source.status = SourceStatus.BLOCKED  # a human must review before any retry
        _fail(db, job, coverage, source, error)
    except Exception as exc:
        db.rollback()
        log.exception("job %s failed", job.id)
        error = f"{type(exc).__name__}: {exc}"
        _fail(db, job, coverage, source, error)
    finally:
        if http_client is None:
            client.close()

    job.last_error = error
    refresh_region_status(db, region.id)
    _record_execution(db, job, started, str(job.status), error=error)
    db.commit()
    return job


def _fail(db: Session, job: SearchJob, coverage, source: Source, error: str) -> None:
    now = datetime.now(UTC)
    job.status, job.finished_at = JobStatus.FAILED, now
    job.errors_count += 1
    coverage.status = RegionStatus.FAILED
    source.last_error_at = now
    db.add(CrawlLog(job_id=job.id, source_id=source.id, page=job.pages_processed + 1, error=error))


def _record_execution(
    db: Session, job: SearchJob, started: float, status: str, error: str | None = None
) -> None:
    db.add(
        AgentExecution(
            agent="property_collector",
            job_id=job.id,
            status=status,
            input={"job_id": job.id, "filters": job.filters},
            output={
                "pages": job.pages_processed,
                "records": job.listings_found,
                "new": job.new_listings,
                "duplicates": job.duplicates,
            },
            error=error,
            started_at=datetime.now(UTC) - timedelta(seconds=time.perf_counter() - started),
            finished_at=datetime.now(UTC),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    )
