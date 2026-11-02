"""Official Brazilian boundaries from IBGE (malhas territoriais) through the IBGE GeoServer WFS:
municipalities (2025 mesh) and districts (Censo 2022). Free use citing the source "IBGE".
Approved 2026-11-01 (docs/DATA_SOURCES.md).

A municipality becomes a top-level search area (a `cities` row + a root region) and its districts
become child regions. servicodados.ibge.gov.br was unreachable from here; the WFS serves the
same official meshes."""

import re

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crawlers.base import raise_for_block
from app.geographic.boundaries import _geom
from app.models import City, Country, Region
from app.models.enums import RegionLevel

WFS = "https://geoservicos.ibge.gov.br/geoserver/ows"
MUNICIPALITIES = "CGMAT:qg_2025_030_munic"
DISTRICTS = "CGMAT:qg_2022_630_distrito_agreg"
BOUNDARY_SOURCE = "OFFICIAL:ibge_malhas"
ATTRIBUTION = "Limites: IBGE"


def fetch_features(client: httpx.Client, layer: str, municipality: str) -> list[dict]:
    if not re.fullmatch(r"\d{7}", municipality):  # interpolated into the CQL filter
        raise ValueError(f"IBGE municipality code must have 7 digits, got {municipality!r}")
    response = client.get(
        WFS,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": layer,
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            "CQL_FILTER": f"cd_mun='{municipality}'",
        },
    )
    raise_for_block(response)
    return response.json().get("features", [])


def _by_ibge(db: Session, key: str, code: str) -> Region | None:
    return db.scalar(select(Region).where(Region.external_ids[key].astext == code))


def import_municipality(
    db: Session, client: httpx.Client, municipality: str, source_location_key: str | None
) -> dict:
    features = fetch_features(client, MUNICIPALITIES, municipality)
    if len(features) != 1:
        raise ValueError(f"expected 1 IBGE municipality {municipality}, got {len(features)}")
    props = features[0]["properties"]
    country = db.scalar(select(Country).where(Country.iso2 == "BR"))
    if country is None:
        country = Country(iso2="BR", iso3="BRA", name="Brasil", default_currency="BRL")
        db.add(country)
        db.flush()
    geom = _geom(features[0])
    ids = {"ibge_cd_mun": municipality}
    root = _by_ibge(db, "ibge_cd_mun", municipality)
    if root is None:
        city = City(country_id=country.id, name=props["nm_mun"], centroid=None)
        root = Region(level=RegionLevel.DISTRICT, source_location_ids={})
    else:
        city = db.get(City, root.city_id)
    city.admin1_code = city.admin1_name = props["sigla_uf"]
    city.geom, city.centroid = geom, func.ST_PointOnSurface(geom)
    city.boundary_source, city.external_ids = BOUNDARY_SOURCE, ids
    db.add(city)
    db.flush()
    root.city_id, root.name = city.id, f"{props['nm_mun']} ({props['sigla_uf']})"
    root.geom, root.centroid = geom, func.ST_PointOnSurface(geom)
    root.boundary_source, root.external_ids = BOUNDARY_SOURCE, ids
    if source_location_key:  # e.g. br_sp_itbi identifies São Paulo by its IBGE code
        root.source_location_ids = {**root.source_location_ids, source_location_key: municipality}
    db.add(root)
    db.flush()

    districts = 0
    for feature in fetch_features(client, DISTRICTS, municipality):
        p = feature["properties"]
        geom = _geom(feature)
        region = _by_ibge(db, "ibge_cd_dist", p["cd_dist"]) or Region(
            city_id=city.id, parent_id=root.id, level=RegionLevel.DISTRICT
        )
        region.name, region.geom, region.centroid = p["nm_dist"], geom, func.ST_PointOnSurface(geom)
        region.boundary_source, region.external_ids = (
            BOUNDARY_SOURCE,
            {"ibge_cd_dist": p["cd_dist"]},
        )
        db.add(region)
        districts += 1
    db.commit()
    return {"municipality": root.name, "region_id": root.id, "districts": districts}
