from datetime import date, timedelta

from sqlalchemy import func, select

from app.models import DedupCandidate, Property, PropertyTransaction
from app.models.enums import DedupDecision, UserRole
from app.services.collector import store_transactions
from app.services.dedup import apply_dedup
from tests.test_api import login, make_user
from tests.test_collector import setup_source
from tests.test_dedup_service import record

RECENT = (date.today() - timedelta(days=40)).isoformat()
OLD = (date.today() - timedelta(days=500)).isoformat()


def seeded(db):
    region, source = setup_source(db)
    store_transactions(
        db,
        source.id,
        region.id,
        [
            record(1, "12 Example Road, Dublin 6", OLD, price="300000"),
            record(2, "12 EXAMPLE RD, DUBLIN 6", RECENT, price="400000", eircode="D06AB12"),
            record(3, "Unit 1, Test Quay, Dublin 1", RECENT, price="250000"),
            record(4, "Unit 1, Test Quay, Dublin 1", RECENT, price="250000"),
            record(5, "5 Sample Park Avenue, Lucan", OLD, price="350000"),
            record(6, "5 Sample Park, Lucan", RECENT, price="600000"),
        ],
    )
    db.commit()
    apply_dedup(db, source.id)
    return region, source


def headers(client, db, role=UserRole.ANALYST, email="analyst@example.com"):
    make_user(db, email=email, role=role)
    return {"Authorization": f"Bearer {login(client, email=email).json()['access_token']}"}


def test_kpis_and_areas(client, db):
    region, _ = seeded(db)
    h = headers(client, db)
    k = client.get("/api/v1/analytics/kpis", headers=h).json()
    assert (k["properties"], k["transactions"], k["listings"]) == (5, 6, 0)
    assert k["review_pending"] == 2

    a = client.get("/api/v1/analytics/areas", headers=h).json()
    county = a["areas"][0]
    assert county["name"] == "County Dublin" and county["sales"] == 6
    assert county["sales_12m"] == 4
    assert county["median_12m"] == 325000.0  # 250k, 250k, 400k, 600k
    assert county["repeat_sold_properties"] == 1
    assert a["unavailable"]["price_per_m2"] == "no_floor_area"
    assert a["currency"] == "EUR" and a["areas"][0]["median_price_m2_12m"] is None


def test_timeseries_and_bands(client, db):
    region, _ = seeded(db)
    h = headers(client, db)
    assert (
        client.get("/api/v1/analytics/timeseries?region_ids=1,2,3,4,5", headers=h).status_code
        == 400
    )
    ts = client.get(
        f"/api/v1/analytics/timeseries?region_ids={region.id}&months=24", headers=h
    ).json()
    points = ts["series"][0]["points"]
    assert sum(p["sales"] for p in points) == 6
    bands = client.get("/api/v1/analytics/price-bands", headers=h).json()["bands"]
    assert sum(b["sales"] for b in bands) == 4
    assert bands[1] == {"min": 200000, "max": 300000, "sales": 2}


def test_property_search_filters_and_detail(client, db):
    seeded(db)
    h = headers(client, db)
    all_ = client.get("/api/v1/properties", headers=h).json()
    assert len(all_["items"]) == 5 and all_["next_cursor"] is None
    repeat = client.get("/api/v1/properties?repeat_sales_only=true", headers=h).json()["items"]
    assert [i["address_display"] for i in repeat] == ["12 EXAMPLE RD, DUBLIN 6"]
    priced = client.get("/api/v1/properties?min_price=500000", headers=h).json()["items"]
    assert [i["last_sale_price"] for i in priced] == [600000.0]
    assert client.get("/api/v1/properties?q=quay", headers=h).json()["items"][0]["sales"] == 1

    detail = client.get(f"/api/v1/properties/{repeat[0]['public_id']}", headers=h).json()
    assert [s["price"] for s in detail["sales"]] == [300000.0, 400000.0]  # oldest first
    assert detail["price_kind"] == "transacted"
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/properties/{missing}", headers=h).status_code == 404


def test_review_queue_decisions(client, db):
    seeded(db)
    analyst = headers(client, db)
    admin = headers(client, db, UserRole.ADMIN, "admin@example.com")
    queue = client.get("/api/v1/dedup/candidates", headers=analyst).json()
    assert queue["total"] == 2
    by_method = {c["method"]: c for c in queue["items"]}
    lucan, units = by_method["fuzzy"], by_method["address"]

    assert (
        client.post(
            f"/api/v1/dedup/candidates/{lucan['id']}/decision",
            json={"decision": "SAME_PROPERTY"},
            headers=analyst,
        ).status_code
        == 403
    )
    r = client.post(
        f"/api/v1/dedup/candidates/{lucan['id']}/decision",
        json={"decision": "SAME_PROPERTY"},
        headers=admin,
    )
    assert r.status_code == 200 and r.json()["moved_from_property"] is not None
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Property)) == 4  # emptied record removed
    assert db.scalar(select(func.count()).select_from(PropertyTransaction)) == 6  # no sale lost

    r = client.post(
        f"/api/v1/dedup/candidates/{units['id']}/decision",
        json={"decision": "DIFFERENT"},
        headers=admin,
    )
    assert r.json()["decision"] == "DIFFERENT"
    assert (
        client.post(
            f"/api/v1/dedup/candidates/{units['id']}/decision",
            json={"decision": "SAME_PROPERTY"},
            headers=admin,
        ).status_code
        == 409
    )

    # A later dedup run keeps the human decisions.
    source_id = db.scalar(select(PropertyTransaction.source_id).limit(1))
    stats = apply_dedup(db, source_id)
    assert stats["properties_created"] == 0 and stats["links_written"] == 0
    pending = db.scalar(
        select(func.count())
        .select_from(DedupCandidate)
        .where(DedupCandidate.decision == DedupDecision.PENDING)
    )
    assert pending == 0


def test_statistics_never_mix_countries(client, db):
    from geoalchemy2.elements import WKTElement

    from app.models import City, Country, Region
    from app.models.enums import RegionLevel

    region, _ = seeded(db)
    point = WKTElement("POINT(-46.6 -23.6)", srid=4326)
    br = Country(iso2="BR", name="Brasil", default_currency="BRL")
    db.add(br)
    db.flush()
    city = City(country_id=br.id, name="Cidade Teste", centroid=point)
    db.add(city)
    db.flush()
    sp = Region(
        city_id=city.id, level=RegionLevel.DISTRICT, name="Cidade Teste (SP)", centroid=point
    )
    db.add(sp)
    db.commit()
    h = headers(client, db)

    mixed = client.get(f"/api/v1/analytics/timeseries?region_ids={region.id},{sp.id}", headers=h)
    assert mixed.status_code == 400
    countries = client.get("/api/v1/analytics/countries", headers=h).json()["countries"]
    assert [(c["iso2"], c["currency"]) for c in countries] == [("IE", "EUR"), ("BR", "BRL")]
    areas = client.get("/api/v1/analytics/areas?country=BR", headers=h).json()
    assert areas["currency"] == "BRL" and areas["areas"] == []  # Irish sales never leak in
    assert "new_vs_second_hand" in areas["unavailable"]
    bands = client.get("/api/v1/analytics/price-bands?country=BR", headers=h).json()
    assert bands["currency"] == "BRL" and sum(b["sales"] for b in bands["bands"]) == 0
    assert client.get("/api/v1/analytics/areas?country=XX", headers=h).status_code == 404
