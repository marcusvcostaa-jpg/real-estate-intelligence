from datetime import UTC, datetime

import httpx
import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select

from app.crawlers import ie_ppr
from app.models import (
    AgentExecution,
    City,
    Country,
    CrawlLog,
    PropertyTransaction,
    Region,
    SearchCoverage,
    Source,
    SourcePermission,
)
from app.models.enums import (
    JobStatus,
    PermissionStatus,
    RegionLevel,
    RegionStatus,
    SourceStatus,
)
from app.services.collector import create_job, run_job
from app.services.coverage import derive_region_status
from tests.ppr_fixture import ppr_zip


def setup_source(db, *, approved=True, rate_limit=100):
    point = WKTElement("POINT(-6.26 53.35)", srid=4326)
    country = Country(iso2="IE", name="Ireland", default_currency="EUR")
    db.add(country)
    db.flush()
    city = City(country_id=country.id, name="Dublin", centroid=point)
    db.add(city)
    db.flush()
    region = Region(
        city_id=city.id,
        level=RegionLevel.DISTRICT,
        name="County Dublin",
        centroid=point,
        source_location_ids={"ie_ppr": "Dublin"},
    )
    spec = {k: v for k, v in ie_ppr.SOURCE.items() if k != "country_iso2"}
    source = Source(**spec, country_id=country.id)
    source.rate_limit_per_minute = rate_limit
    if approved:
        source.status = SourceStatus.ACTIVE
    db.add_all([region, source])
    db.flush()
    permission = SourcePermission(source_id=source.id, **ie_ppr.PERMISSION)
    if approved:
        permission.status, permission.granted_at = PermissionStatus.APPROVED, datetime.now(UTC)
    db.add(permission)
    db.commit()
    return region, source


def zip_client(calls=None, response=None):
    def handler(request):
        if calls is not None:
            calls.append(request.url)
        return response or httpx.Response(
            200, content=ppr_zip(), headers={"content-type": "application/x-zip"}
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_gate_refuses_without_approved_permission(db, redis_client):
    region, source = setup_source(db, approved=False)
    calls = []
    job = create_job(db, region.id, source.id, {}, "MANUAL")
    job = run_job(db, job.id, redis_client=redis_client, http_client=zip_client(calls))

    assert job.status == JobStatus.SKIPPED
    assert "APPROVED" in job.last_error
    assert calls == []  # the source was never contacted
    assert count(db, PropertyTransaction) == 0
    assert db.scalar(select(AgentExecution.status)) == "SKIPPED"


def test_collects_transactions_and_is_idempotent(db, redis_client):
    region, source = setup_source(db)
    job = run_job(
        db,
        create_job(db, region.id, source.id, {}, "MANUAL").id,
        redis_client=redis_client,
        http_client=zip_client(),
    )
    assert job.status == JobStatus.COMPLETED
    assert (job.listings_found, job.new_listings, job.duplicates) == (4, 4, 0)
    assert count(db, PropertyTransaction) == 4
    assert db.scalar(select(CrawlLog.http_status)) == 200

    coverage = db.scalar(select(SearchCoverage))
    assert coverage.status == RegionStatus.COMPLETED
    assert coverage.next_due_at > coverage.last_completed_at
    db.refresh(region)
    assert region.status == RegionStatus.COMPLETED

    again = run_job(
        db,
        create_job(db, region.id, source.id, {}, "MANUAL").id,
        redis_client=redis_client,
        http_client=zip_client(),
    )
    assert (again.new_listings, again.duplicates) == (0, 4)
    assert count(db, PropertyTransaction) == 4


def test_block_marks_source_blocked(db, redis_client):
    region, source = setup_source(db)
    job = run_job(
        db,
        create_job(db, region.id, source.id, {}, "MANUAL").id,
        redis_client=redis_client,
        http_client=zip_client(response=httpx.Response(403)),
    )
    assert job.status == JobStatus.FAILED
    assert job.last_error.startswith("blocked")
    db.refresh(source)
    assert source.status == SourceStatus.BLOCKED
    db.refresh(region)
    assert region.status == RegionStatus.FAILED


def test_rate_limit_requeues_job(db, redis_client):
    region, source = setup_source(db, rate_limit=1)
    first = run_job(
        db,
        create_job(db, region.id, source.id, {}, "MANUAL").id,
        redis_client=redis_client,
        http_client=zip_client(),
    )
    assert first.status == JobStatus.COMPLETED
    calls = []
    second = run_job(
        db,
        create_job(db, region.id, source.id, {}, "MANUAL").id,
        redis_client=redis_client,
        http_client=zip_client(calls),
    )
    assert second.status == JobStatus.QUEUED
    assert second.scheduled_for is not None
    assert calls == []
    # The refused attempt made no request, so it is not counted against the daily budget.
    assert count(db, CrawlLog) == 1


def test_only_one_active_job_per_search(db):
    region, source = setup_source(db)
    first = create_job(db, region.id, source.id, {}, "MANUAL")
    second = create_job(db, region.id, source.id, {}, "SCHEDULE")
    assert first.id == second.id


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([], RegionStatus.NOT_STARTED),
        ([RegionStatus.COMPLETED, RegionStatus.COMPLETED], RegionStatus.COMPLETED),
        ([RegionStatus.COMPLETED, RegionStatus.FAILED], RegionStatus.PARTIALLY_COMPLETED),
        ([RegionStatus.COMPLETED, RegionStatus.IN_PROGRESS], RegionStatus.IN_PROGRESS),
        ([RegionStatus.QUEUED, RegionStatus.COMPLETED], RegionStatus.QUEUED),
        ([RegionStatus.REQUIRES_REVIEW, RegionStatus.IN_PROGRESS], RegionStatus.REQUIRES_REVIEW),
        ([RegionStatus.FAILED], RegionStatus.FAILED),
        ([RegionStatus.COMPLETED, RegionStatus.NOT_STARTED], RegionStatus.PARTIALLY_COMPLETED),
    ],
)
def test_derive_region_status(statuses, expected):
    assert derive_region_status(statuses) == expected


def test_daily_budget_counts_from_postgres_not_redis(db, redis_client):
    region, source = setup_source(db)
    source.daily_request_budget = 1
    db.commit()
    first = run_job(db, create_job(db, region.id, source.id, {}, "MANUAL").id,
                    redis_client=redis_client, http_client=zip_client())  # fmt: skip
    assert first.status == JobStatus.COMPLETED
    redis_client.flushdb()  # Redis restart loses every counter...
    calls = []
    second = run_job(db, create_job(db, region.id, source.id, {}, "MANUAL").id,
                     redis_client=redis_client, http_client=zip_client(calls))  # fmt: skip
    assert second.status == JobStatus.QUEUED  # ...but the budget still holds
    assert calls == []
