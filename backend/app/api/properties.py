"""Property search with filters, property detail with sale history, and the human review
queue for deduplication."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.analytics import IN_COUNTRY
from app.api.deps import current_user, require_role
from app.database.session import get_db
from app.models import DedupCandidate, Property, PropertyTransaction, User
from app.models.enums import DedupDecision, UserRole

router = APIRouter(tags=["properties"])
analyst = require_role(UserRole.ANALYST, UserRole.ADMIN)
admin = require_role(UserRole.ADMIN)
PAGE = 50


@router.get("/properties", dependencies=[Depends(current_user)])
def search_properties(
    country: str | None = Query(None, pattern="^[A-Z]{2}$", description="ISO alpha-2"),
    region_id: int | None = None,
    min_price: Decimal | None = Query(None, ge=0),
    max_price: Decimal | None = Query(None, ge=0),
    sold_from: date | None = None,
    sold_to: date | None = None,
    kind: Literal["new", "second_hand"] | None = None,
    full_market_only: bool = False,
    repeat_sales_only: bool = False,
    q: str | None = Query(None, max_length=100, description="address contains"),
    cursor: str | None = Query(None, description="opaque, from the previous page"),
    db: Session = Depends(get_db),
) -> dict:
    """Filters apply to each property's LAST sale. Ordered by last sale date, newest first."""
    where, params = ["true"], {"limit": PAGE + 1}
    filters = {
        "region_id": ("s.region_id = :region_id", region_id),
        "min_price": ("s.last_sale_price >= :min_price", min_price),
        "max_price": ("s.last_sale_price <= :max_price", max_price),
        "sold_from": ("s.last_sale_date >= :sold_from", sold_from),
        "sold_to": ("s.last_sale_date <= :sold_to", sold_to),
    }
    for key, (clause, value) in filters.items():
        if value is not None:
            where.append(clause)
            params[key] = value
    if country:  # prices are only comparable within one currency
        where.append(f"s.region_id IN (SELECT r.id FROM regions r WHERE {IN_COUNTRY})")  # noqa: S608
        params["country"] = country
    if kind:
        where.append("s.last_is_new" if kind == "new" else "NOT s.last_is_new")
    if full_market_only:
        where.append("s.last_full_market AND NOT s.last_vat_exclusive")
    if repeat_sales_only:
        where.append("s.sales > 1")
    if q:
        where.append("s.address_display ILIKE :q")
        params["q"] = f"%{q.strip()}%"
    if cursor:
        try:
            last_date, last_id = cursor.split("_")
            params["c_date"], params["c_id"] = date.fromisoformat(last_date), int(last_id)
        except ValueError:
            raise HTTPException(400, "invalid cursor") from None
        where.append("(s.last_sale_date, s.property_id) < (:c_date, :c_id)")
    rows = db.execute(
        text(
            f"""
            SELECT s.property_id, s.public_id, s.address_display, s.postal_code, r.name AS region,
                   s.sales, s.first_sale_date, s.last_sale_date, s.last_sale_price, s.currency,
                   s.last_full_market, s.last_vat_exclusive, s.last_is_new
            FROM property_sales_summary s
            JOIN regions r ON r.id = s.region_id
            WHERE {" AND ".join(where)}
            ORDER BY s.last_sale_date DESC, s.property_id DESC
            LIMIT :limit
            """  # noqa: S608 - clauses are constants; every value is a bound parameter
        ),
        params,
    ).all()
    items = [dict(r._mapping) for r in rows[:PAGE]]
    next_cursor = None
    if len(rows) > PAGE:
        next_cursor = f"{items[-1]['last_sale_date'].isoformat()}_{items[-1]['property_id']}"
    for item in items:
        item.pop("property_id")
        item["last_sale_price"] = float(item["last_sale_price"])
    return {"items": items, "next_cursor": next_cursor, "price_kind": "transacted"}


