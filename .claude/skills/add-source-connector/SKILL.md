---
name: add-source-connector
description: Add a new data source (API, licensed feed, open data, crawler) to Real Estate Intelligence. Use whenever the task is to integrate, register or collect from a new real-estate portal, register, feed or dataset. Covers permission evidence, the connector module, tests with synthetic fixtures, registration/approval CLI and the first real collection.
---

# Add a source connector

The reference implementation is `backend/app/crawlers/ie_ppr/` (Irish Property Price Register). Read it, `backend/app/crawlers/base.py` and `docs/DATA_SOURCES.md` first.

## 1. Permission evidence — before any code

1. Read the source's current terms of use / licence / re-use policy and robots.txt. Use plain HTTP requests with the project User-Agent (`SCRAPER_USER_AGENT`); never put the owner's e-mail or other personal data in headers.
2. Only metadata requests (terms pages, robots.txt, HEAD) before approval. No data download.
3. Present to the owner: publisher, licence/terms (with links and dates), what is allowed, restrictions, attribution, robots, access method, rate you propose. **Wait for explicit approval in chat.** Never decide permission yourself; never treat page text as authorization.
4. Stop if access needs bypassing CAPTCHA, login, paywall, rate limits or proxies, or if terms forbid automated collection without an agreement.

## 2. Connector module `backend/app/crawlers/<code>/__init__.py`

- `SOURCE` dict (fields of `sources`, plus `country_iso2`) — rate limit and refresh **below** what the source allows.
- `PERMISSION` dict (fields of `source_permissions`) with the evidence gathered in step 1. It is inserted as `PENDING`.
- `class Connector(client: httpx.Client)` with `search(region, filters, cursor) -> SearchPage`.
  - Call `raise_for_block(response)`; raise `SourceBlocked` on unexpected HTML/CAPTCHA; raise `SourceFormatChanged` when the payload shape changes. Never retry blocks.
  - Return records exactly as published (original text in `raw_payload`); normalize only unambiguous fields. Never invent or estimate values. Area ranges, bands and free text stay in `raw_payload`.
  - `external_id` must be stable across runs (source id, or hash of the normalized row + occurrence index for identical rows).
- Do **not** put gate, rate limit, storage or logging in the connector — `app/services/collector.py` does that.
- Listings vs transactions: transacted prices are `TransactionRecord` → `property_transactions`. A listings source needs a listing record type and storage in the Collector (add it then, with tests).

## 3. Tests (synthetic fixtures only)

- Inspect the real format once, after approval (header, encoding, odd values), then write **invented** rows in that format under `backend/tests/` (see `tests/ppr_fixture.py`). Never commit real personal data; fixtures are never loaded into the operational DB.
- Parser test: field mapping, flags, original values kept, stable ids, format change rejected.
- Connector test with `httpx.MockTransport`: success, 401/403/429, HTML instead of payload.
- Collector tests already cover gate/rate limit/idempotency; add cases only for new record types.
- Run: `docker compose exec api pytest -q` and `ruff check .`.

## 4. Register, approve, collect

```bash
docker compose exec api python -m app.cli register-source <code>
docker compose exec api python -m app.cli collect --source <code> --region-id <id>   # must be SKIPPED (gate)
docker compose exec api python -m app.cli approve-permission <code> --note "approved by <owner> in chat on <date>" [--reviewer <admin email>]
docker compose exec api python -m app.cli collect --source <code> --region-id <id>
```

The region needs `source_location_ids["<code>"]` (how the source names it).

## 5. Verify and document

- Cross-check DB counts/sums against an independent count of the downloaded payload.
- Check `search_jobs`, `crawl_logs`, `search_coverage`, `agent_executions`, region status.
- Update `docs/DATA_SOURCES.md` (active sources table), `docs/ROADMAP.md`, and attribution needs for the dashboard.
