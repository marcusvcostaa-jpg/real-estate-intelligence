from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.agents.orchestrator import (
    MAX_ATTEMPTS,
    STUCK_AFTER,
    due_job_ids,
    orchestrate,
    recover_stuck,
    retry_failed,
)
from app.models import AgentExecution, CrawlLog, SearchJob
from app.models.enums import JobStatus, SourceStatus
from app.services.collector import create_job
from tests.test_collector import setup_source

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def job_in(db, region, source, status, **fields):
    job = create_job(db, region.id, source.id, {"n": len(fields) + id(status) % 1000}, "MANUAL")
    job.status = status
    for key, value in fields.items():
        setattr(job, key, value)
    db.commit()
    return job


def test_stuck_job_is_requeued_then_given_up(db):
    region, source = setup_source(db)
    stuck = job_in(
        db, region, source, JobStatus.IN_PROGRESS, started_at=NOW - STUCK_AFTER * 2, attempt=1
    )
    assert recover_stuck(db, NOW) == {"requeued": 1, "failed": 0}
    db.refresh(stuck)
    assert stuck.status == JobStatus.QUEUED and "stuck" in stuck.last_error

    stuck.status, stuck.attempt, stuck.started_at = (
        JobStatus.IN_PROGRESS,
        MAX_ATTEMPTS,
        NOW - STUCK_AFTER * 2,
    )
    db.commit()
    assert recover_stuck(db, NOW) == {"requeued": 0, "failed": 1}
    db.refresh(stuck)
    assert stuck.status == JobStatus.FAILED and "gave up" in stuck.last_error


def test_recent_in_progress_job_is_left_alone(db):
    region, source = setup_source(db)
    job_in(db, region, source, JobStatus.IN_PROGRESS, started_at=NOW - timedelta(minutes=5))
    assert recover_stuck(db, NOW) == {"requeued": 0, "failed": 0}


def test_transient_failure_retried_after_backoff_but_block_never(db):
    region, source = setup_source(db)
    transient = job_in(
        db, region, source, JobStatus.FAILED, attempt=1, finished_at=NOW - timedelta(minutes=5),
        last_error="ConnectTimeout: timed out",
    )  # fmt: skip
    blocked = job_in(
        db, region, source, JobStatus.FAILED, attempt=1, finished_at=NOW - timedelta(days=1),
        last_error="blocked: HTTP 403",
    )  # fmt: skip
    assert retry_failed(db, NOW) == 0  # backoff (10 min) not over yet
    assert retry_failed(db, NOW + timedelta(minutes=10)) == 1
    db.refresh(transient)
    db.refresh(blocked)
    assert transient.status == JobStatus.QUEUED
    assert blocked.status == JobStatus.FAILED


def test_no_retry_while_source_is_blocked(db):
    region, source = setup_source(db)
    job_in(
        db, region, source, JobStatus.FAILED, attempt=1, finished_at=NOW - timedelta(hours=1),
        last_error="ConnectTimeout",
    )  # fmt: skip
    source.status = SourceStatus.BLOCKED
    db.commit()
    assert retry_failed(db, NOW) == 0


def test_dispatch_only_due_jobs_of_active_sources(db):
    region, source = setup_source(db)
    due = job_in(db, region, source, JobStatus.QUEUED)
    job_in(db, region, source, JobStatus.QUEUED, scheduled_for=NOW + timedelta(hours=1))
    assert due_job_ids(db, NOW) == [due.id]
    source.status = SourceStatus.PAUSED
    db.commit()
    assert due_job_ids(db, NOW) == []


def test_orchestrate_cycle_respects_budget_and_records_execution(db):
    region, source = setup_source(db)
    queued = job_in(db, region, source, JobStatus.QUEUED)
    dispatched = []
    # Budget spent today: the Coverage Monitor must not plan anything new.
    db.add_all(
        CrawlLog(job_id=queued.id, source_id=source.id, http_status=200)
        for _ in range(source.daily_request_budget)
    )
    db.commit()
    stats = orchestrate(db, dispatched.append)
    assert stats["planned"] == 0
    assert dispatched == [queued.id]
    execution = db.scalar(select(AgentExecution).where(AgentExecution.agent == "orchestrator"))
    assert execution.output["dispatched"] == [queued.id]


def test_manual_retry_endpoint(client, db):
    from app.models.enums import UserRole
    from tests.test_api import login, make_user

    region, source = setup_source(db)
    failed = job_in(db, region, source, JobStatus.SKIPPED, last_error="no APPROVED permission")
    make_user(db)
    make_user(db, email="admin@example.com", role=UserRole.ADMIN)
    analyst = {"Authorization": f"Bearer {login(client).json()['access_token']}"}
    admin = {
        "Authorization": f"Bearer {login(client, email='admin@example.com').json()['access_token']}"
    }

    assert client.post(f"/api/v1/jobs/{failed.id}/retry", headers=analyst).status_code == 403
    r = client.post(f"/api/v1/jobs/{failed.id}/retry", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "QUEUED"
    assert client.post(f"/api/v1/jobs/{failed.id}/retry", headers=admin).status_code == 409

    jobs = client.get("/api/v1/jobs?status=QUEUED", headers=analyst).json()
    assert [j["id"] for j in jobs] == [failed.id]
    assert "manual retry by admin@example.com" in jobs[0]["last_error"]
    sources = client.get("/api/v1/sources", headers=analyst).json()
    assert sources[0]["code"] == "ie_ppr" and sources[0]["permission"]["status"] == "APPROVED"
    db.expire_all()  # the API committed through its own session
    assert db.get(SearchJob, failed.id).status == JobStatus.QUEUED
