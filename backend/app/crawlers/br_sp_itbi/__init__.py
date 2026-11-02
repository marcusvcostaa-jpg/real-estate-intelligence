"""ITBI transactions of the City of São Paulo, published by the Secretaria Municipal da Fazenda.

One XLSX per year (one sheet per month of tax payment), listed on the Fazenda transparency page.
Each row is a paid Declaração de Transações Imobiliárias: a TRANSACTED price declared to the tax
authority (it may be below the negotiated price), never a listing. Publication is required by
Lei municipal 18.161/2024 (art. 18-A), without buyer/seller identification.
Permission evidence: docs/DATA_SOURCES.md (checked and approved 2026-11-01)."""

import hashlib
import io
import re
import unicodedata
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import openpyxl

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

INDEX_URL = "https://prefeitura.sp.gov.br/web/fazenda/w/acesso_a_informacao/31501"
MUNICIPALITY = "3550308"  # IBGE code of São Paulo; the only region this source covers
YEARS_BACK = 5  # art. 18-A: the city publishes the last 5 years (files exist back to 2006)
MAX_MALFORMED = 0.01  # a few shifted rows are tolerated and skipped; more means a new layout

SOURCE = {
    "code": "br_sp_itbi",
    "name": "Transações imobiliárias com ITBI — Prefeitura de São Paulo (SF)",
    "country_iso2": "BR",
    "base_url": "https://prefeitura.sp.gov.br",
    "integration_type": IntegrationType.OPEN_DATA,
    "has_api": False,
    "rate_limit_per_minute": 1,
    "daily_request_budget": 4,  # pages (one year file each = index page + conditional download)
    "min_refresh_interval": timedelta(days=30),  # current-year file is updated monthly
    "available_fields": [
        "sql",
        "address",
        "cep",
        "transaction_nature",
        "declared_value",
        "transaction_date",
        "reference_value",
        "share_transferred",
        "financing",
        "registry_office",
        "registry_number",
        "iptu_land_area",
        "iptu_built_area",
        "iptu_use",
        "iptu_standard",
        "iptu_construction_year",
    ],
}

PERMISSION = {
    "permission_type": PermissionType.OPEN_DATA_LICENSE,
    "license_name": "Public data under mandatory active transparency (Lei municipal SP "
    "18.161/2024, art. 18-A; Lei 17.901/2023 Política Municipal de Dados Abertos). "
    "No explicit licence stated on the page.",
    "evidence_url": INDEX_URL,
    "evidence_document": (
        "Checked 2026-11-01: Fazenda page lists yearly XLSX/ODS 2006-2026, current year updated "
        "monthly; city announcement says data is for use by the population and researchers and "
        "omits buyer/seller names; Lei 18.161/2024 art. 18-A requires monthly publication 'para "
        "consulta geral dos interessados' of SQL, matrícula, cartório, full address, declared "
        "value, reference value, date and nature, without buyer/seller identification; "
        "prefeitura.sp.gov.br and drive.prefeitura.sp.gov.br robots.txt allow /; 2026 file "
        "Last-Modified 2026-09-30, 31.9 MB."
    ),
    "scope": "Download the yearly ITBI files of the last 5 years for the City of São Paulo and "
    "store them as transacted (declared) prices; display and analyse them with attribution.",
    "restrictions": (
        "Attribute the Prefeitura de São Paulo / Secretaria Municipal da Fazenda; declared values "
        "may be below negotiated prices; rows are grouped by month of tax payment; rural, PPI and "
        "Auto de Infração transactions are excluded by the source; never store buyer/seller "
        "identification (rows that leak it are malformed and skipped). One file per page, "
        "conditional GET, monthly refresh."
    ),
    "attribution_required": True,
    "attribution_text": "Fonte: Prefeitura de São Paulo — Secretaria Municipal da Fazenda "
    "(transações imobiliárias com ITBI).",
    "robots_txt_checked_at": datetime(2026, 11, 1, tzinfo=UTC),
}

# Normalized header (no accents, lowercase) -> field. Matched exactly so a renamed column fails.
COLUMNS = {
    "n do cadastro (sql)": "sql",
    "nome do logradouro": "street",
    "numero": "number",
    "complemento": "complement",
    "bairro": "neighbourhood",
    "cep": "cep",
    "natureza de transacao": "nature",
    "valor de transacao (declarado pelo contribuinte)": "value",
    "data de transacao": "date",
    "proporcao transmitida (%)": "share",
    "fracao ideal": "ideal_fraction",
    "area do terreno (m2)": "land_area",
    "area construida (m2)": "built_area",
    "uso (iptu)": "use_code",
    "descricao do uso (iptu)": "use_desc",
}
_MONTH_SHEET = re.compile(r"[A-Z]{3}-\d{4}")
_UNIT = re.compile(r"\b(AP|APTO|APART\w*|UNID\w*|CJ|CONJ\w*|SALA|STUDIO|LOJA)\W*\d", re.IGNORECASE)
_YEAR_LINK = re.compile(
    r"\b(20\d{2})\s*(?:<[^>]+>\s*)*\(\s*(?:<[^>]+>\s*)*<a[^>]+href=\"([^\"]+\.xlsx)\"[^>]*>"
    r"\s*(?:<[^>]+>\s*)*Excel/xlsx",
    re.IGNORECASE,
)


