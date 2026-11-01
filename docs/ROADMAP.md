# Roadmap

Regra: **não avançar de fase sem cumprir o critério de saída da anterior.** Estimativas são grosseiras.

## Decisões

| Data | Decisão | Origem |
|---|---|---|
| 2026-10-31 | Plano da Fase 1 aprovado: monólito modular, agentes como tarefas Celery, LangGraph e Browser Use adiados | Responsável |
| 2026-10-31 | Padrões adotados até decisão contrária: cidade piloto **Dublin**; primeira fonte **Property Price Register (IE)**; **sem LLM** na partida | Recomendação aprovada com o plano |
| 2026-10-31 | Runtime de containers: **Docker Desktop** (requer WSL2) | Responsável |
| 2026-11-01 | Repositório GitHub **privado** `marcusvcostaa-jpg/real-estate-intelligence` | Responsável |
| 2026-11-01 | Fonte `ie_ppr` (Property Price Register) **aprovada** nas condições de `docs/DATA_SOURCES.md` | Responsável |

### Pendentes (bloqueiam a fase indicada)

| Decisão | Bloqueia |
|---|---|
| Solicitar acesso a APIs de anúncios (Daft.ie / idealista) — ação do responsável | Primeira fonte de **anúncios** (Fase 4 usa transações enquanto isso) |
| Provedor de LLM (nenhum / Ollama local / API paga) | Primeira fonte com texto livre |

## Fases

### Fase 1 — Arquitetura ✅
Estrutura de pastas, documentação, CLAUDE.md, subagentes, skills, git.
**Saída:** aprovação dos documentos.

### Fase 2 — Fundação (~1 semana) ✅

Validação local (2026-11-01, Docker Desktop 4.97 / Engine 29.9.2 / Compose v5.6.1 sobre WSL 3.0.3):
- ✅ Migration inicial `54aec88d8bff` revisada: 17 tabelas, 14 enums, extensões `postgis`/`citext`, view materializada `region_neighbors`. `upgrade → downgrade → upgrade → downgrade` sem erro; `alembic check` sem divergência entre modelos e banco.
- ✅ `pytest`: 10 testes (segurança, login/refresh/me, credenciais inválidas, usuário inativo, rate limit 429, papéis 403/200, health) passando contra PostGIS real.
- ✅ `docker compose up`: db e redis healthy; API `/health` = ok (db, redis); `/docs` 200; worker Celery responde `pong`; beat iniciado; backup diário gravado.
- ✅ Navegador: senha errada rejeitada; login → página protegida; tokens invisíveis ao JavaScript (cookies HttpOnly); logout → `/login`; `proxy.ts` renova o access token a partir do refresh.
- ✅ Backup restaurado em banco descartável: mesmas tabelas, revisão Alembic, view e enums.
- ✅ CI no GitHub Actions (repositório privado `marcusvcostaa-jpg/real-estate-intelligence`): jobs backend (lint, migrations ida/volta, pytest com PostGIS) e frontend (lint, build com type-check).

Escopo:

Escopo:
- `docker-compose.yml` (db, redis, api, worker, beat, frontend, backup).
- Backend: FastAPI, config, logging, sessão SQLAlchemy, Alembic com **migration inicial do schema completo**.
- Autenticação JWT + papéis; rate limiting; `/health`.
- Frontend: Next.js + TS + Tailwind, layout base, login.
- CI: lint + testes (Postgres real) no GitHub Actions.
- Backup/restore testado.
**Saída:** `docker compose up` sobe tudo; migration aplica e reverte; CI verde.

### Fase 3 — Primeira fonte (~1 semana) ✅

Entregue (2026-11-01):
- ✅ Termos do Property Price Register verificados; aprovação do responsável registrada em `source_permissions` (evidências em `docs/DATA_SOURCES.md`).
- ✅ Collector (`app/services/collector.py`): gate de permissão (job `SKIPPED` sem contato com a fonte), rate limit/orçamento diário no Redis, parada e `BLOCKED` em 401/403/429/HTML, `crawl_logs`, cobertura, status derivado da região, `agent_executions`, cursor retomável, job único por pesquisa.
- ✅ Conector `ie_ppr` + CLI `add-city`, `register-source`, `approve-permission`, `collect`.
- ✅ 30 testes (fixtures sintéticas no formato real); CI.
- ✅ Coleta real: 255.242 vendas de Dublin (2010-01-01 → 2026-10-23), contagens e soma de preços idênticas à contagem independente do arquivo.
- ✅ Skill `.claude/skills/add-source-connector`.
- Observações: são preços **transacionados** (não anúncios) — anúncios dependem de acesso a APIs (pendência abaixo). Celery task de coleta fica para a Fase 6 (orquestrador); por ora a coleta é disparada pela CLI. A atribuição da PSRA deve aparecer no dashboard (Fase 7).

