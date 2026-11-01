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
| GET | `/properties?region_id=&min_price=&max_price=&sold_from=&sold_to=&kind=new\|second_hand&full_market_only=&repeat_sales_only=&q=&cursor=` | VIEWER | ✅ Busca sobre a **última venda** de cada imóvel, ordenada por data, 50 por página, `next_cursor`. Área/quartos/banheiros/garagem: indisponíveis na fonte atual | 7 |
| GET | `/properties/{public_id}` | VIEWER | ✅ Imóvel + todas as vendas (texto original, flags de mercado/IVA, fonte) + revisões pendentes; 404 | 7 |
| GET | `/listings/{id}` | VIEWER | Anúncio com payload normalizado | 3 |
| GET | `/dedup/candidates?decision=PENDING&limit=&after_id=` | ANALYST | ✅ Fila de revisão: venda × imóvel candidato, score, vetos, motivo, total | 7 |
| POST | `/dedup/candidates/{id}/decision` | ADMIN | ✅ Body `{decision: SAME_PROPERTY\|DIFFERENT}`; SAME_PROPERTY move a venda (registro de imóvel vazio é removido; nenhuma venda apagada); 409 se já decidido | 7 |
| POST | `/cities` | ADMIN | Cadastra cidade semente (dispara RegionExplorer) | 5 |
| GET | `/regions?parent_id=` | VIEWER | ✅ GeoJSON FeatureCollection (topo, ou filhas de `parent_id`); propriedades: `id, name, level, status, parent_id, last_searched_at, children, sales, sales_12m, median_12m`; `median_basis` descreve a mediana (transacionado, mercado pleno, com IVA, 12 meses). Geometria simplificada só para exibição | 5 |
| GET | `/regions/{id}` | VIEWER | ✅ Detalhe: região pai, contadores (`sales`, `properties`, filhos), mediana, `coverage[]` por fonte (status, concluída, próxima), `neighbors[]`; 404 se não existir | 5 |
| GET | `/coverage/summary` | VIEWER | ✅ `regions_by_status` (topo e todas), `totals` (imóveis, transações, anúncios, fontes ativas, última atualização, revisões de dedup pendentes), `attributions[]` obrigatórias | 5 |
| GET | `/jobs?status=&limit=` | ANALYST | ✅ Jobs mais recentes: região, fonte, status, gatilho, tentativa, agendamento, contadores, último erro | 6 |
| POST | `/jobs/{id}/retry` | ADMIN | ✅ Reenfileira job FAILED/SKIPPED/CANCELLED (409 se houver outro ativo para a mesma pesquisa); o Collector reaplica todas as verificações | 6 |
| GET | `/agents/executions?agent=&limit=` | ANALYST | ✅ Execuções dos agentes (orquestrador, collector, dedup) com saída e erro | 6 |
| GET | `/sources` | VIEWER | ✅ Fontes com status, limites, **requisições restantes hoje**, última permissão e atribuição | 6 |
| POST | `/jobs` | ADMIN | Pesquisa manual de uma região × fonte | 6 |
| GET | `/analytics/kpis` | VIEWER | ✅ Indicadores da página inicial | 7 |
| GET | `/analytics/areas` | VIEWER | ✅ Por área de topo: vendas, mediana/média 12m, mediana 12m anterior, variação %, novos 12m, imóveis, revendidos; `unavailable` lista o que a fonte não permite | 7 |
| GET | `/analytics/timeseries?region_ids=1,2&months=60` | VIEWER | ✅ Mediana e contagem mensais (1 a 4 áreas), `provisional` nos meses recentes | 7 |
| GET | `/analytics/price-bands?region_id=` | VIEWER | ✅ Vendas dos últimos 12 meses por faixa de preço | 7 |
| GET | `/analytics/regions` | VIEWER | Preço médio, preço/m², área média etc. por região | 7 |
| GET | `/analytics/compare` | VIEWER | Comparação entre bairros/cidades | 7 |

## Frontend (backend-for-frontend)

O navegador nunca chama a API diretamente. Rotas do Next.js repassam a requisição com o token do cookie httpOnly: `GET /api/regions?parent_id=`, `GET /api/regions/{id}`. `GET /vendor/maplibre-worker` serve o web worker da MapLibre (arquivo do pacote instalado).
