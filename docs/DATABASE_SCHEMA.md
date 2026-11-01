# Schema do Banco — Real Estate Intelligence

> PostgreSQL 16 + PostGIS 3. Este documento é a **especificação** para a migration inicial (Fase 2).
> Depois que a migration existir, **a fonte da verdade é o Alembic**; este arquivo é atualizado junto com cada migration.
>
> Estado: migrations `54aec88d8bff` (inicial) e `1e8e9dae7156` (candidatos de dedup para transações, issue aberta única) aplicadas (modelos em `backend/app/models/`). A view `region_neighbors` usa uma regra provisória (polígonos que se tocam, ou centróides a até 1,5 km quando falta polígono), a revisar com dados reais na Fase 5.

## Convenções

- Chaves: `bigint generated always as identity` (`id`). Imóveis também têm `public_id uuid` exposto na API.
- Tempo: `timestamptz` sempre, UTC.
- Dinheiro: `numeric(14,2)` + `currency char(3)` (ISO 4217). **Nunca float.**
- Áreas: `numeric(10,2)` em m². Valor e unidade originais vão em `property_features`.
- Geometria: SRID 4326. Polígonos `geometry(MultiPolygon,4326)`; pontos de imóveis `geography(Point,4326)`. Índices GIST.
- Enums Postgres para estados estáveis; `text` + CHECK para listas que crescem (tipos de imóvel).
- Todo FK indexado. `created_at`/`updated_at` em tabelas mutáveis.

## Enums

```sql
region_status     : NOT_STARTED, QUEUED, IN_PROGRESS, PARTIALLY_COMPLETED, COMPLETED, FAILED, REQUIRES_REVIEW
job_status        : QUEUED, IN_PROGRESS, COMPLETED, PARTIALLY_COMPLETED, FAILED, CANCELLED, SKIPPED
region_level      : DISTRICT, NEIGHBORHOOD, LOCALITY, POSTAL_AREA, GRID_CELL
source_status     : PENDING_APPROVAL, ACTIVE, PAUSED, BLOCKED, RETIRED
integration_type  : OFFICIAL_API, LICENSED_FEED, OPEN_DATA, PARTNER, CRAWLER
permission_type   : OFFICIAL_API_TERMS, OPEN_DATA_LICENSE, WRITTEN_AGREEMENT, LICENSE_PURCHASED, TOS_ALLOWS
permission_status : PENDING, APPROVED, DENIED, EXPIRED, REVOKED
offer_type        : SALE, RENT
listing_status    : ACTIVE, NOT_SEEN, REMOVED
validation_status : PENDING, VALID, WARNING, INVALID, REQUIRES_REVIEW
extraction_method : SOURCE_FIELD, RULE, LLM, MANUAL, ESTIMATE
history_event     : FIRST_SEEN, PRICE_CHANGE, STATUS_CHANGE, NOT_SEEN, REMOVED, REAPPEARED
dedup_decision    : PENDING, AUTO_LINKED, SAME_PROPERTY, DIFFERENT
user_role         : ADMIN, ANALYST, VIEWER
```

## Diagrama de relacionamentos

```
countries 1─N cities 1─N regions (parent_id → regions)
                           │
sources 1─N source_permissions
   │
   ├─1─N search_coverage N─1 regions
   ├─1─N search_jobs     N─1 regions ──1─N crawl_logs
   │
   └─1─N property_listings N─1 properties N─1 regions
              │                    │
              ├─1─N property_features
              ├─1─N property_history
              └─1─N dedup_candidates N─1 properties

property_transactions N─1 properties (opcional), N─1 sources
data_quality → (entity_type, entity_id)      agent_executions → search_jobs (opcional)
users (autenticação)
```

## Tabelas

### Geografia

