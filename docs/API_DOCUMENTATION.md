# API — Real Estate Intelligence

> Status: **planejada** (nada implementado). A documentação interativa será gerada pelo FastAPI em `/docs` (OpenAPI); este arquivo lista o contrato pretendido e é atualizado a cada endpoint entregue.

Base: `/api/v1` · Autenticação: `Authorization: Bearer <JWT>` · Papéis: ADMIN, ANALYST, VIEWER.
Paginação: `?limit=&cursor=` (cursor opaco). Erros: `{"detail": "...", "code": "..."}`.

| Método | Rota | Papel | Descrição | Fase |
|---|---|---|---|---|
| POST | `/auth/login` | — | Emite access + refresh token | 2 |
| POST | `/auth/refresh` | — | Renova access token | 2 |
| GET | `/health` | — | Liveness/readiness (db, redis) | 2 |
| GET | `/sources` | VIEWER | Lista fontes e status | 3 |
| POST | `/sources` | ADMIN | Cadastra fonte (nasce PENDING_APPROVAL) | 3 |
| POST | `/sources/{id}/permissions` | ADMIN | Registra/aprova permissão com evidência | 3 |
| GET | `/properties` | VIEWER | Busca com filtros (país, cidade, região, tipo, categoria, preço, área, quartos, banheiros, garagem, fonte, data) | 3–7 |
| GET | `/properties/{public_id}` | VIEWER | Detalhe + anúncios vinculados + proveniência por campo | 4 |
| GET | `/properties/{public_id}/history` | VIEWER | Histórico de preços/status | 4 |
| GET | `/listings/{id}` | VIEWER | Anúncio com payload normalizado | 3 |
| GET | `/dedup/candidates` | ANALYST | Fila de revisão | 4 |
| POST | `/dedup/candidates/{id}/decision` | ADMIN | SAME_PROPERTY / DIFFERENT | 4 |
| POST | `/cities` | ADMIN | Cadastra cidade semente (dispara RegionExplorer) | 5 |
| GET | `/regions` | VIEWER | Regiões com status (GeoJSON) | 5 |
| GET | `/regions/{id}` | VIEWER | Detalhe, cobertura por fonte, contadores | 5 |
| GET | `/coverage/summary` | VIEWER | Pesquisadas, pendentes, em processamento | 5 |
| GET | `/jobs` | ANALYST | Jobs com filtros por status/fonte/região | 6 |
| POST | `/jobs` | ADMIN | Pesquisa manual de uma região × fonte | 6 |
| GET | `/analytics/kpis` | VIEWER | Indicadores da página inicial | 7 |
| GET | `/analytics/regions` | VIEWER | Preço médio, preço/m², área média etc. por região | 7 |
| GET | `/analytics/compare` | VIEWER | Comparação entre bairros/cidades | 7 |
