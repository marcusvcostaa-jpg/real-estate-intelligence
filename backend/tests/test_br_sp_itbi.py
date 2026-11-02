import json
from datetime import date, datetime, time
from decimal import Decimal

import httpx
import pytest

from app.crawlers.base import RegionRef, SourceBlocked, SourceFormatChanged
from app.crawlers.br_sp_itbi import Connector, parse_workbook, year_links
from tests.itbi_fixture import HEADER, INDEX_HTML, MALFORMED, ROWS, itbi_xlsx

SAO_PAULO = RegionRef(id=1, name="São Paulo", source_location="3550308")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_year_links_reads_each_year_once():
    links = year_links(INDEX_HTML)
    assert sorted(links) == [2021, 2022, 2023, 2024, 2025, 2026]
    assert links[2026] == "https://example.test/itbi/GUIAS%20(30092026).xlsx"  # not the .ods
    assert links[2025] == "https://example.test/itbi/GUIAS%20DE%20ITBI%202025%20XLS.xlsx"
    with pytest.raises(SourceFormatChanged):
        year_links("<html>no files</html>")


def test_parse_maps_fields_and_keeps_original_values():
    records, malformed = parse_workbook(itbi_xlsx())
    assert malformed == 0 and len(records) == 6  # legend sheet ignored

    first = records[0]
    assert first.transaction_date == date(2025, 3, 1)
    assert first.price == Decimal("500000.00") and first.currency == "BRL"
    assert first.is_full_market_price is True and first.vat_exclusive is False
    assert first.postal_code == "01234-000"  # leading zero restored
    assert first.address_original == "R EXEMPLO, 10, AP 12 E 1VG - VILA TESTE"
    assert first.description_original == "1.Compra e venda"
    assert first.raw_payload["Valor de Transação (declarado pelo contribuinte)"] == 500000
    assert first.raw_payload["Data de Transação"] == "2025-03-01T00:00:00"
    # Whole condo unit: built area (includes common-area share) yes, plot area no.
    assert first.built_area_m2 == Decimal("80") and first.land_area_m2 is None
    assert (first.property_type, first.category) == ("APARTMENT", "RESIDENTIAL")
    assert records[1].price == Decimal("650000.50")


def test_property_key_market_flag_and_areas_follow_the_share_transferred():
    r = parse_workbook(itbi_xlsx())[0]
    # Same SQL, whole transfer: same property despite different complement text.
    assert r[0].source_property_key == r[1].source_property_key == "sql:01234567890"
    # Fractions of the plot's SQL (off-plan units or shares): no key, nothing inferred.
    assert r[2].source_property_key is None and r[3].source_property_key is None
    assert r[2].is_full_market_price is None
    assert (r[2].built_area_m2, r[2].land_area_m2, r[2].category) == (None, None, None)
    # House outside a condominium: plot area belongs to it.
    assert r[4].land_area_m2 == Decimal("250") and r[4].property_type == "HOUSE"
    # Capital contribution is never a market sale.
    assert r[5].is_full_market_price is False


def test_identical_rows_get_distinct_stable_ids():
    twice = itbi_xlsx(rows=[ROWS[0], ROWS[0]])
    ids = [r.external_id for r in parse_workbook(twice)[0]]
    assert len(set(ids)) == 2
    assert ids == [r.external_id for r in parse_workbook(twice)[0]]


def test_malformed_rows_are_skipped_and_never_stored():
    many = [ROWS[0]] * 150
    records, malformed = parse_workbook(itbi_xlsx(rows=many, extra_rows=[MALFORMED]))
    assert (len(records), malformed) == (150, 1)
    assert not any("EMPRESA" in str(r.raw_payload) for r in records)
    with pytest.raises(SourceFormatChanged):  # too many: the layout changed
        parse_workbook(itbi_xlsx(rows=ROWS[:2], extra_rows=[MALFORMED]))


def test_missing_column_is_rejected():
    header = [h for h in HEADER if h != "Proporção Transmitida (%)"]
    with pytest.raises(SourceFormatChanged):
        parse_workbook(itbi_xlsx(rows=[], header=header))


def _connector(handler, tmp_path) -> Connector:
    return Connector(httpx.Client(transport=httpx.MockTransport(handler)), cache_dir=tmp_path)


def _ok(request):
    if request.url.path.endswith(".xlsx"):
        return httpx.Response(
            200,
            content=itbi_xlsx(),
            headers={"content-type": XLSX, "last-modified": "Wed, 30 Sep 2026 13:52:43 GMT"},
        )
    return httpx.Response(200, text=INDEX_HTML, headers={"content-type": "text/html"})


