"""Dashboard indicators and market analytics (Market Analyst, agent 08).

All prices are TRANSACTED prices (official register), never asking prices. Unless stated,
"market" statistics use only full-market, VAT-inclusive sales — see MARKET_BASIS.
The register has no floor area, rooms or parking, so those analyses report as unavailable
instead of being estimated."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.database.session import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(current_user)])

MARKET = "is_full_market_price AND NOT vat_exclusive"
MARKET_BASIS = "transacted, full market price, VAT-inclusive"
IS_NEW = "(description_original ILIKE 'New %' OR description_original ILIKE '%Nua%')"
PROVISIONAL_MONTHS = 2  # sales reach the register weeks after the deal: recent months are partial
UNAVAILABLE = {
    "price_per_m2": "source has no floor area",
    "area": "source has no floor area",
    "bedrooms": "source has no room counts",
    "bathrooms": "source has no room counts",
    "parking": "source has no parking data",
}
PRICE_BANDS = [0, 200_000, 300_000, 400_000, 500_000, 750_000, 1_000_000]


@router.get("/kpis")
def kpis(db: Session = Depends(get_db)) -> dict:
    row = db.execute(
        text(
            """
            SELECT (SELECT count(*) FROM properties) AS properties,
                   (SELECT count(*) FROM property_transactions) AS transactions,
                   (SELECT count(*) FROM property_listings) AS listings,
                   (SELECT count(*) FROM regions WHERE parent_id IS NULL AND status = 'COMPLETED')
                     AS areas_researched,
                   (SELECT count(*) FROM regions WHERE parent_id IS NULL) AS areas_total,
                   (SELECT count(*) FROM regions WHERE status = 'COMPLETED') AS regions_researched,
                   (SELECT count(*) FROM regions
                     WHERE status IN ('NOT_STARTED', 'PARTIALLY_COMPLETED', 'FAILED',
                                      'REQUIRES_REVIEW')) AS regions_pending,
                   (SELECT count(*) FROM regions WHERE status IN ('QUEUED', 'IN_PROGRESS'))
                     AS regions_in_progress,
                   (SELECT count(*) FROM properties WHERE created_at >= now() - interval '7 days')
                     AS new_properties_7d,
                   (SELECT count(*) FROM sources WHERE status = 'ACTIVE') AS active_sources,
                   (SELECT max(last_completed_at) FROM search_coverage) AS last_update,
                   (SELECT count(*) FROM dedup_candidates WHERE decision = 'PENDING')
                     AS review_pending,
                   (SELECT count(*) FROM search_jobs WHERE status = 'QUEUED') AS jobs_queued
            """
        )
    ).first()
    return dict(row._mapping)


_AREAS = text(
    f"""
    SELECT r.id, r.name, r.status,
           count(*) AS sales,
           count(*) FILTER (WHERE t.recent) AS sales_12m,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY t.price)
             FILTER (WHERE t.recent AND t.market) AS median_12m,
           avg(t.price) FILTER (WHERE t.recent AND t.market) AS mean_12m,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY t.price)
             FILTER (WHERE t.previous AND t.market) AS median_prev_12m,
           count(*) FILTER (WHERE t.recent AND t.is_new) AS new_sales_12m,
           count(DISTINCT t.property_id) AS properties,
           (SELECT count(*) FROM property_sales_summary s
             WHERE s.region_id = r.id AND s.sales > 1) AS repeat_sold_properties
    FROM regions r
    JOIN (
        SELECT region_id, property_id, price,
               {MARKET} AS market, {IS_NEW} AS is_new,
               transaction_date >= current_date - interval '12 months' AS recent,
               transaction_date < current_date - interval '12 months'
                 AND transaction_date >= current_date - interval '24 months' AS previous
        FROM property_transactions
    ) t ON t.region_id = r.id
    WHERE r.parent_id IS NULL
    GROUP BY r.id
    ORDER BY median_12m DESC NULLS LAST
    """  # noqa: S608 - only constant SQL fragments are interpolated
)


@router.get("/areas")
def areas(db: Session = Depends(get_db)) -> dict:
    rows = []
    for row in db.execute(_AREAS):
        item = dict(row._mapping)
        for key in ("median_12m", "mean_12m", "median_prev_12m"):
            item[key] = float(item[key]) if item[key] is not None else None
        prev, cur = item["median_prev_12m"], item["median_12m"]
        item["median_change_pct"] = round((cur / prev - 1) * 100, 1) if prev and cur else None
        rows.append(item)
    return {"areas": rows, "basis": MARKET_BASIS, "unavailable": UNAVAILABLE}


@router.get("/timeseries")
def timeseries(
    region_ids: str = Query(..., description="comma-separated region ids (max 4)"),
    months: int = Query(60, ge=6, le=240),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ids = [int(x) for x in region_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "region_ids must be integers") from None
    if not 1 <= len(ids) <= 4:
        raise HTTPException(400, "choose 1 to 4 regions")  # more lines are unreadable
    rows = db.execute(
        text(
            f"""
            SELECT region_id, date_trunc('month', transaction_date)::date AS month,
                   count(*) AS sales,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY price) AS median
            FROM property_transactions
            WHERE {MARKET} AND region_id = ANY(:ids)
              AND transaction_date >= date_trunc('month', current_date)
                                      - make_interval(months => :months)
            GROUP BY 1, 2 ORDER BY 1, 2
            """  # noqa: S608 - constant fragment only; values are bound
        ),
        {"ids": ids, "months": months},
    ).all()
    names = dict(
        db.execute(text("SELECT id, name FROM regions WHERE id = ANY(:ids)"), {"ids": ids}).all()
    )
    today = datetime.now(UTC).date()
    cutoff = date(today.year, today.month, 1)
    for _ in range(PROVISIONAL_MONTHS - 1):
        cutoff = date(cutoff.year - (cutoff.month == 1), (cutoff.month - 2) % 12 + 1, 1)
    series = {rid: {"region_id": rid, "name": names.get(rid), "points": []} for rid in ids}
    for region_id, month, sales, median in rows:
        series[region_id]["points"].append(
            {
                "month": month.isoformat(),
                "sales": sales,
                "median": float(median),
                "provisional": month >= cutoff,
            }
        )
    return {"series": list(series.values()), "basis": MARKET_BASIS}


@router.get("/price-bands")
def price_bands(region_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    """Distribution of last-12-month market sales by price band (single series)."""
    rows = dict(
        db.execute(
            text(
                f"""
                SELECT width_bucket(price, ARRAY[{",".join(map(str, PRICE_BANDS[1:]))}]::numeric[])
                         AS band, count(*)
                FROM property_transactions
                WHERE {MARKET} AND transaction_date >= current_date - interval '12 months'
                  AND (CAST(:region_id AS bigint) IS NULL OR region_id = CAST(:region_id AS bigint))
                GROUP BY 1
                """  # noqa: S608 - constant fragments only; values are bound
            ),
            {"region_id": region_id},
        ).all()
    )
    bands = []
    for i, low in enumerate(PRICE_BANDS):
        high = PRICE_BANDS[i + 1] if i + 1 < len(PRICE_BANDS) else None
        bands.append({"min": low, "max": high, "sales": rows.get(i, 0)})
    return {"bands": bands, "basis": f"{MARKET_BASIS}, last 12 months"}
