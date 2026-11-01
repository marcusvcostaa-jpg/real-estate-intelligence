"""Operational commands (run inside the api container: python -m app.cli <command> ...).

create-user        --email you@example.com --role ADMIN   (password via REI_PASSWORD or prompt)
add-city           --iso2 IE --country-name Ireland --currency EUR --city Dublin
                   --admin1 "County Dublin" --region-name "County Dublin"
                   --lat 53.3498 --lon -6.2603 --source-location ie_ppr=Dublin
register-source    ie_ppr        (creates source + PENDING permission from the connector module)
approve-permission ie_ppr --note "..." [--reviewer admin@example.com]
collect            --source ie_ppr --region-id 1
"""

import argparse
import getpass
import importlib
import os
import sys
import time
from datetime import UTC, datetime

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app.agents.coverage_monitor import plan_jobs
from app.agents.deduplication import evaluate_against_eircode
from app.core.config import get_settings
from app.core.security import hash_password
from app.database.session import SessionLocal
from app.geographic.boundaries import import_counties, refresh_neighbors, subdivide_county
from app.models import City, Country, Region, Source, SourcePermission, User
from app.models.enums import JobStatus, PermissionStatus, RegionLevel, SourceStatus, UserRole
from app.services.collector import create_job, run_job
from app.services.coverage import refresh_region_status
from app.services.dedup import apply_dedup, load_txns
from app.validators.transactions import validate_transactions


def create_user(email: str, role: UserRole) -> None:
    password = os.environ.get("REI_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < 12:
        sys.exit("Password must have at least 12 characters.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            sys.exit(f"User {email} already exists.")
        db.add(User(email=email, password_hash=hash_password(password), role=role))
        db.commit()
    print(f"Created {role} user {email}")


def add_city(args: argparse.Namespace) -> None:
    """Country (if missing) + city + one root region. The centroid is a manual reference point
    (boundary_source=MANUAL); real boundaries are imported in Phase 5."""
    source_locations = dict(item.split("=", 1) for item in args.source_location)
    point = WKTElement(f"POINT({args.lon} {args.lat})", srid=4326)
    with SessionLocal() as db:
        country = db.scalar(select(Country).where(Country.iso2 == args.iso2))
        if country is None:
            country = Country(
                iso2=args.iso2, name=args.country_name, default_currency=args.currency
            )
            db.add(country)
            db.flush()
        city = City(
            country_id=country.id,
            admin1_name=args.admin1,
            name=args.city,
            centroid=point,
            boundary_source="MANUAL",
        )
        db.add(city)
        db.flush()
        region = Region(
            city_id=city.id,
            level=RegionLevel.DISTRICT,
            name=args.region_name or args.city,
            centroid=point,
            boundary_source="MANUAL",
            source_location_ids=source_locations,
        )
        db.add(region)
        db.commit()
        print(f"country={country.id} city={city.id} region={region.id} ({region.name})")


def register_source(code: str) -> None:
    module = importlib.import_module(f"app.crawlers.{code}")
    spec = dict(module.SOURCE)
    with SessionLocal() as db:
        if db.scalar(select(Source).where(Source.code == code)):
            sys.exit(f"Source {code} already registered.")
        iso2 = spec.pop("country_iso2", None)
        country = db.scalar(select(Country).where(Country.iso2 == iso2)) if iso2 else None
        if iso2 and country is None:
            sys.exit(f"Country {iso2} not found; run add-city first.")
        source = Source(**spec, country_id=country.id if country else None)
        db.add(source)
        db.flush()
        db.add(SourcePermission(source_id=source.id, **module.PERMISSION))
        db.commit()
        print(f"Registered source {code} (id={source.id}); permission is PENDING until approved.")


def approve_permission(code: str, note: str, reviewer: str | None) -> None:
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.code == code))
        if source is None:
            sys.exit(f"Source {code} not found.")
        permission = db.scalar(
            select(SourcePermission).where(
                SourcePermission.source_id == source.id,
                SourcePermission.status == PermissionStatus.PENDING,
            )
        )
        if permission is None:
            sys.exit(f"No PENDING permission for {code}.")
        reviewer_id = None
        if reviewer:
            user = db.scalar(select(User).where(User.email == reviewer))
            if user is None or user.role != UserRole.ADMIN:
                sys.exit(f"{reviewer} is not an ADMIN user.")
            reviewer_id = user.id
        now = datetime.now(UTC)
        permission.status, permission.granted_at, permission.reviewed_by = (
            PermissionStatus.APPROVED,
            now,
            reviewer_id,
        )
        source.status = SourceStatus.ACTIVE
        source.notes = f"{source.notes or ''}\n[{now:%Y-%m-%d}] Permission approved: {note}".strip()
        db.commit()
        print(f"Permission {permission.id} for {code} APPROVED; source is ACTIVE.")


