"""Contract between the Collector and source connectors (docs/ARCHITECTURE.md §5).

Connectors only fetch and parse. Permission gate, rate limiting, logging and storage live in
the Collector, so no connector can skip them."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol

import httpx


class SourceBlocked(Exception):
    """The source refused us (401/403/429, CAPTCHA, unexpected HTML). Never retried."""


class SourceFormatChanged(Exception):
    """The payload no longer matches what the connector expects. Needs a human."""


@dataclass(frozen=True)
class RegionRef:
    id: int
    name: str
    source_location: str | None  # how this source names the region (regions.source_location_ids)


@dataclass(frozen=True)
class TransactionRecord:
    """A transacted price from an official register. Values are as published."""

    external_id: str
    transaction_date: date
    price: Decimal
    currency: str
    is_full_market_price: bool | None
    vat_exclusive: bool | None
    address_original: str | None
    postal_code: str | None
    description_original: str | None
    raw_payload: dict


@dataclass
class SearchPage:
    items: list[TransactionRecord]
    request_url: str
    http_status: int
    next_cursor: dict | None = None
    notes: dict = field(default_factory=dict)


class Connector(Protocol):
    def __init__(self, client: httpx.Client) -> None: ...

    def search(self, region: RegionRef, filters: dict, cursor: dict | None) -> SearchPage: ...


def raise_for_block(response: httpx.Response) -> None:
    if response.status_code in (401, 403, 429):
        raise SourceBlocked(f"HTTP {response.status_code} from {response.url}")
    response.raise_for_status()
