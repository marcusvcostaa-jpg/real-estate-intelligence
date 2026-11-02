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
        category="RESIDENTIAL",  # as the PPR connector sets it
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


def test_source_property_key_groups_exactly_without_review(db):
    from dataclasses import replace

    region, source = setup_source(db)
    base = record(1, "R EXEMPLO, 10, AP 12", "2025-03-01")
    store_transactions(
        db,
        source.id,
        region.id,
        [
            replace(base, external_id="k1", source_property_key="sql:1", category="RESIDENTIAL",
                    property_type="APARTMENT", built_area_m2=Decimal("80")),
            replace(base, external_id="k2", source_property_key="sql:1",
                    address_original="R EXEMPLO, 10, AP 12 E 1VG",
                    transaction_date=date(2026, 1, 15)),
            replace(base, external_id="k3", source_property_key=None),  # fraction: own property
            replace(base, external_id="k4", source_property_key=None),
        ],
    )  # fmt: skip
    db.commit()
    stats = apply_dedup(db, source.id)
    assert stats["properties_created"] == 3 and stats["method"] == "source_property_key"
    assert db.scalar(select(func.count()).select_from(DedupCandidate)) == 0
    pk1, pk2 = db.scalars(
        select(PropertyTransaction.property_id)
        .where(PropertyTransaction.external_id.in_(["k1", "k2"]))
        .order_by(PropertyTransaction.external_id)
    ).all()
    assert pk1 == pk2
    prop = db.get(Property, pk1)
    assert prop.address_display == "R EXEMPLO, 10, AP 12 E 1VG"  # latest sale
    assert (prop.property_type, prop.category, prop.built_area_m2) == (
        "APARTMENT",
        "RESIDENTIAL",
        Decimal("80.00"),
    )  # latest known value of each attribute
    assert apply_dedup(db, source.id)["properties_created"] == 0


def test_postal_code_rules_follow_the_country():
    from app.validators.transactions import postal_code_valid

    assert postal_code_valid("BR", "01234-000") and not postal_code_valid("BR", "1234000")
    assert postal_code_valid("IE", "D06 AB12") and not postal_code_valid("IE", "01234-000")
