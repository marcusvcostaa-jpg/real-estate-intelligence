"""Region status is derived from search_coverage, never set by hand (docs/DATABASE_SCHEMA.md)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Region, SearchCoverage
from app.models.enums import RegionStatus as S


def derive_region_status(statuses: list[S]) -> S:
    if not statuses:
        return S.NOT_STARTED
    present = set(statuses)
    for status in (S.REQUIRES_REVIEW, S.IN_PROGRESS, S.QUEUED):
        if status in present:
            return status
    if present == {S.COMPLETED}:
        return S.COMPLETED
    if present == {S.FAILED}:
        return S.FAILED
    return S.PARTIALLY_COMPLETED


def refresh_region_status(db: Session, region_id: int) -> S:
    region = db.get(Region, region_id)
    statuses = list(
        db.scalars(select(SearchCoverage.status).where(SearchCoverage.region_id == region_id))
    )
    region.status = derive_region_status(statuses)
    region.last_searched_at = datetime.now(UTC)
    return region.status
