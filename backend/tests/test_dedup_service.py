from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.crawlers.base import TransactionRecord
from app.models import DataQualityIssue, DedupCandidate, Property, PropertyTransaction
from app.models.enums import DedupDecision
from app.services.collector import store_transactions
from app.services.dedup import apply_dedup
from app.validators.transactions import validate_transactions
from tests.test_collector import setup_source


def record(n, address, sale_date, price="300000", eircode=None):
    return TransactionRecord(
        external_id=f"t{n}",
        transaction_date=date.fromisoformat(sale_date),
        price=Decimal(price),
        currency="EUR",
        is_full_market_price=True,
        vat_exclusive=False,
        address_original=address,
        postal_code=eircode,
        description_original="Second-Hand Dwelling house /Apartment",
        raw_payload={},
    )


def seed(db):
    region, source = setup_source(db)
    store_transactions(
        db,
        source.id,
        region.id,
        [
            record(1, "12 Example Road, Dublin 6", "2012-05-01"),
            record(2, "12 EXAMPLE RD, DUBLIN 6", "2019-07-15", eircode="D06AB12"),
            record(3, "Unit 1, Test Quay, Dublin 1", "2024-03-10"),
            record(4, "Unit 1, Test Quay, Dublin 1", "2024-03-10"),
            record(5, "5 Sample Park Avenue, Lucan", "2012-01-01"),
            record(6, "5 Sample Park, Lucan", "2019-01-01", price="5000"),
        ],
    )
    db.commit()
    return source


def test_apply_dedup_links_and_is_rerunnable(db):
    source = seed(db)
    stats = apply_dedup(db, source.id)
    assert stats["properties_created"] == 5  # 1+2 merged; 3,4 separate; 5,6 separate
    assert db.scalar(select(func.count()).where(PropertyTransaction.property_id.is_(None))) == 0

    p1, p2 = db.scalars(
        select(PropertyTransaction.property_id).where(
            PropertyTransaction.external_id.in_(["t1", "t2"])
        )
    ).all()
    assert p1 == p2
    merged = db.get(Property, p1)
    assert merged.address_display == "12 EXAMPLE RD, DUBLIN 6"  # latest sale
    assert merged.postal_code == "D06AB12"
    assert merged.property_type == "DWELLING"

    pending = db.scalars(
        select(DedupCandidate).where(DedupCandidate.decision == DedupDecision.PENDING)
    ).all()
    assert len(pending) == 2  # same-date units + one-sided "Avenue"
    assert all(c.transaction_id and c.listing_id is None for c in pending)

    again = apply_dedup(db, source.id)
    assert again["properties_created"] == 0
    assert again["links_written"] == 0
    assert db.scalar(select(func.count()).select_from(DedupCandidate)) == len(pending)


def test_validate_flags_and_is_rerunnable(db):
    source = seed(db)
    assert validate_transactions(db, source.id) == {"PRICE_VERY_LOW": 1}
    validate_transactions(db, source.id)
    assert db.scalar(select(func.count()).select_from(DataQualityIssue)) == 1
