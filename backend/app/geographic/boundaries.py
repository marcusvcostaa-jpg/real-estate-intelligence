"""Official Irish boundaries from Tailte Éireann (National Statutory Boundaries 2019, generalised
20 m), licensed CC BY 4.0 — attribution "© Tailte Éireann". Approved 2026-11-01.

Counties become top-level search areas (a `cities` row + a root region); selected counties are
subdivided into administrative areas (local authorities) and electoral divisions."""

import json
import time

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.crawlers.base import raise_for_block
from app.models import City, Country, Region
from app.models.enums import RegionLevel

ARCGIS = "https://services-eu1.arcgis.com/FH5XCsx8rYXqnjF5/arcgis/rest/services"
_NSB = "OSi_National_Statutory_Boundaries___Generalised_20m"
LAYERS = {
    "counties": f"Counties___{_NSB}",
    "admin_areas": f"Administrative_Areas___{_NSB}",
    "electoral_divisions": f"Electoral_Divisions___{_NSB}",
}
BOUNDARY_SOURCE = "OFFICIAL:tailte_nsb_2019_gen20m"
ATTRIBUTION = "© Tailte Éireann (CC BY 4.0)"
_PAGE = 1000


def fetch_layer(client: httpx.Client, layer: str, where: str) -> list[dict]:
    features: list[dict] = []
    while True:
        response = client.get(
            f"{ARCGIS}/{LAYERS[layer]}/FeatureServer/0/query",
            params={
                "where": where,
                "outFields": "*",
                "outSR": 4326,
                "f": "geojson",
                "orderByFields": "ESRI_OID",
                "resultOffset": len(features),
                "resultRecordCount": _PAGE,
            },
        )
        raise_for_block(response)
        page = response.json().get("features", [])
        features += page
        if len(page) < _PAGE:
            return features
        time.sleep(1)  # be gentle with the public service


def _geom(feature: dict):
    """GeoJSON -> valid MultiPolygon in SRID 4326."""
    g = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(feature["geometry"])), 4326)
    return func.ST_Multi(func.ST_CollectionExtract(func.ST_MakeValid(g), 3))


def _name(raw: str) -> str:
    """'DUN LAOGHAIRE-RATHDOWN' -> 'Dun Laoghaire-Rathdown', "ST. KEVIN'S" -> "St. Kevin's"."""
    return " ".join("-".join(p.capitalize() for p in w.split("-")) for w in raw.lower().split())


def _ids(props: dict, id_field: str) -> dict:
    return {
        "tailte_guid": props.get("GUID"),
        f"tailte_{id_field.lower()}": props.get(id_field),
        "name_en": props.get("ENGLISH"),
        "name_ga": props.get("GAEILGE"),
    }


def _by_guid(db: Session, guid: str) -> Region | None:
    return db.scalar(select(Region).where(Region.external_ids["tailte_guid"].astext == guid))


def import_counties(db: Session, client: httpx.Client, source_location_key: str | None) -> dict:
    country = db.scalar(select(Country).where(Country.iso2 == "IE"))
    if country is None:
        country = Country(iso2="IE", iso3="IRL", name="Ireland", default_currency="EUR")
        db.add(country)
        db.flush()
    created = updated = 0
    for feature in fetch_layer(client, "counties", "1=1"):
        props = feature["properties"]
        name = _name(props["ENGLISH"])
        region_name = f"County {name}"
        geom = _geom(feature)
        region = _by_guid(db, props["GUID"]) or db.scalar(
            select(Region).where(Region.parent_id.is_(None), Region.name == region_name)
        )
        if region is None:
            city = City(country_id=country.id, name=name, admin1_name=region_name, centroid=None)
            region = Region(level=RegionLevel.DISTRICT, name=region_name, source_location_ids={})
            created += 1
        else:
            city = db.get(City, region.city_id)
            updated += 1
        city.geom, city.centroid = geom, func.ST_PointOnSurface(geom)
        city.boundary_source = BOUNDARY_SOURCE
        city.external_ids = _ids(props, "CO_ID")
        db.add(city)
        db.flush()
        region.city_id = city.id
        region.geom, region.centroid = geom, func.ST_PointOnSurface(geom)
        region.boundary_source = BOUNDARY_SOURCE
        region.external_ids = _ids(props, "CO_ID")
        if source_location_key:
            # e.g. the Property Price Register names counties exactly like this ("Dublin").
            region.source_location_ids = {**region.source_location_ids, source_location_key: name}
        db.add(region)
    db.commit()
    return {"counties_created": created, "counties_updated": updated}


def subdivide_county(db: Session, client: httpx.Client, county: str) -> dict:
    """Administrative areas under the county, electoral divisions under the area that contains
    their point-on-surface."""
    root = db.scalar(
        select(Region).where(Region.parent_id.is_(None), Region.name == f"County {_name(county)}")
    )
    if root is None:
        raise ValueError(f"County {county} not imported yet")
    where = f"COUNTY='{county.upper()}'"
    counts = {"admin_areas": 0, "electoral_divisions": 0}
    for layer, level, id_field in (
        ("admin_areas", RegionLevel.DISTRICT, "CC_ID"),
        ("electoral_divisions", RegionLevel.LOCALITY, "ED_ID"),
    ):
        for feature in fetch_layer(client, layer, where):
            props = feature["properties"]
            geom = _geom(feature)
            existing = _by_guid(db, props["GUID"])
            if existing:  # re-import refreshes name and shape, keeps id and hierarchy
                existing.name, existing.geom = _name(props["ENGLISH"]), geom
                existing.centroid = func.ST_PointOnSurface(geom)
                continue
            parent_id = root.id
            if layer == "electoral_divisions":
                parent_id = (
                    db.scalar(
                        select(Region.id)
                        .where(
                            Region.parent_id == root.id,
                            func.ST_Contains(Region.geom, func.ST_PointOnSurface(geom)),
                        )
                        .limit(1)
                    )
                    or root.id
                )
            db.add(
                Region(
                    city_id=root.city_id,
                    parent_id=parent_id,
                    level=level,
                    name=_name(props["ENGLISH"]),
                    geom=geom,
                    centroid=func.ST_PointOnSurface(geom),
                    boundary_source=BOUNDARY_SOURCE,
                    external_ids=_ids(props, id_field),
                )
            )
            counts[layer] += 1
        db.flush()
    db.commit()
    return counts


def refresh_neighbors(db: Session) -> None:
    db.execute(text("REFRESH MATERIALIZED VIEW region_neighbors"))
    db.commit()
