"""Coverage Monitor (agent 09): decides what to search next.

  due_for_refresh   completed searches whose refresh interval has passed
  expansion         top-level areas that touch a completed area and were never searched by the
                    source, nearest first (breadth-first growth from the seed)

It only creates jobs; the Collector runs them under the usual gate, rate limit and budget."""

from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import SearchCoverage, SearchJob, Source
from app.models.enums import RegionStatus
from app.services.collector import create_job

_EXPANSION_SQL = text(
    """
    SELECT c.id
    FROM regions c
    JOIN region_neighbors n ON n.neighbor_id = c.id
    JOIN regions done ON done.id = n.region_id
    WHERE c.parent_id IS NULL AND done.parent_id IS NULL
      AND done.status = 'COMPLETED'
      AND c.source_location_ids ? :code
      AND NOT EXISTS (SELECT 1 FROM search_coverage sc
                      WHERE sc.region_id = c.id AND sc.source_id = :source_id)
      AND NOT EXISTS (SELECT 1 FROM search_jobs j
                      WHERE j.region_id = c.id AND j.source_id = :source_id
                        AND j.status IN ('QUEUED', 'IN_PROGRESS'))
    GROUP BY c.id
    ORDER BY min(ST_Distance(c.centroid::geography, done.centroid::geography)), c.id
    LIMIT :limit
    """
)


def expansion_region_ids(db: Session, source: Source, limit: int) -> list[int]:
    return list(
        db.scalars(
            _EXPANSION_SQL,
            {"code": source.code, "source_id": source.id, "limit": limit},
        )
    )


def due_region_ids(db: Session, source: Source, limit: int) -> list[int]:
    return list(
        db.scalars(
            select(SearchCoverage.region_id)
            .where(
                SearchCoverage.source_id == source.id,
                SearchCoverage.status == RegionStatus.COMPLETED,
                SearchCoverage.next_due_at <= datetime.now(UTC),
            )
            .order_by(SearchCoverage.next_due_at)
            .limit(limit)
        )
    )


def plan_jobs(db: Session, source: Source, max_jobs: int) -> list[SearchJob]:
    """Refreshes first (keep known data current), then expansion, within max_jobs."""
    jobs = [
        create_job(db, rid, source.id, {}, "SCHEDULE")
        for rid in due_region_ids(db, source, max_jobs)
    ]
    remaining = max_jobs - len(jobs)
    if remaining > 0:
        jobs += [
            create_job(db, rid, source.id, {}, "EXPANSION")
            for rid in expansion_region_ids(db, source, remaining)
        ]
    return jobs
