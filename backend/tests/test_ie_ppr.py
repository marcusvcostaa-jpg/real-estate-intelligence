from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.crawlers.base import RegionRef, SourceBlocked, SourceFormatChanged
from app.crawlers.ie_ppr import Connector, parse_register
from tests.ppr_fixture import CSV_TEXT, HEADER, ppr_zip

DUBLIN = RegionRef(id=1, name="County Dublin", source_location="Dublin")


def test_parse_filters_county_and_keeps_original_values():
    records = parse_register(CSV_TEXT, "Dublin")
    assert len(records) == 4  # Cork row excluded

    first = records[0]
    assert first.transaction_date == date(2024, 1, 3)
    assert first.price == Decimal("450000.00")
    assert first.currency == "EUR"
    assert first.is_full_market_price is True  # "Not Full Market Price" = No
    assert first.vat_exclusive is False
    assert first.postal_code == "D08 XY12"
    assert first.raw_payload["Price (€)"] == "€450,000.00"

    second = records[1]
    assert second.is_full_market_price is False
    assert second.vat_exclusive is True
    assert second.postal_code is None
    # Size band stays only in the raw payload; it is a range, not an area.
    assert "38 sq metres" in second.raw_payload["Property Size Description"]


def test_identical_rows_get_distinct_stable_ids():
    ids = [r.external_id for r in parse_register(CSV_TEXT, "Dublin")]
    assert len(set(ids)) == 4
    assert ids == [r.external_id for r in parse_register(CSV_TEXT, "Dublin")]


def test_unexpected_header_is_rejected():
    with pytest.raises(SourceFormatChanged):
        parse_register("Date,Address\r\n", "Dublin")
    with pytest.raises(SourceFormatChanged):
        parse_register(
            HEADER + '\r\n"01/01/2024","x","Dublin","","€abc","No","No","d",""', "Dublin"
        )


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_connector_downloads_and_parses_zip():
    def handler(request):
        return httpx.Response(200, content=ppr_zip(), headers={"content-type": "application/x-zip"})

    page = Connector(_client(handler)).search(DUBLIN, {}, None)
    assert len(page.items) == 4
    assert page.next_cursor is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403),
        httpx.Response(429),
        httpx.Response(
            200, text="<html>checking your browser</html>", headers={"content-type": "text/html"}
        ),
    ],
)
def test_connector_stops_on_block(response):
    with pytest.raises(SourceBlocked):
        Connector(_client(lambda request: response)).search(DUBLIN, {}, None)
