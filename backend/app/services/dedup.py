"""Persists Deduplication results for a transactions source: properties, links, review queue."""

import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.agents.deduplication import VERSION, Txn, cluster
from app.models import (
    AgentExecution,
    DedupCandidate,
    Property,
    PropertyTransaction,
    Region,
    Source,
)
from app.models.enums import DedupDecision, ValidationStatus
from app.services.summary import refresh_property_summary

_BATCH = 2000


def load_txns(db: Session, source_id: int) -> list[Txn]:
    rows = db.execute(
        select(
            PropertyTransaction.id,
            PropertyTransaction.address_original,
            PropertyTransaction.postal_code,
            PropertyTransaction.transaction_date,
            PropertyTransaction.region_id,
        )
        .where(PropertyTransaction.source_id == source_id)
        .order_by(PropertyTransaction.id)  # deterministic clusters and review pairs
    ).all()
    return [Txn.build(*row) for row in rows]


def apply_dedup(db: Session, source_id: int) -> dict:
    """Link every transaction of the source to a property (creating properties as needed).

    Re-runnable: clusters that already contain a linked transaction keep that property; a
    cluster that would join two existing properties is not merged automatically (review)."""
    started = time.perf_counter()
    source = db.get(Source, source_id)
    txns = load_txns(db, source_id)
    by_id = {t.id: t for t in txns}
    result = cluster(txns)

    current = dict(
        db.execute(
            select(PropertyTransaction.id, PropertyTransaction.property_id).where(
                PropertyTransaction.source_id == source_id
            )
        ).all()
    )
    region_ids = dict(
        db.execute(
            select(PropertyTransaction.id, PropertyTransaction.region_id).where(
                PropertyTransaction.source_id == source_id
            )
        ).all()
    )
    city_of_region = dict(db.execute(select(Region.id, Region.city_id)).all())

    to_create: list[tuple[list[int], dict]] = []
    links: dict[int, int] = {}
    conflicts = 0
    for group in result.groups:
        existing = {current[tid] for tid in group if current[tid] is not None}
        if len(existing) == 1:
            pid = existing.pop()
            links.update({tid: pid for tid in group if current[tid] is None})
            continue
        if len(existing) > 1:
            conflicts += 1  # ponytail: left as-is; surfaced in stats for review tooling
            continue
        # Most recent sale describes the property; prefer the latest one with an Eircode.
        ordered = sorted((by_id[tid] for tid in group), key=lambda t: t.sale_date)
        latest = ordered[-1]
        with_code = [t for t in ordered if t.eircode]
        region_id = region_ids[latest.id]
        to_create.append(
            (
                group,
                {
                    "country_id": source.country_id,
                    "region_id": region_id,
                    "city_id": city_of_region.get(region_id),
                    "property_type": "DWELLING",  # source does not say house vs apartment
                    "category": "RESIDENTIAL",
                    "address_display": latest.address,
                    "address_normalized": latest.norm.text,
                    "postal_code": with_code[-1].eircode if with_code else None,
                    "validation_status": ValidationStatus.PENDING,
                },
            )
        )

    for start in range(0, len(to_create), _BATCH):
        chunk = to_create[start : start + _BATCH]
        ids = db.scalars(
            pg_insert(Property).values([values for _, values in chunk]).returning(Property.id)
        ).all()
        for (group, _), pid in zip(chunk, ids, strict=True):
            links.update({tid: pid for tid in group})

    items = list(links.items())
    for start in range(0, len(items), _BATCH):
        db.execute(
            update(PropertyTransaction),
            [{"id": tid, "property_id": pid} for tid, pid in items[start : start + _BATCH]],
        )

    property_of = {**{k: v for k, v in current.items() if v is not None}, **links}
    candidates = [
        {
            "transaction_id": link.b,
            "candidate_property_id": property_of[link.a],
            "score": link.score / 100,
            "signals": {"method": "fuzzy_address", "version": VERSION, "auto": True},
            "decision": DedupDecision.AUTO_LINKED,
        }
        for link in result.fuzzy_links
        if link.a in property_of
    ] + [
        {
            "transaction_id": pair.b,
            "candidate_property_id": property_of[pair.a],
            "score": pair.score / 100,
            "signals": {"method": pair.reason, "version": VERSION},
            "vetoes": list(pair.vetoes),
            "decision": DedupDecision.PENDING,
        }
        for pair in result.review
        if property_of.get(pair.a) and property_of.get(pair.a) != property_of.get(pair.b)
    ]
    for start in range(0, len(candidates), _BATCH):
        db.execute(
            pg_insert(DedupCandidate)
            .values(candidates[start : start + _BATCH])
            .on_conflict_do_nothing(index_elements=["transaction_id", "candidate_property_id"])
        )

    stats = {
        **result.stats,
        "transactions": len(txns),
        "groups": len(result.groups),
        "properties_created": len(to_create),
        "links_written": len(links),
        "fuzzy_auto_links": len(result.fuzzy_links),
        "review_candidates": sum(1 for c in candidates if c["decision"] == DedupDecision.PENDING),
        "existing_property_conflicts": conflicts,
    }
    elapsed = time.perf_counter() - started
    db.add(
        AgentExecution(
            agent="deduplication",
            status="COMPLETED",
            input={"source_id": source_id, "version": VERSION},
            output=stats,
            started_at=datetime.now(UTC) - timedelta(seconds=elapsed),
            finished_at=datetime.now(UTC),
            duration_ms=int(elapsed * 1000),
        )
    )
    db.commit()
    refresh_property_summary(db)
    return stats