Escopo original:
- Verificar termos da fonte escolhida; registrar `source_permissions`.
- Conector + Collector com gate, rate limit, paginação/cursor, `crawl_logs`.
- Extração determinística; armazenamento.
- Skill de projeto `add-source-connector` (`.claude/skills/`), escrita a partir do primeiro conector real.
**Saída:** dados reais no banco com proveniência completa; testes de contrato com fixtures.

### Fase 4 — Tratamento dos dados (1–2 semanas) ✅ (para transações)

Entregue (2026-11-01), sobre as 255.242 vendas reais de Dublin:
- ✅ Normalização determinística de endereço irlandês e Eircode (`app/validators/address.py`): distrito postal, abreviações, acentos, números rotulados (`apt:4`, `block:2`).
- ✅ Validação (`app/validators/transactions.py` → `data_quality`, re-executável): 397 `PRICE_VERY_LOW`, 208 `PRICE_VERY_HIGH`, 486 `EIRCODE_SHARED` (179 Eircodes de preenchimento/erro, ex. "A123456"). Nada é alterado nos valores publicados.
- ✅ Deduplicação (`app/agents/deduplication.py` + `app/services/dedup.py`): Eircode confiável → endereço normalizado idêntico → fuzzy só para diferenças de digitação. Vetos: números diferentes, distrito diferente (por cluster, sem "ponte" transitiva), sem número (só Eircode liga), Eircodes diferentes, **duas vendas na mesma data** (unidades vendidas em lote). Palavra extra de um lado → revisão; palavras trocadas ("Walk"/"Way") → imóveis diferentes.
- ✅ **Precisão medida contra o Eircode como gabarito** (Eircode escondido do algoritmo, 84.619 vendas): **precisão 99,50%**, recall 87,0% (`app.cli dedup-eval`). Iterações: 95,5% (fuzzy simples) → 99,45% (vetos) → 99,50% (Eircodes falsos ignorados).
- ✅ Resultado: 223.248 imóveis; 28.902 com 2–5 vendas (histórico de preços transacionados por imóvel); 4.391 ligações fuzzy auditáveis (`AUTO_LINKED`); 2.798 pares pendentes de revisão humana. Re-execução idêntica (determinística, sem duplicar nada).
- ✅ 48 testes (casos sintéticos modelados nos padrões reais: apartamentos vizinhos, bloco/apto, tipo de rua, distritos, Eircode falso, lote na mesma data).
- ⏳ Histórico de **anúncios** (`property_history`: mudança de preço, NOT_SEEN/REMOVED) e dedup de anúncios por coordenadas/área/quartos: **aguardam uma fonte de anúncios** — não implementados sem dados reais para validar.
- ⏳ Interface para revisar a fila `dedup_candidates` (Fase 7; decisões ADMIN via API).

Escopo original:
- Normalização e validação (`data_quality`, confiança).
- Dedup: exata → blocking (ST_DWithin 150 m / CEP) → score (rapidfuzz, distância, área, quartos…) → vetos → decisão; fila de revisão.
- Histórico de preços e ciclo NOT_SEEN/REMOVED.
**Saída:** suíte com casos reais de duplicados e não-duplicados (mesmo prédio); precisão de auto-merge medida.

### Fase 5 — Geografia (~2 semanas)
- Importar Dublin (limites oficiais/OSM), hierarquia, vizinhança.
- Cobertura por polígono; status derivado; expansão BFS com orçamento.
- Mapa MapLibre com status das regiões e clique para detalhes.
- Skill de projeto `seed-city`, escrita a partir da importação de Dublin.
**Saída:** expansão automática observável no mapa a partir de uma semente.

### Fase 6 — Agentes (~1 semana)
- Consolidar orquestrador (prioridade, jobs travados, retries), `agent_executions`, Flower.
**Saída:** falhas visíveis e recuperáveis sem intervenção manual no banco.

### Fase 7 — Dashboard (~2 semanas)
- KPIs, mapa de calor/concentração, preços médios por região, análises, filtros, comparativos, histórico.
**Saída:** todas as métricas da especificação, sobre dados reais.

### Fase 8 — Escalabilidade (contínuo)
- Novas fontes/países (skill `add-source-connector`), particionamento de tabelas grandes, Nominatim self-hosted, otimização.