def _norm(text: object) -> str:
    # "Nº"/"N°" both occur in the published headers; ordinal and degree signs are dropped.
    text = str(text or "").replace("º", "").replace("°", "")
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().split())


def year_links(index_html: str) -> dict[int, str]:
    """{year: xlsx url} from the Fazenda page ("2025 ( Excel/xlsx ) ( ODS )")."""
    links: dict[int, str] = {}
    for year, url in _YEAR_LINK.findall(index_html):
        links.setdefault(int(year), url.replace(" ", "%20"))
    if not links:
        raise SourceFormatChanged("no yearly ITBI xlsx link found on the index page")
    return links


def _whole(share: object) -> bool:
    return isinstance(share, int | float) and share == 100


def _classify(use_code: object, use_desc: str) -> tuple[str, str]:
    """(property_type, category) from the IPTU use of the SQL."""
    desc = _norm(use_desc)
    if use_code == 0:
        return "LAND", "LAND"
    if desc.startswith("apartamento"):
        return "APARTMENT", "RESIDENTIAL"
    if desc == "residencia":
        return "HOUSE", "RESIDENTIAL"
    if desc.startswith("residencia") or "predominancia residencial" in desc:
        return "OTHER_RESIDENTIAL", "RESIDENTIAL"
    if "garagem" in desc:
        return "PARKING", "OTHER"
    return "NON_RESIDENTIAL", "COMMERCIAL"


def _area(value: object) -> Decimal | None:
    return Decimal(str(value)) if isinstance(value, int | float) and value > 0 else None


def parse_row(row: dict, raw: dict, occurrences: Counter) -> TransactionRecord | None:
    """One published row (by field; `raw` = as published) -> record, or None if the row is
    malformed (shifted columns)."""
    sql, when, value = row.get("sql"), row.get("date"), row.get("value")
    if not (isinstance(sql, int) and isinstance(when, datetime) and isinstance(value, int | float)):
        return None
    nature = str(row.get("nature") or "").strip()
    nature_code = nature.split(".", 1)[0].strip()
    complement = str(row.get("complement") or "").strip()
    share = row.get("share")
    whole = _whole(share)
    # The SQL identifies the property when the whole of it is transferred. A fraction is either
    # a share of the property or an off-plan unit declared on the plot's SQL (the complement
    # does not reliably name the unit: real files show 163 "0.2%" sales with no complement).
    # Some "100%" rows also name a unit ("apartamento 122") on a plot that is not a condominium
    # (ideal fraction 1): the SQL is the plot, not the unit. Neither identifies the property, so
    # they get no key (each stays its own property) and no IPTU attributes.
    # ponytail: misses repeat sales of off-plan units; link them when the IPTU split is known.
    plot_for_unit = row.get("ideal_fraction") == 1 and bool(_UNIT.search(complement))
    identifies = whole and not plot_for_unit
    key = f"sql:{sql:011d}" if identifies else None
    if nature_code != "1":
        market = False  # donations-in-payment, auctions, capital contributions, swaps, ...
    elif whole:
        market = True
    else:
        market = None  # a share of a property or an off-plan unit: not distinguishable here
    use = (row.get("use_code"), str(row.get("use_desc") or ""))
    property_type, category = _classify(*use) if identifies else (None, None)
    # IPTU areas describe the SQL as registered today; only meaningful when it is the property.
    # Built area of a condo unit includes its share of common areas (basis BUILT); the plot area
    # of a condo unit is the whole plot, so land area is kept only outside condominiums.
    built = _area(row.get("built_area")) if identifies else None
    land = _area(row.get("land_area")) if identifies and row.get("ideal_fraction") == 1 else None

    street, number = str(row.get("street") or "").strip(), row.get("number")
    address = ", ".join(str(p) for p in (street, number or None, complement or None) if p)
    if row.get("neighbourhood"):
        address += f" - {str(row['neighbourhood']).strip()}"
    cep = row.get("cep")
    identity = "\x1f".join(
        str(x) for x in (sql, when.date().isoformat(), value, nature_code, complement, share)
    )
    occurrences[identity] += 1
    return TransactionRecord(
        external_id=hashlib.sha256(f"{identity}\x1f{occurrences[identity]}".encode()).hexdigest(),
        transaction_date=when.date(),
        price=Decimal(str(value)).quantize(Decimal("0.01")),
        currency="BRL",
        is_full_market_price=market,
        vat_exclusive=False,  # no VAT on property transfers in Brazil: the value is the price
        address_original=address or None,
        postal_code=f"{cep:08d}"[:5] + "-" + f"{cep:08d}"[5:] if isinstance(cep, int) else None,
        description_original=nature or None,
        raw_payload=raw,
        source_property_key=key,
        built_area_m2=built,
        land_area_m2=land,
        property_type=property_type,
        category=category,
    )


