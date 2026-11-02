# API — Real Estate Intelligence

> Status: Fase 7 — todos os endpoints do dashboard implementados (✅). Preços são sempre **transacionados**; a base estatística padrão é mercado pleno, com IVA. A documentação interativa será gerada pelo FastAPI em `/docs` (OpenAPI); este arquivo lista o contrato pretendido e é atualizado a cada endpoint entregue.

Base: `/api/v1` · Autenticação: `Authorization: Bearer <JWT>` · Papéis: ADMIN, ANALYST, VIEWER.
Paginação: `?limit=&cursor=` (cursor opaco). Erros: `{"detail": "...", "code": "..."}`.

| Método | Rota | Papel | Descrição | Fase |
|---|---|---|---|---|
| POST | `/auth/login` | — | ✅ Emite access + refresh token. Body `{email, password}`. Limite `LOGIN_RATE_LIMIT` (5/min) | 2 |
| POST | `/auth/refresh` | — | ✅ Body `{refresh_token}` → novo par de tokens | 2 |
| GET | `/auth/me` | qualquer | ✅ `{id, email, role}` do usuário autenticado | 2 |
| GET | `/health` | — | ✅ `{status, db, redis}`; 503 se algum falhar | 2 |
| POST | `/sources` | ADMIN | Cadastra fonte (nasce PENDING_APPROVAL) | 3 |
| POST | `/sources/{id}/permissions` | ADMIN | Registra/aprova permissão com evidência | 3 |
| GET | `/properties?country=&region_id=&min_price=&max_price=&sold_from=&sold_to=&kind=new\|second_hand&full_market_only=&repeat_sales_only=&q=&cursor=` | VIEWER | ✅ Busca sobre a **última venda** de cada imóvel, ordenada por data, 50 por página, `next_cursor`. `country` (ISO alfa-2) restringe a um país/moeda. Detalhe (`/properties/{public_id}`) inclui `built_area_m2`/`land_area_m2` quando a fonte informa (IPTU, São Paulo) | 7–8 |
| GET | `/properties/{public_id}` | VIEWER | ✅ Imóvel + todas as vendas (texto original, flags de mercado/IVA, fonte) + revisões pendentes; 404 | 7 |
| GET | `/listings/{id}` | VIEWER | Anúncio com payload normalizado | 3 |
| GET | `/dedup/candidates?decision=PENDING&limit=&after_id=` | ANALYST | ✅ Fila de revisão: venda × imóvel candidato, score, vetos, motivo, total | 7 |
| POST | `/dedup/candidates/{id}/decision` | ADMIN | ✅ Body `{decision: SAME_PROPERTY\|DIFFERENT}`; SAME_PROPERTY move a venda (registro de imóvel vazio é removido; nenhuma venda apagada); 409 se já decidido | 7 |
| POST | `/cities` | ADMIN | Cadastra cidade semente (dispara RegionExplorer) | 5 |
| GET | `/regions?parent_id=&country=` | VIEWER | ✅ GeoJSON FeatureCollection (topo, ou filhas de `parent_id`; `country` filtra o topo); propriedades: `id, name, level, status, parent_id, last_searched_at, children, sales, sales_12m, median_12m, country, currency`; `median_basis` descreve a mediana (por país; objeto por país sem `country`). Geometria simplificada só para exibição | 5–8 |
| GET | `/regions/{id}` | VIEWER | ✅ Detalhe: região pai, contadores (`sales`, `properties`, filhos), mediana, `coverage[]` por fonte (status, concluída, próxima), `neighbors[]`; 404 se não existir | 5 |
| GET | `/coverage/summary` | VIEWER | ✅ `regions_by_status` (topo e todas), `totals` (imóveis, transações, anúncios, fontes ativas, última atualização, revisões de dedup pendentes), `attributions[]` obrigatórias | 5 |
| GET | `/jobs?status=&limit=` | ANALYST | ✅ Jobs mais recentes: região, fonte, status, gatilho, tentativa, agendamento, contadores, último erro | 6 |
| POST | `/jobs/{id}/retry` | ADMIN | ✅ Reenfileira job FAILED/SKIPPED/CANCELLED (409 se houver outro ativo para a mesma pesquisa); o Collector reaplica todas as verificações | 6 |
| GET | `/agents/executions?agent=&limit=` | ANALYST | ✅ Execuções dos agentes (orquestrador, collector, dedup) com saída e erro | 6 |
| GET | `/sources` | VIEWER | ✅ Fontes com status, limites, **requisições restantes hoje**, última permissão e atribuição | 6 |
| GET | `/collection/places?country=` | VIEWER | ✅ Cada lugar × fonte que o cobre (`source_location_ids`): situação da cobertura, última coleta, próxima automática, registros lidos, job ativo e `manual_blocked_until` (intervalo mínimo da fonte ainda não passou) | 8 |
| POST | `/collection/requests` | ADMIN | ✅ Body `{region_id, source}`: pesquisa manual de um lugar × fonte (gatilho `MANUAL`, prioridade 10, despachada no próximo ciclo do orquestrador). 404 lugar/fonte inexistente; 422 fonte não cobre o lugar; 409 se o gate recusa a fonte ou o intervalo mínimo não passou. Se já há job ativo, devolve-o (e o prioriza) | 8 |
| GET | `/analytics/kpis` | VIEWER | ✅ Indicadores da página inicial | 7 |
| GET | `/analytics/countries` | VIEWER | ✅ Países com áreas pesquisadas (`iso2, name, currency`) para o seletor do dashboard | 8 |
| GET | `/analytics/areas?country=IE` | VIEWER | ✅ Por área de topo do país: vendas, mediana/média 12m, mediana 12m anterior, variação %, mediana por m² 12m (`price_m2_basis`, só onde há área), novos 12m (`null` se a fonte não diz), imóveis, revendidos; `currency`, `basis`, `unavailable` (códigos `no_floor_area`, `no_room_counts`, `no_parking`, `no_new_flag`) | 7–8 |
| GET | `/analytics/timeseries?region_ids=1,2&months=60` | VIEWER | ✅ Mediana e contagem mensais (1 a 4 áreas), `provisional` nos meses recentes | 7 |
| GET | `/analytics/price-bands?country=IE&region_id=` | VIEWER | ✅ Vendas dos últimos 12 meses por faixa de preço (faixas na moeda do país) | 7–8 |
| GET | `/analytics/timeseries?...` | VIEWER | Regiões de países diferentes na mesma série → 400 (moedas diferentes) | 8 |
| GET | `/analytics/regions` | VIEWER | Preço médio, preço/m², área média etc. por região | 7 |
| GET | `/analytics/compare` | VIEWER | Comparação entre bairros/cidades | 7 |

## Frontend (backend-for-frontend)

O navegador nunca chama a API diretamente. Rotas do Next.js repassam a requisição com o token do cookie httpOnly: `GET /api/regions?parent_id=`, `GET /api/regions/{id}`. `GET /vendor/maplibre-worker` serve o web worker da MapLibre (arquivo do pacote instalado).
