"""Regions as GeoJSON for the map, region details and coverage summary.

Sale statistics are TRANSACTED prices from official registers: the median uses the same market
basis as the analytics (residential, whole-property market sales) over the last 12 months, in
the currency of the region's country."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.analytics import BASIS, IN_COUNTRY, MARKET
from app.api.deps import current_user
from app.database.session import get_db
from app.geographic import boundaries, ibge

router = APIRouter(tags=["regions"], dependencies=[Depends(current_user)])

MEDIAN_BASIS = {country: f"{basis}, last 12 months" for country, basis in BASIS.items()}
BOUNDARY_ATTRIBUTIONS = {
    boundaries.BOUNDARY_SOURCE: boundaries.ATTRIBUTION,
    ibge.BOUNDARY_SOURCE: ibge.ATTRIBUTION,
}
_COUNTRY = """(SELECT co.iso2 FROM cities c JOIN countries co ON co.id = c.country_id
               WHERE c.id = r.city_id) AS country,
              (SELECT co.default_currency FROM cities c JOIN countries co ON co.id = c.country_id
               WHERE c.id = r.city_id) AS currency"""

_STATS = f"""
    SELECT region_id,
           count(*) AS sales,
           count(*) FILTER (WHERE recent) AS sales_12m,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY price) FILTER (WHERE recent) AS median_12m
    FROM (
        SELECT region_id, price,
               transaction_date >= current_date - interval '12 months'
                 AND {MARKET} AS recent
        FROM property_transactions
    ) t
    GROUP BY region_id
"""  # noqa: S608 - only the constant MARKET fragment is interpolated

_REGIONS = text(
    f"""
    WITH stats AS ({_STATS})
    SELECT r.id, r.name, r.level, r.status, r.parent_id, r.last_searched_at,
           (SELECT count(*) FROM regions c WHERE c.parent_id = r.id) AS children,
           s.sales, s.sales_12m, s.median_12m, {_COUNTRY},
           ST_AsGeoJSON(ST_SimplifyPreserveTopology(r.geom, :tolerance), 5)::json AS geometry
    FROM regions r
    LEFT JOIN stats s ON s.region_id = r.id
    WHERE r.geom IS NOT NULL
      AND (CASE WHEN CAST(:parent_id AS bigint) IS NULL THEN r.parent_id IS NULL
                ELSE r.parent_id = CAST(:parent_id AS bigint) END)
      AND (CAST(:country AS text) IS NULL OR {IN_COUNTRY})
    ORDER BY r.name
    """  # noqa: S608 - only a constant fragment is interpolated; values are bound
)


def _feature(row) -> dict:
    props = dict(row._mapping)
    geometry = props.pop("geometry")
    props["last_searched_at"] = props["last_searched_at"] and props["last_searched_at"].isoformat()
    props["median_12m"] = props["median_12m"] and float(props["median_12m"])
    return {"type": "Feature", "id": props["id"], "geometry": geometry, "properties": props}


@router.get("/regions")
def regions_geojson(
    parent_id: int | None = Query(None, description="children of this region; omit for top level"),
    country: str | None = Query(None, pattern="^[A-Z]{2}$", description="ISO alpha-2 filter"),
    db: Session = Depends(get_db),
) -> dict:
    tolerance = 0.002 if parent_id is None else 0.0003  # degrees; map display only
    params = {"parent_id": parent_id, "tolerance": tolerance, "country": country}
    rows = db.execute(_REGIONS, params).all()
    return {
        "type": "FeatureCollection",
        "features": [_feature(r) for r in rows],
        "median_basis": MEDIAN_BASIS.get(country) if country else MEDIAN_BASIS,
    }


@router.get("/regions/{region_id}")
def region_detail(region_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.execute(
        text(
            f"""
            WITH stats AS ({_STATS})
            SELECT r.id, r.name, r.level, r.status, r.parent_id, r.boundary_source,
                   r.last_searched_at, p.name AS parent_name,
                   s.sales, s.sales_12m, s.median_12m, {_COUNTRY},
                   (SELECT count(*) FROM regions c WHERE c.parent_id = r.id) AS children,
                   (SELECT count(*) FROM properties pr WHERE pr.region_id = r.id) AS properties
            FROM regions r
            LEFT JOIN regions p ON p.id = r.parent_id
            LEFT JOIN stats s ON s.region_id = r.id
            WHERE r.id = :id
            """  # noqa: S608 - constant fragment; values are bound
        ),
        {"id": region_id},
    ).first()
    if row is None:
        raise HTTPException(404, "Region not found")
    detail = dict(row._mapping)
    detail["median_12m"] = detail["median_12m"] and float(detail["median_12m"])
    detail["median_basis"] = MEDIAN_BASIS.get(detail["country"])
    detail["coverage"] = [
        dict(c._mapping)
        for c in db.execute(
            text(
                """
                SELECT s.code AS source, s.name AS source_name, c.status, c.last_completed_at,
                       c.next_due_at, c.listings_found AS records
                FROM search_coverage c JOIN sources s ON s.id = c.source_id
                WHERE c.region_id = :id
                ORDER BY s.code
                """
            ),
            {"id": region_id},
        )
    ]
    detail["neighbors"] = list(
        db.scalars(
            text(
                """
                SELECT r.name FROM region_neighbors n JOIN regions r ON r.id = n.neighbor_id
                WHERE n.region_id = :id ORDER BY r.name
                """
            ),
            {"id": region_id},
        )
    )
    return detail


@router.get("/coverage/summary")
def coverage_summary(db: Session = Depends(get_db)) -> dict:
    by_status = {
        level: dict(rows)
        for level, rows in (
            (
                "top_level",
                db.execute(
                    text("SELECT status, count(*) FROM regions WHERE parent_id IS NULL GROUP BY 1")
                ).all(),
            ),
            ("all", db.execute(text("SELECT status, count(*) FROM regions GROUP BY 1")).all()),
        )
    }
    totals = db.execute(
        text(
            """
            SELECT (SELECT count(*) FROM properties) AS properties,
                   (SELECT count(*) FROM property_transactions) AS transactions,
                   (SELECT count(*) FROM property_listings) AS listings,
                   (SELECT count(*) FROM sources WHERE status = 'ACTIVE') AS active_sources,
                   (SELECT max(last_completed_at) FROM search_coverage) AS last_update,
                   (SELECT count(*) FROM dedup_candidates WHERE decision = 'PENDING')
                     AS dedup_pending_review
            """
        )
    ).first()
    attributions = list(
        db.scalars(
            text(
                """
                SELECT DISTINCT p.attribution_text FROM source_permissions p
                JOIN sources s ON s.id = p.source_id
                WHERE p.status = 'APPROVED' AND p.attribution_required
                """
            )
        )
    )
    used = db.scalars(text("SELECT DISTINCT boundary_source FROM regions")).all()
    return {
        "regions_by_status": by_status,
        "totals": dict(totals._mapping),
        "attributions": [
            *attributions,
            *(label for source, label in BOUNDARY_ATTRIBUTIONS.items() if source in used),
        ],
    }