```sql
countries (
  id smallint PK, iso2 char(2) UNIQUE NOT NULL, iso3 char(3) UNIQUE,
  name text NOT NULL, default_currency char(3) NOT NULL,
  created_at timestamptz
)

cities (
  id PK, country_id FK NOT NULL,
  admin1_code text, admin1_name text,          -- estado / província / condado
  name text NOT NULL,
  external_ids jsonb DEFAULT '{}',             -- {"osm": 123, "cso": "..."}
  geom geometry(MultiPolygon,4326),            -- NULL se não houver limite
  centroid geometry(Point,4326) NOT NULL,
  boundary_source text,                        -- OFFICIAL:<dataset> | OSM | MANUAL
  status region_status DEFAULT 'NOT_STARTED',
  created_at, updated_at,
  UNIQUE (country_id, admin1_code, name)
)

regions (
  id PK, city_id FK NOT NULL, parent_id FK regions NULL,
  level region_level NOT NULL, name text NOT NULL,
  external_ids jsonb DEFAULT '{}',
  source_location_ids jsonb DEFAULT '{}',      -- como cada fonte identifica a região: {"ie_ppr": "Dublin 8"}
  geom geometry(MultiPolygon,4326),
  centroid geometry(Point,4326) NOT NULL,
  boundary_source text,
  status region_status DEFAULT 'NOT_STARTED',  -- DERIVADO de search_coverage, nunca setado à mão
  last_searched_at timestamptz,
  listings_found int DEFAULT 0, listings_new int DEFAULT 0,
  duplicates int DEFAULT 0, errors int DEFAULT 0,
  created_at, updated_at
)
-- GIST(geom), GIST(centroid), (city_id, level), (parent_id)

MATERIALIZED VIEW region_neighbors (region_id, neighbor_id, relation)   -- 'TOUCHES' via ST_Touches, 'NEAR' via ST_DWithin p/ regiões sem polígono
```

### Fontes

```sql
sources (
  id PK, code text UNIQUE NOT NULL,            -- = nome do módulo do conector, ex. 'ie_ppr'
  name text NOT NULL, country_id FK NULL,      -- NULL = multi-país
  base_url text NOT NULL, integration_type integration_type NOT NULL,
  has_api bool NOT NULL DEFAULT false,
  rate_limit_per_minute int NOT NULL, daily_request_budget int,
  min_refresh_interval interval NOT NULL,      -- frequência permitida pela fonte
  available_fields text[] DEFAULT '{}',
  status source_status NOT NULL DEFAULT 'PENDING_APPROVAL',
  last_success_at timestamptz, last_error_at timestamptz, notes text,
  created_at, updated_at
)

source_permissions (
  id PK, source_id FK NOT NULL,
  permission_type permission_type NOT NULL, status permission_status NOT NULL DEFAULT 'PENDING',
  license_name text,                           -- ex. 'CC-BY-4.0', 'OGL-3.0', contrato X
  evidence_url text, evidence_document text,   -- link/arquivo que comprova a permissão
  scope text NOT NULL,                         -- o que é permitido (campos, uso comercial, redistribuição)
  restrictions text, attribution_required bool DEFAULT false, attribution_text text,
  robots_txt_checked_at timestamptz,
  granted_at timestamptz, expires_at timestamptz,
  reviewed_by FK users, created_at
)
-- Gate: existe linha APPROVED AND (expires_at IS NULL OR expires_at > now())
```

### Imóveis e anúncios