def test_connector_walks_back_five_years(tmp_path):
    connector = _connector(_ok, tmp_path)
    page = connector.search(SAO_PAULO, {}, None)
    assert page.notes["year"] == 2026 and len(page.items) == 6
    assert page.next_cursor == {"year": 2025}
    last = connector.search(SAO_PAULO, {}, {"year": 2022})
    assert last.next_cursor is None  # 2026..2022 = 5 years; 2021 is not fetched


def test_connector_uses_cache_on_304(tmp_path):
    _connector(_ok, tmp_path).search(SAO_PAULO, {}, None)
    seen = []

    def not_modified(request):
        if request.url.path.endswith(".xlsx"):
            seen.append(request.headers.get("if-modified-since"))
            return httpx.Response(304)
        return _ok(request)

    page = _connector(not_modified, tmp_path).search(SAO_PAULO, {}, None)
    assert seen == ["Wed, 30 Sep 2026 13:52:43 GMT"]
    assert page.http_status == 304 and len(page.items) == 6


@pytest.mark.parametrize("status", [401, 403, 429])
def test_connector_stops_on_block(tmp_path, status):
    with pytest.raises(SourceBlocked):
        _connector(lambda request: httpx.Response(status), tmp_path).search(SAO_PAULO, {}, None)


def test_connector_stops_on_html_instead_of_xlsx(tmp_path):
    def handler(request):
        if request.url.path.endswith(".xlsx"):
            return httpx.Response(200, text="<html>aguarde</html>",
                                  headers={"content-type": "text/html"})  # fmt: skip
        return _ok(request)

    with pytest.raises(SourceBlocked):
        _connector(handler, tmp_path).search(SAO_PAULO, {}, None)


def test_connector_refuses_other_regions(tmp_path):
    with pytest.raises(ValueError):
        _connector(_ok, tmp_path).search(RegionRef(2, "Dublin", "Dublin"), {}, None)


def test_unit_declared_on_a_plot_sql_does_not_identify_the_property():
    from collections import Counter

    from app.crawlers.br_sp_itbi import parse_row
    from tests.itbi_fixture import row

    values = row(1112223334, "R LOTE", 1, "APTO 7", None, 1000000, "1.Compra e venda", 300000,
                 datetime(2026, 1, 5), 100, 1, 900, 400, 81, "INDÚSTRIA")  # fmt: skip
    fields = dict(zip(
        ["sql", "street", "number", "complement", "neighbourhood", "_ref", "cep", "nature", "value",
         "date", "_vvr", "share", "_vvrp", "_base", "_fin", "_finv", "_cart", "_mat", "_sit",
         "land_area", "_test", "ideal_fraction", "built_area", "use_code", "use_desc"],
        values, strict=False))  # fmt: skip
    r = parse_row(fields, {}, Counter())
    assert r.source_property_key is None
    assert (r.category, r.built_area_m2, r.land_area_m2) == (None, None, None)
    assert r.is_full_market_price is True  # still a whole-unit sale


def test_raw_payload_is_json_serializable():
    odd = list(ROWS[0])
    odd[5] = time(13, 52)  # a time-of-day cell seen in the real 2026 file
    records, _ = parse_workbook(itbi_xlsx(rows=[odd]))
    assert json.loads(json.dumps(records[0].raw_payload))["Referência"] == "13:52:00"


def test_sheet_without_header_uses_the_files_header_and_float_numbers():
    import io

    import openpyxl

    from tests.itbi_fixture import HEADER, ROWS

    workbook = openpyxl.Workbook()
    nameless = workbook.active
    nameless.title = "JAN-2024"  # published without header row, every number as float
    nameless.append([float(v) if isinstance(v, int) else v for v in ROWS[0]])
    other = workbook.create_sheet("FEV-2024")
    other.append(HEADER)
    other.append(ROWS[0])
    buf = io.BytesIO()
    workbook.save(buf)
    records, malformed = parse_workbook(buf.getvalue())
    assert malformed == 0 and len(records) == 2
    floaty, plain = records
    assert floaty.source_property_key == plain.source_property_key == "sql:01234567890"
    assert floaty.postal_code == "01234-000" and floaty.is_full_market_price is True
    # Int or float form of the same row has the same identity (hence the 2nd occurrence).
    assert floaty.external_id != plain.external_id  # 2nd occurrence within the file
    assert floaty.raw_payload["Nº do Cadastro (SQL)"] == 1234567890.0  # kept as published
