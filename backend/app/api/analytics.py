"""Dashboard indicators and market analytics (Market Analyst, agent 08).

All prices are TRANSACTED prices (official registers), never asking prices. Statistics are per
country (one currency each); "market" statistics use only residential, whole-property market
sales — see MARKET and BASIS. What a country's sources do not publish (rooms, parking, ...) is
reported as unavailable instead of being estimated."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.database.session import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(current_user)])

MARKET = "is_full_market_price AND NOT vat_exclusive AND category = 'RESIDENTIAL'"
BASIS = {
    "IE": "transacted, full market price, VAT-inclusive, residential (PPR)",
    "BR": "declared transaction value (ITBI), purchase of the whole property, residential",
}
PRICE_M2_BASIS = {"BR": "BUILT: IPTU built area, incl. share of condominium common areas"}
# Only the Irish register says whether a dwelling was sold new.
IS_NEW = {"IE": "(description_original ILIKE 'New %' OR description_original ILIKE '%Nua%')"}
PROVISIONAL_MONTHS = 2  # sales reach the register weeks after the deal: recent months are partial
UNAVAILABLE = {
    "IE": {
        "price_per_m2": "no_floor_area",
        "area": "no_floor_area",
        "bedrooms": "no_room_counts",
        "bathrooms": "no_room_counts",
        "parking": "no_parking",
    },
    "BR": {
        "new_vs_second_hand": "no_new_flag",
        "bedrooms": "no_room_counts",
        "bathrooms": "no_room_counts",
        "parking": "no_parking",
    },
}
PRICE_BANDS = {
    "EUR": [0, 200_000, 300_000, 400_000, 500_000, 750_000, 1_000_000],
    "BRL": [0, 250_000, 400_000, 600_000, 800_000, 1_000_000, 1_500_000, 2_000_000, 3_000_000],
}
COUNTRY = Query("IE", pattern="^[A-Z]{2}$", description="ISO 3166-1 alpha-2")
IN_COUNTRY = """r.city_id IN (SELECT c.id FROM cities c JOIN countries co ON co.id = c.country_id
                               WHERE co.iso2 = :country)"""


def _currency(db: Session, country: str) -> str:
    currency = db.scalar(
        text("SELECT default_currency FROM countries WHERE iso2 = :c"), {"c": country}
    )
    if currency is None:
        raise HTTPException(404, f"no data for country {country}")
    return currency


@router.get("/countries")
def countries(db: Session = Depends(get_db)) -> dict:
    """Countries with search areas, for the dashboard's country switch."""
    rows = db.execute(
        text(
            """
            SELECT co.iso2, co.name, co.default_currency AS currency
            FROM countries co
            WHERE EXISTS (SELECT 1 FROM cities c JOIN regions r ON r.city_id = c.id
                          WHERE c.country_id = co.id AND r.parent_id IS NULL)
            ORDER BY co.id
            """
        )
    ).all()
    return {"countries": [dict(r._mapping) for r in rows]}


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


_AREAS = """
    SELECT r.id, r.name, r.status,
           count(*) AS sales,
           count(*) FILTER (WHERE t.recent) AS sales_12m,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY t.price)
             FILTER (WHERE t.recent AND t.market) AS median_12m,
           avg(t.price) FILTER (WHERE t.recent AND t.market) AS mean_12m,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY t.price)
             FILTER (WHERE t.previous AND t.market) AS median_prev_12m,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY t.price_m2)
             FILTER (WHERE t.recent AND t.market) AS median_price_m2_12m,
           count(t.price_m2) FILTER (WHERE t.recent AND t.market) AS price_m2_sales_12m,
           count(*) FILTER (WHERE t.recent AND t.is_new) AS new_sales_12m,
           count(DISTINCT t.property_id) AS properties,
           (SELECT count(*) FROM property_sales_summary s
             WHERE s.region_id = r.id AND s.sales > 1) AS repeat_sold_properties
    FROM regions r
    JOIN (
        SELECT region_id, property_id, price, price / NULLIF(built_area_m2, 0) AS price_m2,
               {market} AS market, {is_new} AS is_new,
               transaction_date >= current_date - interval '12 months' AS recent,
               transaction_date < current_date - interval '12 months'
                 AND transaction_date >= current_date - interval '24 months' AS previous
        FROM property_transactions
    ) t ON t.region_id = r.id
    WHERE r.parent_id IS NULL AND {in_country}
    GROUP BY r.id
    ORDER BY median_12m DESC NULLS LAST
    """


@router.get("/areas")
def areas(country: str = COUNTRY, db: Session = Depends(get_db)) -> dict:
    currency = _currency(db, country)
    sql = _AREAS.format(  # constant fragments only; values are bound
        market=MARKET, is_new=IS_NEW.get(country, "false"), in_country=IN_COUNTRY
    )
    rows = []
    for row in db.execute(text(sql), {"country": country}):
        item = dict(row._mapping)
        for key in ("median_12m", "mean_12m", "median_prev_12m", "median_price_m2_12m"):
            item[key] = float(item[key]) if item[key] is not None else None
        prev, cur = item["median_prev_12m"], item["median_12m"]
        item["median_change_pct"] = round((cur / prev - 1) * 100, 1) if prev and cur else None
        if country not in IS_NEW:
            item["new_sales_12m"] = None  # unknown, not zero
        rows.append(item)
    return {
        "country": country,
        "currency": currency,
        "areas": rows,
        "basis": BASIS.get(country),
        "price_m2_basis": PRICE_M2_BASIS.get(country),
        "unavailable": UNAVAILABLE.get(country, {}),
    }


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
    countries = db.scalars(
        text(
            "SELECT DISTINCT co.iso2 FROM regions r JOIN cities c ON c.id = r.city_id "
            "JOIN countries co ON co.id = c.country_id WHERE r.id = ANY(:ids)"
        ),
        {"ids": ids},
    ).all()
    if len(countries) > 1:
        raise HTTPException(400, "regions must be in one country (one currency)")
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
    country = countries[0] if countries else None
    return {"series": list(series.values()), "basis": BASIS.get(country)}


@router.get("/price-bands")
def price_bands(
    country: str = COUNTRY, region_id: int | None = None, db: Session = Depends(get_db)
) -> dict:
    """Distribution of last-12-month market sales by price band (single series)."""
    currency = _currency(db, country)
    limits = PRICE_BANDS.get(currency, PRICE_BANDS["EUR"])
    rows = dict(
        db.execute(
            text(
                f"""
                SELECT width_bucket(t.price, ARRAY[{",".join(map(str, limits[1:]))}]::numeric[])
                         AS band, count(*)
                FROM property_transactions t JOIN regions r ON r.id = t.region_id
                WHERE {MARKET} AND t.transaction_date >= current_date - interval '12 months'
                  AND {IN_COUNTRY}
                  AND (CAST(:region_id AS bigint) IS NULL
                       OR t.region_id = CAST(:region_id AS bigint))
                GROUP BY 1
                """  # noqa: S608 - constant fragments only; values are bound
            ),
            {"region_id": region_id, "country": country},
        ).all()
    )
    bands = []
    for i, low in enumerate(limits):
        high = limits[i + 1] if i + 1 < len(limits) else None
        bands.append({"min": low, "max": high, "sales": rows.get(i, 0)})
    return {"currency": currency, "bands": bands, "basis": f"{BASIS.get(country)}, last 12 months"}