def _clean(value: object) -> object:
    """Older files store every number as float (SQL 100800297.0): integral floats -> int, so
    types and stable ids match the files that store ints."""
    return int(value) if isinstance(value, float) and value.is_integer() else value


def _header(first_row: tuple) -> list[str | None]:
    return [str(h).strip() if h is not None else None for h in first_row]


def _fields(header: list[str | None]) -> dict[int, str]:
    return {i: COLUMNS[_norm(h)] for i, h in enumerate(header) if h and _norm(h) in COLUMNS}


def parse_workbook(content: bytes) -> tuple[list[TransactionRecord], int]:
    """Records of every monthly sheet, and the number of malformed rows skipped."""
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    sheets = [s for s in workbook.worksheets if _MONTH_SHEET.fullmatch(s.title)]  # skip legends
    # Some sheets were published without the header row (2024: JAN, OUT). They use the header of
    # the other months of the same file, but only if they have exactly as many columns.
    firsts = {s.title: next(s.iter_rows(values_only=True), ()) for s in sheets}
    canonical = next(
        (_header(r) for r in firsts.values() if len(_fields(_header(r))) == len(COLUMNS)), None
    )
    records, malformed, occurrences = [], 0, Counter()
    for sheet in sheets:
        rows = sheet.iter_rows(values_only=True)
        first = next(rows, ())
        header = _header(first)
        if not _fields(header) and canonical and len(first) == len(canonical):
            header, rows = canonical, sheet.iter_rows(values_only=True)  # first row is data
        fields = _fields(header)
        missing = set(COLUMNS.values()) - set(fields.values())
        if missing:
            raise SourceFormatChanged(f"sheet {sheet.title}: missing columns {sorted(missing)}")
        for values in rows:
            if not any(v not in (None, "") for v in values):
                continue
            raw = {
                h: (v.isoformat() if isinstance(v, datetime | date | time) else v)
                for h, v in zip(header, values, strict=False)
                if h and v not in (None, "")
            }
            row = {f: _clean(values[i]) for i, f in fields.items() if i < len(values)}
            record = parse_row(row, raw, occurrences)
            if record is None:
                malformed += 1  # never stored: shifted rows can carry party names
                continue
            records.append(record)
    total = len(records) + malformed
    if total == 0:
        raise SourceFormatChanged("no monthly sheet with rows")
    if malformed / total > MAX_MALFORMED:
        raise SourceFormatChanged(f"{malformed} of {total} rows malformed")
    return records, malformed


class Connector:
    """Pages are years, newest first: the cursor walks back YEARS_BACK years from the latest
    file listed. Files are cached and re-requested with If-Modified-Since, so a refresh costs
    304s for past years and one download for the current year."""

    def __init__(self, client: httpx.Client, cache_dir: Path | None = None) -> None:
        self.client = client
        self.cache_dir = (cache_dir or Path(get_settings().cache_dir)) / "br_sp_itbi"

    def _get(self, url: str, **kwargs) -> httpx.Response:
        response = self.client.get(url, follow_redirects=True, **kwargs)
        if response.status_code != 304:
            raise_for_block(response)
        return response

    def _download(self, year: int, url: str) -> tuple[bytes, int, str | None]:
        data, stamp = self.cache_dir / f"{year}.xlsx", self.cache_dir / f"{year}.last-modified"
        headers = {}
        if data.exists() and stamp.exists():
            headers["If-Modified-Since"] = stamp.read_text()
        response = self._get(url, headers=headers)
        if response.status_code == 304:
            return data.read_bytes(), 304, stamp.read_text()
        if "spreadsheetml" not in response.headers.get("content-type", ""):
            raise SourceBlocked(f"expected XLSX, got {response.headers.get('content-type')!r}")
        last_modified = response.headers.get("last-modified")
        if last_modified:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            data.write_bytes(response.content)
            stamp.write_text(last_modified)
        return response.content, response.status_code, last_modified

    def search(self, region: RegionRef, filters: dict, cursor: dict | None) -> SearchPage:
        if region.source_location != MUNICIPALITY:
            raise ValueError(f"region {region.id} is not mapped to São Paulo ({MUNICIPALITY})")
        index = self._get(INDEX_URL)
        if "html" not in index.headers.get("content-type", ""):
            raise SourceBlocked(f"index is {index.headers.get('content-type')!r}, not HTML")
        links = year_links(index.text)
        latest = max(links)
        year = cursor["year"] if cursor else latest
        if year not in links:
            raise SourceFormatChanged(f"no ITBI file listed for {year}")
        content, status, last_modified = self._download(year, links[year])
        records, malformed = parse_workbook(content)
        oldest = latest - YEARS_BACK + 1
        return SearchPage(
            items=records,
            request_url=links[year],
            http_status=status,
            next_cursor={"year": year - 1} if year > oldest else None,
            notes={"year": year, "last_modified": last_modified, "malformed_skipped": malformed},
        )