```sql
properties (                                   -- imóvel FÍSICO consolidado
  id PK, public_id uuid UNIQUE NOT NULL DEFAULT gen_random_uuid(),
  country_id FK NOT NULL, city_id FK, region_id FK NULL,
  property_type text NOT NULL,                 -- APARTMENT, HOUSE, LAND, COMMERCIAL, DWELLING (casa ou apto, fonte não distingue), ...
  category text NOT NULL,                      -- RESIDENTIAL, COMMERCIAL, LAND, OTHER
  status text NOT NULL DEFAULT 'UNKNOWN',      -- LISTED, NOT_LISTED, UNKNOWN (nunca 'SOLD' por inferência)
  address_display text, address_normalized text, unit_identifier text,   -- nº apto/unidade (veto de dedup)
  postal_code text,
  location geography(Point,4326),
  location_precision text,                     -- ROOFTOP, STREET, POSTAL, REGION, UNKNOWN
  built_area_m2 numeric(10,2), land_area_m2 numeric(10,2),
  useful_area_m2 numeric(10,2), total_area_m2 numeric(10,2),
  bedrooms smallint, bathrooms numeric(3,1), suites smallint,
  garage_spaces smallint, parking_spaces smallint,
  living_rooms smallint, kitchens smallint,
  has_garden bool, has_balcony bool,
  floors smallint, floor_level smallint, year_built smallint, energy_rating text,
  confidence numeric(4,3), validation_status validation_status DEFAULT 'PENDING',
  created_at, updated_at
)
-- GIST(location), (city_id, property_type), (postal_code), (region_id)
-- Valores consolidados; a origem de cada valor está em property_features.

property_listings (                            -- ANÚNCIO em uma fonte
  id PK, property_id FK NULL,                  -- NULL até o dedup decidir
  source_id FK NOT NULL, external_id text NOT NULL, url text,
  offer_type offer_type NOT NULL, listing_status listing_status NOT NULL DEFAULT 'ACTIVE',
  price_text_original text,                    -- exatamente como veio
  price_original numeric(14,2), currency char(3),
  rent_period text,                            -- MONTH, WEEK, ... (só RENT)
  price_monthly numeric(14,2),                 -- aluguel normalizado p/ mês
  price_per_m2 numeric(12,2), price_per_m2_basis text,   -- BUILT | USEFUL | TOTAL — nunca misturar
  published_at timestamptz,
  first_seen_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL, removed_at timestamptz,
  consecutive_misses smallint DEFAULT 0,       -- NOT_SEEN/REMOVED após N varreduras completas
  raw_payload jsonb NOT NULL, raw_payload_sha256 char(64) NOT NULL,
  confidence numeric(4,3), validation_status validation_status DEFAULT 'PENDING',
  last_job_id FK search_jobs,
  created_at, updated_at,
  UNIQUE (source_id, external_id)
)

property_features (                            -- proveniência por campo
  id PK, listing_id FK NOT NULL, property_id FK NULL,
  field_name text NOT NULL,                    -- 'built_area', 'bedrooms', ...
  value_original text, unit_original text,
  value_normalized numeric, value_text text, unit_normalized text,
  method extraction_method NOT NULL,
  evidence text,                               -- trecho literal da fonte (obrigatório se method = LLM)
  confidence numeric(4,3) NOT NULL,
  is_estimated bool NOT NULL DEFAULT false,
  extractor_version text NOT NULL, extracted_at timestamptz NOT NULL,
  CHECK (method <> 'LLM' OR evidence IS NOT NULL),
  CHECK (method <> 'ESTIMATE' OR is_estimated)
)
-- (listing_id, field_name), (property_id, field_name)

property_history (
  id PK, listing_id FK NOT NULL, property_id FK NULL, source_id FK NOT NULL,
  event history_event NOT NULL,
  old_price numeric(14,2), new_price numeric(14,2), currency char(3),
  old_status listing_status, new_status listing_status,
  url text, observed_at timestamptz NOT NULL, job_id FK search_jobs
)
-- (property_id, observed_at), (listing_id, observed_at). Particionar por mês quando crescer.

property_transactions (                        -- preço EFETIVAMENTE transacionado (registro oficial)
  id PK, property_id FK NULL, source_id FK NOT NULL,
  external_id text NOT NULL,                   -- id da fonte ou sha256 da linha normalizada
  transaction_date date NOT NULL, price numeric(14,2) NOT NULL, currency char(3) NOT NULL,
  is_full_market_price bool, vat_exclusive bool,
  address_original text, postal_code text, description_original text,
  location geography(Point,4326), region_id FK NULL,
  raw_payload jsonb NOT NULL, created_at,
  UNIQUE (source_id, external_id)
)

dedup_candidates (                             -- assunto: UM anúncio OU UMA transação
  id PK, listing_id FK NULL, transaction_id FK NULL, candidate_property_id FK NOT NULL,
  score numeric(4,3) NOT NULL, signals jsonb NOT NULL, vetoes text[] DEFAULT '{}',
  decision dedup_decision NOT NULL DEFAULT 'PENDING',
  decided_by FK users NULL, decided_at timestamptz, created_at,
  UNIQUE (listing_id, candidate_property_id),
  UNIQUE (transaction_id, candidate_property_id),
  CHECK (num_nonnulls(listing_id, transaction_id) = 1)
)
```

### Pesquisa e cobertura

