from datetime import datetime, timedelta

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, Interval, SmallInteger, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, pg_enum, pk
from app.models.enums import JobStatus, RegionStatus


class SearchCoverage(Base):
    """One row per (region, source, filters): what was searched, when, and when it is due."""

    __tablename__ = "search_coverage"
    __table_args__ = (
        Index(
            "uq_search_coverage_region_source_filters",
            "region_id",
            "source_id",
            "filters_hash",
            unique=True,
        ),
    )

    id: Mapped[int] = pk()
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    filters: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    filters_hash: Mapped[str] = mapped_column(CHAR(64))
    status: Mapped[RegionStatus] = mapped_column(
        pg_enum(RegionStatus, "region_status"), server_default=RegionStatus.NOT_STARTED
    )
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pages_processed: Mapped[int] = mapped_column(server_default="0")
    pages_expected: Mapped[int | None]
    listings_found: Mapped[int] = mapped_column(server_default="0")
    refresh_interval: Mapped[timedelta] = mapped_column(Interval)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_job_id: Mapped[int | None] = mapped_column(ForeignKey("search_jobs.id"), index=True)


class SearchJob(Base):
    __tablename__ = "search_jobs"
    __table_args__ = (
        # The database itself refuses a second active job for the same search.
        Index(
            "uq_search_jobs_one_active",
            "region_id",
            "source_id",
            "filters_hash",
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'IN_PROGRESS')"),
        ),
        Index("ix_search_jobs_status_priority", "status", "priority"),
    )

    id: Mapped[int] = pk()
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    filters: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    filters_hash: Mapped[str] = mapped_column(CHAR(64))
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"), server_default=JobStatus.QUEUED
    )
    priority: Mapped[int] = mapped_column(SmallInteger, server_default="100")
    attempt: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    triggered_by: Mapped[str] = mapped_column(Text)  # SCHEDULE, EXPANSION, MANUAL, RETRY
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pages_processed: Mapped[int] = mapped_column(server_default="0")
    pages_expected: Mapped[int | None]
    next_cursor: Mapped[dict | None] = mapped_column(JSONB)  # resume point
    listings_found: Mapped[int] = mapped_column(server_default="0")
    new_listings: Mapped[int] = mapped_column(server_default="0")
    new_properties: Mapped[int] = mapped_column(server_default="0")
    duplicates: Mapped[int] = mapped_column(server_default="0")
    errors_count: Mapped[int] = mapped_column(server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id: Mapped[int] = pk()
    job_id: Mapped[int] = mapped_column(ForeignKey("search_jobs.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    page: Mapped[int | None]
    request_url: Mapped[str | None] = mapped_column(Text)  # never with keys/tokens
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    items_count: Mapped[int | None]
    duration_ms: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