@router.get("/properties/{public_id}", dependencies=[Depends(current_user)])
def property_detail(public_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    prop = db.scalar(select(Property).where(Property.public_id == public_id))
    if prop is None:
        raise HTTPException(404, "Property not found")
    region = db.execute(
        text("SELECT name FROM regions WHERE id = :id"), {"id": prop.region_id}
    ).scalar()
    sales = db.execute(
        text(
            """
            SELECT t.id, t.transaction_date, t.price, t.currency, t.is_full_market_price,
                   t.vat_exclusive, t.address_original, t.postal_code, t.description_original,
                   s.code AS source
            FROM property_transactions t JOIN sources s ON s.id = t.source_id
            WHERE t.property_id = :id ORDER BY t.transaction_date
            """
        ),
        {"id": prop.id},
    ).all()
    return {
        "public_id": prop.public_id,
        "address_display": prop.address_display,
        "postal_code": prop.postal_code,
        "property_type": prop.property_type,
        "category": prop.category,
        # IPTU areas when the source has them (basis BUILT incl. condominium common areas).
        "built_area_m2": prop.built_area_m2 and float(prop.built_area_m2),
        "land_area_m2": prop.land_area_m2 and float(prop.land_area_m2),
        "region": region,
        "sales": [{**dict(r._mapping), "price": float(r.price)} for r in sales],
        "pending_reviews": db.scalar(
            select(func.count())
            .select_from(DedupCandidate)
            .join(PropertyTransaction, PropertyTransaction.id == DedupCandidate.transaction_id)
            .where(
                DedupCandidate.decision == DedupDecision.PENDING,
                (DedupCandidate.candidate_property_id == prop.id)
                | (PropertyTransaction.property_id == prop.id),
            )
        ),
        "price_kind": "transacted",
    }


@router.get("/dedup/candidates", dependencies=[Depends(analyst)])
def review_queue(
    decision: DedupDecision = DedupDecision.PENDING,
    limit: int = Query(25, ge=1, le=100),
    after_id: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    rows = db.execute(
        text(
            """
            SELECT c.id, c.score, c.vetoes, c.signals->>'method' AS method, c.decision,
                   t.address_original AS sale_address, t.transaction_date AS sale_date,
                   t.price AS sale_price, t.postal_code AS sale_eircode,
                   p.address_display AS candidate_address, p.postal_code AS candidate_eircode,
                   p.public_id AS candidate_public_id,
                   (SELECT count(*) FROM property_transactions x
                     WHERE x.property_id = p.id) AS candidate_sales,
                   r.name AS region
            FROM dedup_candidates c
            JOIN property_transactions t ON t.id = c.transaction_id
            JOIN properties p ON p.id = c.candidate_property_id
            LEFT JOIN regions r ON r.id = p.region_id
            WHERE c.decision = CAST(:decision AS dedup_decision) AND c.id > :after_id
            ORDER BY c.id
            LIMIT :limit
            """
        ),
        {"decision": decision, "after_id": after_id, "limit": limit},
    ).all()
    items = [
        {**dict(r._mapping), "score": float(r.score), "sale_price": float(r.sale_price)}
        for r in rows
    ]
    total = db.scalar(
        select(func.count()).select_from(DedupCandidate).where(DedupCandidate.decision == decision)
    )
    return {"items": items, "total": total}


class DecisionIn(BaseModel):
    decision: Literal["SAME_PROPERTY", "DIFFERENT"]


@router.post("/dedup/candidates/{candidate_id}/decision")
def decide(
    candidate_id: int, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(admin)
) -> dict:
    """SAME_PROPERTY moves the sale into the candidate property (the emptied property record,
    which is derived data, is removed). DIFFERENT only records the decision. Sales themselves are
    never deleted, and later deduplication runs keep these assignments."""
    candidate = db.get(DedupCandidate, candidate_id)
    if candidate is None or candidate.transaction_id is None:
        raise HTTPException(404, "Candidate not found")
    if candidate.decision != DedupDecision.PENDING:
        raise HTTPException(409, f"Already decided: {candidate.decision}")
    moved_from = None
    if body.decision == "SAME_PROPERTY":
        sale = db.get(PropertyTransaction, candidate.transaction_id)
        moved_from = sale.property_id
        sale.property_id = candidate.candidate_property_id
        db.flush()
        remaining = db.scalar(
            select(func.count())
            .select_from(PropertyTransaction)
            .where(PropertyTransaction.property_id == moved_from)
        )
        if moved_from and moved_from != candidate.candidate_property_id and remaining == 0:
            # Repoint other review rows at the surviving property before removing the empty one.
            db.execute(
                text(
                    "UPDATE dedup_candidates SET candidate_property_id = :keep "
                    "WHERE candidate_property_id = :gone AND id <> :id "
                    "AND NOT EXISTS (SELECT 1 FROM dedup_candidates d2 "
                    "WHERE d2.transaction_id = dedup_candidates.transaction_id "
                    "AND d2.candidate_property_id = :keep)"
                ),
                {"keep": candidate.candidate_property_id, "gone": moved_from, "id": candidate.id},
            )
            db.execute(
                text("DELETE FROM dedup_candidates WHERE candidate_property_id = :gone"),
                {"gone": moved_from},
            )
            db.delete(db.get(Property, moved_from))
    candidate.decision = DedupDecision(body.decision)
    candidate.decided_by, candidate.decided_at = user.id, datetime.now(UTC)
    db.commit()
    return {"id": candidate.id, "decision": candidate.decision, "moved_from_property": moved_from}
