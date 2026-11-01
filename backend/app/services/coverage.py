"""Region status is derived from search_coverage, never set by hand (docs/DATABASE_SCHEMA.md).

Coverage is inherited downwards: a search of a county (e.g. the Property Price Register, which
works per county) also covers its administrative areas and electoral divisions."""

from collections import defaultdict
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
    """Recompute the status of a region and of all its descendants."""
    root = db.get(Region, region_id)
    inherited: list[S] = []
    parent_id = root.parent_id
    while parent_id is not None:  # coverage of ancestors applies to this region too
        inherited += db.scalars(
            select(SearchCoverage.status).where(SearchCoverage.region_id == parent_id)
        ).all()
        parent_id = db.scalar(select(Region.parent_id).where(Region.id == parent_id))

    children: dict[int, list[Region]] = defaultdict(list)
    for region in db.scalars(select(Region).where(Region.city_id == root.city_id)):
        if region.parent_id is not None:
            children[region.parent_id].append(region)
    own: dict[int, list[S]] = defaultdict(list)
    for rid, status in db.execute(
        select(SearchCoverage.region_id, SearchCoverage.status)
        .join(Region, Region.id == SearchCoverage.region_id)
        .where(Region.city_id == root.city_id)
    ):
        own[rid].append(status)

    now = datetime.now(UTC)
    stack = [(root, inherited)]
    while stack:
        region, upstream = stack.pop()
        statuses = upstream + own[region.id]
        region.status = derive_region_status(statuses)
        if own[region.id] or upstream:
            region.last_searched_at = now
        stack += [(child, statuses) for child in children[region.id]]
    return root.status
