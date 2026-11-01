"""Synthetic squares (not real boundaries) to test hierarchy, inheritance and expansion."""

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import select, text

from app.agents.coverage_monitor import expansion_region_ids, plan_jobs
from app.crawlers.base import RegionRef
from app.crawlers.ie_ppr import Connector
from app.geographic.boundaries import _name
from app.models import City, Country, Region, SearchCoverage
from app.models.enums import JobStatus, RegionLevel, RegionStatus
from app.services.coverage import refresh_region_status
from tests.ppr_fixture import ppr_zip
from tests.test_collector import setup_source


def square(x0, y0, size=1.0):
    x1, y1 = x0 + size, y0 + size
    return WKTElement(
        f"MULTIPOLYGON((({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0})))", srid=4326
    )


def add_county(db, country_id, name, x0, y0):
    city = City(country_id=country_id, name=name, centroid=WKTElement(f"POINT({x0} {y0})", 4326))
    db.add(city)
    db.flush()
    region = Region(
        city_id=city.id,
        level=RegionLevel.DISTRICT,
        name=f"County {name}",
        geom=square(x0, y0),
        centroid=WKTElement(f"POINT({x0 + 0.5} {y0 + 0.5})", 4326),
        source_location_ids={"ie_ppr": name},
    )
    db.add(region)
    db.flush()
    return region


def test_name_capitalization():
    assert _name("DUN LAOGHAIRE-RATHDOWN COUNTY COUNCIL") == "Dun Laoghaire-Rathdown County Council"
    assert _name("ST. KEVIN'S") == "St. Kevin's"


def test_children_inherit_county_coverage(db):
    seed, source = setup_source(db)
    child = Region(
        city_id=seed.city_id,
        parent_id=seed.id,
        level=RegionLevel.LOCALITY,
        name="Child",
        centroid=WKTElement("POINT(-6.2 53.3)", 4326),
    )
    db.add(child)
    db.add(
        SearchCoverage(
            region_id=seed.id,
            source_id=source.id,
            filters={},
            filters_hash="0" * 64,
            status=RegionStatus.COMPLETED,
            refresh_interval=source.min_refresh_interval,
        )
    )
    db.flush()
    assert refresh_region_status(db, seed.id) == RegionStatus.COMPLETED
    assert child.status == RegionStatus.COMPLETED
    assert refresh_region_status(db, child.id) == RegionStatus.COMPLETED


def test_expansion_picks_unsearched_neighbours_nearest_first(db):
    _, source = setup_source(db)
    country_id = db.scalar(select(Country.id))
    done = add_county(db, country_id, "Done", 0, 0)
    near = add_county(db, country_id, "Near", 1, 0)  # shares an edge
    add_county(db, country_id, "Far", 5, 5)  # not adjacent
    corner = add_county(db, country_id, "Corner", 1, 1)  # touches at a corner only
    done.status = RegionStatus.COMPLETED
    db.commit()
    db.execute(text("REFRESH MATERIALIZED VIEW region_neighbors"))

    ids = expansion_region_ids(db, source, 10)
    assert ids == [near.id, corner.id]

    jobs = plan_jobs(db, source, 1)
    assert [(j.region_id, j.triggered_by, j.status) for j in jobs] == [
        (near.id, "EXPANSION", JobStatus.QUEUED)
    ]
    assert expansion_region_ids(db, source, 10) == [corner.id]  # active job excluded


def test_connector_reuses_cache_on_304(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.headers.get("if-modified-since"))
        if request.headers.get("if-modified-since"):
            return httpx.Response(304)
        return httpx.Response(
            200,
            content=ppr_zip(),
            headers={"content-type": "application/x-zip", "last-modified": "Wed, 28 Oct 2026"},
        )

    connector = Connector(httpx.Client(transport=httpx.MockTransport(handler)), cache_dir=tmp_path)
    region = RegionRef(1, "County Dublin", "Dublin")
    first = connector.search(region, {}, None)
    second = connector.search(region, {}, None)
    assert calls == [None, "Wed, 28 Oct 2026"]
    assert (first.http_status, second.http_status) == (200, 304)
    assert len(first.items) == len(second.items) == 4


def test_regions_api_requires_auth_and_returns_geojson(client, db):
    from tests.test_api import login, make_user

    seed, source = setup_source(db)
    seed.geom = square(-7, 53)
    db.commit()
    assert client.get("/api/v1/regions").status_code == 401

    make_user(db)
    headers = {"Authorization": f"Bearer {login(client).json()['access_token']}"}
    fc = client.get("/api/v1/regions", headers=headers).json()
    assert fc["type"] == "FeatureCollection"
    assert [f["properties"]["name"] for f in fc["features"]] == ["County Dublin"]
    assert fc["features"][0]["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert "VAT-inclusive" in fc["median_basis"]

    detail = client.get(f"/api/v1/regions/{seed.id}", headers=headers).json()
    assert detail["name"] == "County Dublin" and detail["coverage"] == []
    assert client.get("/api/v1/regions/999999", headers=headers).status_code == 404

    summary = client.get("/api/v1/coverage/summary", headers=headers).json()
    assert summary["totals"]["active_sources"] == 1
    assert any("PSRA" in a for a in summary["attributions"])
    assert any("Tailte" in a for a in summary["attributions"])