```sql
search_coverage (                              -- 1 linha por (região, fonte, filtros)
  id PK, region_id FK NOT NULL, source_id FK NOT NULL,
  filters jsonb NOT NULL DEFAULT '{}', filters_hash char(64) NOT NULL,
  status region_status NOT NULL DEFAULT 'NOT_STARTED',
  last_started_at, last_completed_at timestamptz,
  pages_processed int DEFAULT 0, pages_expected int,
  listings_found int DEFAULT 0,
  refresh_interval interval NOT NULL,          -- configurável por região × fonte (>= sources.min_refresh_interval)
  next_due_at timestamptz, last_job_id FK search_jobs,
  UNIQUE (region_id, source_id, filters_hash)
)
-- (next_due_at) para o CoverageMonitor

search_jobs (
  id PK, region_id FK NOT NULL, source_id FK NOT NULL,
  filters jsonb NOT NULL DEFAULT '{}', filters_hash char(64) NOT NULL,
  status job_status NOT NULL DEFAULT 'QUEUED',
  priority smallint DEFAULT 100, attempt smallint DEFAULT 0,
  triggered_by text NOT NULL,                  -- SCHEDULE, EXPANSION, MANUAL, RETRY
  scheduled_for timestamptz, started_at, finished_at timestamptz,
  pages_processed int DEFAULT 0, pages_expected int, next_cursor jsonb,   -- retomada
  listings_found int DEFAULT 0, new_listings int DEFAULT 0, new_properties int DEFAULT 0,
  duplicates int DEFAULT 0, errors_count int DEFAULT 0, last_error text,
  next_run_at timestamptz, created_at
)
-- Anti-duplicação garantida pelo banco:
CREATE UNIQUE INDEX search_jobs_one_active
  ON search_jobs (region_id, source_id, filters_hash)
  WHERE status IN ('QUEUED','IN_PROGRESS');

crawl_logs (
  id PK, job_id FK NOT NULL, source_id FK NOT NULL, page int,
  request_url text,                            -- sem chaves/tokens
  http_status smallint, items_count int, duration_ms int, error text,
  created_at timestamptz NOT NULL
)
-- (job_id). Particionar por mês quando crescer.
```

### Qualidade, auditoria e usuários

```sql
data_quality (
  id PK, entity_type text NOT NULL,            -- PROPERTY, LISTING, TRANSACTION
  entity_id bigint NOT NULL, rule_code text NOT NULL,
  severity text NOT NULL,                      -- INFO, WARNING, ERROR
  message text NOT NULL, details jsonb,
  detected_at timestamptz NOT NULL, resolved_at timestamptz, resolution text
)
-- (entity_type, entity_id); UNIQUE (entity_type, entity_id, rule_code) WHERE resolved_at IS NULL

agent_executions (
  id PK, agent text NOT NULL, task_id text, job_id FK NULL,
  status text NOT NULL, input jsonb, output jsonb, error text,
  started_at timestamptz NOT NULL, finished_at timestamptz, duration_ms int,
  llm_model text, tokens_in int, tokens_out int, cost_estimate numeric(10,4)
)

users (
  id PK, email citext UNIQUE NOT NULL, password_hash text NOT NULL,
  role user_role NOT NULL DEFAULT 'VIEWER', is_active bool DEFAULT true,
  created_at, last_login_at
)
```

## Notas de uso

- Contadores de `search_jobs` (`listings_found`, `new_listings`, `duplicates`) contam **registros recebidos da fonte** — anúncios ou transações, conforme a fonte. Os contadores de `regions` (`listings_*`) são só para anúncios e não são alterados por fontes de transações.
- `regions.boundary_source = 'MANUAL'`: centróide de referência inserido à mão (`add-city`), sem polígono — limites reais na Fase 5.

## Regras de derivação

**Status da região** (serviço Python, testado; executado ao fim de cada job), considerando só fontes aplicáveis (aprovadas e que cobrem o país):

| Condição sobre `search_coverage` da região | Status |
|---|---|
| Nenhuma linha | NOT_STARTED |
| Alguma REQUIRES_REVIEW | REQUIRES_REVIEW |
| Alguma IN_PROGRESS | IN_PROGRESS |
| Alguma QUEUED (nenhuma em progresso) | QUEUED |
| Todas COMPLETED, sem páginas pendentes, sem erro aberto | COMPLETED |
| Todas FAILED | FAILED |
| Qualquer outra mistura | PARTIALLY_COMPLETED |

**Anúncio desaparecido:** não visto em uma varredura **completa** → `consecutive_misses += 1`; ≥ 1 → `NOT_SEEN`; ≥ N (configurável) → `REMOVED`. Nunca marca o imóvel como vendido; só uma `property_transactions` vinculada indica venda.

**Imóvel consolidado:** para cada campo, valor de maior confiança; empate → mais recente. Estimativas só preenchem campo vazio e permanecem marcadas.
