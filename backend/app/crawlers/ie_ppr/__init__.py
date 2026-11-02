"""Residential Property Price Register (Ireland), published by the PSRA.

Official open data: one ZIP with the whole national register (CSV, cp1252). We keep only the
rows of the county mapped to the region. Records are TRANSACTED prices, not listings.
Permission evidence: docs/DATA_SOURCES.md (checked 2026-11-01)."""

import csv
import hashlib
import io
import zipfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.crawlers.base import (
    RegionRef,
    SearchPage,
    SourceBlocked,
    SourceFormatChanged,
    TransactionRecord,
    raise_for_block,
)
from app.models.enums import IntegrationType, PermissionType

DOWNLOAD_URL = (
    "https://www.propertypriceregister.ie/website/npsra/ppr/npsra-ppr.nsf/"
    "Downloads/PPR-ALL.zip/$FILE/PPR-ALL.zip"
)
EXPECTED_COLUMNS = 9
COL_DATE, COL_ADDRESS, COL_COUNTY, COL_EIRCODE, COL_PRICE = 0, 1, 2, 3, 4
COL_NOT_FULL_MARKET, COL_VAT_EXCLUSIVE, COL_DESCRIPTION = 5, 6, 7

SOURCE = {
    "code": "ie_ppr",
    "name": "Residential Property Price Register (PSRA)",
    "country_iso2": "IE",
    "base_url": "https://www.propertypriceregister.ie",
    "integration_type": IntegrationType.OPEN_DATA,
    "has_api": False,
    "rate_limit_per_minute": 1,
    "daily_request_budget": 4,
    "min_refresh_interval": timedelta(days=7),
    "available_fields": [
        "transaction_date",
        "address",
        "county",
        "eircode",
        "price",
        "not_full_market_price",
        "vat_exclusive",
        "description_of_property",
        "property_size_description",
    ],
}

PERMISSION = {
    "permission_type": PermissionType.OPEN_DATA_LICENSE,
    "license_name": "PSRA re-use of public sector information policy; "
    "Dublin subset on data.gov.ie licensed CC BY 4.0",
    "evidence_url": "https://www.psr.ie/re-use-of-public-sector-information/",
    "evidence_document": (
        "Checked 2026-11-01: PSRA re-use page (last updated 2022-07-29) allows free re-use in "
        "any format incl. publishing; data.gov.ie dataset 'dublin-residential-property-price-"
        "register' lists CC BY 4.0 (publisher PSRA); propertypriceregister.ie/robots.txt "
        "returns 404; PPR-ALL.zip Last-Modified 2026-10-28."
    ),
    "scope": "Download the official PPR-ALL.zip and store residential sales of the counties "
    "reached by coverage expansion (Dublin first; neighbours approved 2026-11-01) as "
    "transacted prices; display and analyse them with attribution.",
    "restrictions": (
        "Acknowledge source and PSRA copyright when supplying data to others; reproduce "
        "accurately; do not use in a misleading way (not a price index; '**' prices are not "
        "full market value; VAT-exclusive prices flagged); not principally for advertising; "
        "not for illegal purposes. Max 1 download per run, weekly refresh."
    ),
    "attribution_required": True,
    "attribution_text": "Source: Residential Property Price Register, Property Services "
    "Regulatory Authority (PSRA). © PSRA.",
    "robots_txt_checked_at": datetime(2026, 11, 1, tzinfo=UTC),
}

_YES_NO = {"Yes": True, "No": False}


def parse_price(text: str) -> Decimal:
    cleaned = text.replace("€", "").replace(",", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise SourceFormatChanged(f"unparseable price {text!r}") from None


def parse_register(csv_text: str, county: str) -> list[TransactionRecord]:
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader, [])
    if len(header) != EXPECTED_COLUMNS or not header[COL_DATE].startswith("Date of Sale"):
        raise SourceFormatChanged(f"unexpected header: {header}")

    occurrences: Counter[str] = Counter()
    records = []
    for row in reader:
        if len(row) != EXPECTED_COLUMNS:
            raise SourceFormatChanged(f"row with {len(row)} columns: {row}")
        if row[COL_COUNTY] != county:
            continue
        # Identical rows are legitimate (e.g. units sold together); the occurrence number keeps
        # them distinct while staying stable across downloads.
        key = "\x1f".join(row)
        occurrences[key] += 1
        external_id = hashlib.sha256(f"{key}\x1f{occurrences[key]}".encode()).hexdigest()
        records.append(
            TransactionRecord(
                external_id=external_id,
                transaction_date=datetime.strptime(row[COL_DATE], "%d/%m/%Y").date(),
                price=parse_price(row[COL_PRICE]),
                currency="EUR",
                # Column says "Not Full Market Price": "No" means it IS a full market price.
                is_full_market_price={"No": True, "Yes": False}.get(row[COL_NOT_FULL_MARKET]),
                vat_exclusive=_YES_NO.get(row[COL_VAT_EXCLUSIVE]),
                address_original=row[COL_ADDRESS].strip() or None,
                postal_code=row[COL_EIRCODE].strip() or None,
                description_original=row[COL_DESCRIPTION].strip() or None,
                raw_payload=dict(zip(header, row, strict=True)),
                category="RESIDENTIAL",  # the register covers residential sales only
            )
        )
    return records


class Connector:
    """One national file serves every county: it is cached on disk and re-requested with
    If-Modified-Since, so searching several counties costs the source a 304, not 19 MB each."""

    def __init__(self, client: httpx.Client, cache_dir: Path | None = None) -> None:
        self.client = client
        self.cache_dir = (cache_dir or Path(get_settings().cache_dir)) / "ie_ppr"

    def _download(self) -> tuple[bytes, int, str | None]:
        archive, stamp = self.cache_dir / "PPR-ALL.zip", self.cache_dir / "last-modified"
        headers = {}
        if archive.exists() and stamp.exists():
            headers["If-Modified-Since"] = stamp.read_text()
        response = self.client.get(DOWNLOAD_URL, headers=headers)
        if response.status_code == 304:
            return archive.read_bytes(), 304, stamp.read_text()
        raise_for_block(response)
        if "zip" not in response.headers.get("content-type", ""):
            # An HTML page instead of the ZIP may be a block or maintenance page: stop, don't parse.
            raise SourceBlocked(f"expected ZIP, got {response.headers.get('content-type')!r}")
        last_modified = response.headers.get("last-modified")
        if last_modified:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(response.content)
            stamp.write_text(last_modified)
        return response.content, response.status_code, last_modified

    def search(self, region: RegionRef, filters: dict, cursor: dict | None) -> SearchPage:
        if not region.source_location:
            raise ValueError(f"region {region.id} has no ie_ppr county mapping")
        content, status, last_modified = self._download()
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = [m for m in archive.namelist() if m.lower().endswith(".csv")]
            if len(members) != 1:
                raise SourceFormatChanged(f"expected one CSV in ZIP, got {members}")
            csv_text = archive.read(members[0]).decode("cp1252")
        return SearchPage(
            items=parse_register(csv_text, region.source_location),
            request_url=DOWNLOAD_URL,
            http_status=status,
            notes={"last_modified": last_modified},
        )
