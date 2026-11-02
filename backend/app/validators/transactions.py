"""Data quality rules for transacted prices (Data Validator, agent 06).

Rules flag records in data_quality; they never change or delete the published values."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.agents.deduplication import Txn, untrusted_eircodes
from app.models import Country, DataQualityIssue, PropertyTransaction, Source
from app.validators.address import normalize_eircode

# ponytail: fixed bounds; replace with per-region percentiles once Market Analyst exists.
LOW_PRICE = Decimal("10000")
HIGH_PRICE = Decimal("20000000")
_CEP = re.compile(r"\d{5}-\d{3}")


def postal_code_valid(country_iso2: str | None, code: str) -> bool:
    if country_iso2 == "IE":
        return normalize_eircode(code) is not None
    if country_iso2 == "BR":
        return bool(_CEP.fullmatch(code))
    return True  # no rule for this country yet


def check_transaction(
    t: PropertyTransaction, today: date, country_iso2: str | None = "IE"
) -> list[tuple[str, str, str]]:
    """Return (rule_code, severity, message) for each issue found."""
    issues = []
    if t.price <= 0:
        issues.append(("PRICE_NON_POSITIVE", "ERROR", f"price {t.price}"))
    elif t.price < LOW_PRICE and t.is_full_market_price:
        issues.append(("PRICE_VERY_LOW", "WARNING", f"full-market price {t.price} < {LOW_PRICE}"))
    elif t.price > HIGH_PRICE:
        issues.append(("PRICE_VERY_HIGH", "WARNING", f"price {t.price} > {HIGH_PRICE}"))
    if t.transaction_date > today:
        issues.append(("DATE_IN_FUTURE", "ERROR", f"transaction_date {t.transaction_date}"))
    if not t.address_original:
        issues.append(("ADDRESS_MISSING", "ERROR", "no address"))
    if t.postal_code and not postal_code_valid(country_iso2, t.postal_code):
        rule = "EIRCODE_INVALID" if country_iso2 == "IE" else "POSTAL_CODE_INVALID"
        issues.append((rule, "WARNING", f"invalid postal code {t.postal_code!r}"))
    # PPR publishes Yes/No flags: NULL means an unrecognized value. Elsewhere NULL can be a
    # deliberate "not determinable" (e.g. ITBI fractional transfers) and is not an issue.
    if country_iso2 == "IE" and (t.is_full_market_price is None or t.vat_exclusive is None):
        issues.append(("FLAG_UNRECOGNIZED", "WARNING", "market-price or VAT flag not Yes/No"))
    return issues


def validate_transactions(db: Session, source_id: int, batch: int = 5000) -> dict[str, int]:
    """Flag issues for every transaction of a source. Re-runnable: an open issue is never
    duplicated (partial unique index on data_quality)."""
    today = datetime.now(UTC).date()
    country = db.scalar(
        select(Country.iso2)
        .join(Source, Source.country_id == Country.id)
        .where(Source.id == source_id)
    )
    counts: dict[str, int] = {}
    last_id = 0
    while True:
        rows = db.scalars(
            select(PropertyTransaction)
            .where(PropertyTransaction.source_id == source_id, PropertyTransaction.id > last_id)
            .order_by(PropertyTransaction.id)
            .limit(batch)
        ).all()
        if not rows:
            break
        values = []
        for t in rows:
            for rule, severity, message in check_transaction(t, today, country):
                counts[rule] = counts.get(rule, 0) + 1
                values.append(
                    {
                        "entity_type": "TRANSACTION",
                        "entity_id": t.id,
                        "rule_code": rule,
                        "severity": severity,
                        "message": message,
                    }
                )
        if values:
            db.execute(
                pg_insert(DataQualityIssue)
                .values(values)
                .on_conflict_do_nothing(
                    index_elements=["entity_type", "entity_id", "rule_code"],
                    index_where=DataQualityIssue.resolved_at.is_(None),
                )
            )
        db.commit()
        last_id = rows[-1].id

    if country != "IE":
        return counts
    # Group rule: an Eircode shared by addresses with different numbers is a placeholder/typo.
    rows = db.execute(
        select(
            PropertyTransaction.id,
            PropertyTransaction.address_original,
            PropertyTransaction.postal_code,
            PropertyTransaction.transaction_date,
        ).where(PropertyTransaction.source_id == source_id)
    ).all()
    txns = [Txn.build(*row) for row in rows]
    untrusted = untrusted_eircodes(txns)
    values = [
        {
            "entity_type": "TRANSACTION",
            "entity_id": t.id,
            "rule_code": "EIRCODE_SHARED",
            "severity": "WARNING",
            "message": f"Eircode {t.eircode} also used for addresses with other numbers",
        }
        for t in txns
        if t.eircode in untrusted
    ]
    for start in range(0, len(values), batch):
        db.execute(
            pg_insert(DataQualityIssue)
            .values(values[start : start + batch])
            .on_conflict_do_nothing(
                index_elements=["entity_type", "entity_id", "rule_code"],
                index_where=DataQualityIssue.resolved_at.is_(None),
            )
        )
    if values:
        counts["EIRCODE_SHARED"] = len(values)
    db.commit()
    return counts