def collect(code: str, region_id: int) -> None:
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.code == code))
        if source is None:
            sys.exit(f"Source {code} not found.")
        job = create_job(db, region_id, source.id, {}, "MANUAL")
        job = run_job(db, job.id)
        print(
            f"job={job.id} status={job.status} pages={job.pages_processed} "
            f"records={job.listings_found} new={job.new_listings} "
            f"already_known={job.duplicates} error={job.last_error}"
        )


def _source_id(db, code: str) -> int:
    source = db.scalar(select(Source).where(Source.code == code))
    if source is None:
        sys.exit(f"Source {code} not found.")
    return source.id


def validate(code: str) -> None:
    with SessionLocal() as db:
        print(validate_transactions(db, _source_id(db, code)))


def dedup(code: str) -> None:
    with SessionLocal() as db:
        for key, value in sorted(apply_dedup(db, _source_id(db, code)).items()):
            print(f"{key}: {value}")


def dedup_eval(code: str, thresholds: list[float]) -> None:
    with SessionLocal() as db:
        txns = load_txns(db, _source_id(db, code))
    for threshold in thresholds:
        m = evaluate_against_eircode(txns, auto_link=threshold)
        print(
            f"auto_link>={threshold:g}: precision={m['precision']:.4f} recall={m['recall']:.4f} "
            f"true_pairs={m['true_pairs']} predicted_pairs={m['predicted_pairs']} "
            f"review_pairs={m['review_pairs']} (n={m['transactions']})"
        )


def import_boundaries(source_location: str | None, subdivide: list[str]) -> None:
    headers = {"User-Agent": get_settings().scraper_user_agent}
    with SessionLocal() as db, httpx.Client(headers=headers, timeout=120) as client:
        print(import_counties(db, client, source_location))
        for county in subdivide:
            print(county, subdivide_county(db, client, county))
        refresh_neighbors(db)
        for region_id in db.scalars(select(Region.id).where(Region.parent_id.is_(None))):
            refresh_region_status(db, region_id)
        db.commit()


def expand(code: str, max_jobs: int, run: bool) -> None:
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.code == code))
        if source is None:
            sys.exit(f"Source {code} not found.")
        jobs = plan_jobs(db, source, max_jobs)
        for job in jobs:
            region = db.get(Region, job.region_id)
            print(f"planned job={job.id} {job.triggered_by} region={region.name}")
            if run:
                job = run_job(db, job.id)
                # Rate limit hit: wait for the allowed slot (bounded) instead of skipping.
                while job.status == JobStatus.QUEUED and job.scheduled_for:
                    wait = (job.scheduled_for - datetime.now(UTC)).total_seconds()
                    if wait > 180:
                        break
                    print(f"  rate limited, waiting {max(wait, 0):.0f}s")
                    time.sleep(max(wait, 0) + 1)
                    job = run_job(db, job.id)
                print(
                    f"  -> {job.status} records={job.listings_found} new={job.new_listings} "
                    f"error={job.last_error}"
                )
        if not jobs:
            print("nothing to do: no due refresh and no unsearched neighbour of a completed area")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-user")
    p.add_argument("--email", required=True)
    p.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.VIEWER)

    p = sub.add_parser("add-city")
    for name in ("--iso2", "--country-name", "--currency", "--city"):
        p.add_argument(name, required=True)
    p.add_argument("--admin1")
    p.add_argument("--region-name")
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--source-location", action="append", default=[], metavar="CODE=NAME")

    p = sub.add_parser("register-source")
    p.add_argument("code")

    p = sub.add_parser("approve-permission")
    p.add_argument("code")
    p.add_argument("--note", required=True)
    p.add_argument("--reviewer")

    p = sub.add_parser("collect")
    p.add_argument("--source", required=True)
    p.add_argument("--region-id", type=int, required=True)

    for name in ("validate", "dedup"):
        sub.add_parser(name).add_argument("--source", required=True)
    p = sub.add_parser("dedup-eval")
    p.add_argument("--source", required=True)
    p.add_argument("--thresholds", type=float, nargs="+", default=[90, 95, 98, 101])

    p = sub.add_parser("import-boundaries")
    p.add_argument("--source-location", help="source code whose county names match (e.g. ie_ppr)")
    p.add_argument("--subdivide", action="append", default=[], metavar="COUNTY")

    p = sub.add_parser("expand")
    p.add_argument("--source", required=True)
    p.add_argument("--max", type=int, default=3)
    p.add_argument("--run", action="store_true")

    args = parser.parse_args()
    match args.command:
        case "create-user":
            create_user(args.email.strip(), UserRole(args.role))
        case "add-city":
            add_city(args)
        case "register-source":
            register_source(args.code)
        case "approve-permission":
            approve_permission(args.code, args.note, args.reviewer)
        case "collect":
            collect(args.source, args.region_id)
        case "validate":
            validate(args.source)
        case "dedup":
            dedup(args.source)
        case "dedup-eval":
            dedup_eval(args.source, args.thresholds)
        case "import-boundaries":
            import_boundaries(args.source_location, args.subdivide)
        case "expand":
            expand(args.source, args.max, args.run)


if __name__ == "__main__":
    main()
