# Papéis dos Agentes

Há dois tipos de "agente" neste projeto — não confundir:

1. **Agentes de runtime** — componentes da plataforma (tarefas Celery em `backend/app/agents` + `backend/app/tasks`).
2. **Subagentes de desenvolvimento** — assistentes do Claude Code em `.claude/agents/` que ajudam a construir o sistema.

## 1. Agentes de runtime

Regra geral: **código convencional para operações determinísticas; IA apenas para interpretar texto ambíguo.** Toda execução grava uma linha em `agent_executions`.

| # | Agente | Fila Celery | IA | Lê | Escreve |
|---|---|---|---|---|---|
| 01 | Master Orchestrator | `default` | Não | search_jobs, sources | search_jobs (despacho/estado) |
| 02 | Source Discovery | `default` | Opcional (resumo de ToS) | sources | sources, source_permissions (sempre PENDING) |
| 03 | Region Explorer | `geo` | Não | cities, regions | cities, regions, region_neighbors |
| 04 | Property Collector | `collect` | Não | search_jobs, source_permissions | property_listings (bruto), property_transactions, crawl_logs |
| 05 | Data Extractor | `process` / `ai` | Só texto livre | property_listings | property_features |
| 06 | Data Validator | `process` | Não | property_features | property_listings, data_quality |
| 07 | Deduplication | `process` | Opcional (explicação) | listings, properties | properties, property_listings.property_id, dedup_candidates |
| 08 | Market Analyst | `default` | Opcional (texto de relatório) | properties, listings, transactions | views materializadas, relatórios |
| 09 | Coverage Monitor | `default` | Não | regions, search_coverage, sources | search_coverage, search_jobs, regions.status |

### 01 — Master Orchestrator
- **Implementado** (`app/agents/orchestrator.py`, task `agents.orchestrate` a cada `ORCHESTRATOR_INTERVAL_SECONDS`): (1) jobs IN_PROGRESS há mais de 30 min voltam à fila (FAILED após 3 tentativas); (2) falhas transitórias retentadas com backoff 10·2^(n-1) min — bloqueios, recusas do gate e fontes não ACTIVE nunca; (3) Coverage Monitor planeja até 3 jobs por fonte, limitado ao orçamento restante do dia; (4) despacha jobs vencidos por prioridade para a fila `collect`.
- Redundância evitada pelo índice único parcial em `search_jobs` e por lock consultivo do ciclo.
- Expansão desligável: `ORCHESTRATOR_EXPANSION=false`.

### 02 — Source Discovery
- Cadastro assistido de fontes; checagem automática de disponibilidade e robots.txt.
- Pode usar LLM para **resumir** termos de uso, mas **nunca aprova**: toda permissão nasce `PENDING` e só um ADMIN muda para `APPROVED` com evidência.

### 03 — Region Explorer
- Importa limites (oficial > OSM/Overpass > `ST_HexagonGrid`), monta hierarquia e vizinhança (`ST_Touches`/`ST_DWithin`).
- Para expansão além da cidade, aplica a mesma lógica sobre `cities.geom`.
- Mapeia como cada fonte nomeia a região (`regions.source_location_ids`).

### 04 — Property Collector
- Executa o conector da fonte com paginação e cursor retomável (`search_jobs.next_cursor`).
- Aplica gate de permissão, rate limit, robots.txt (crawlers) e parada em bloqueio — **fora do conector**.
- Grava payload bruto + hash; atualiza `last_seen_at`; registra cada página em `crawl_logs`.

### 05 — Data Extractor
- Mapeamento declarativo campo-a-campo para fontes estruturadas (`method = SOURCE_FIELD/RULE`).
- LLM (quando habilitado) só para texto livre, com saída estruturada e **trecho de evidência obrigatório**; o validador confere que o trecho existe no texto, senão descarta.
- Nunca preenche campo ausente; estimativas só com `method = ESTIMATE` e `is_estimated = true`.

### 06 — Data Validator
- Normaliza unidades (ft² → m², semanas → mês), moeda, tipos.
- Regras de coerência: útil ≤ total, terreno vs construída por tipo, preço/m² fora de faixa por região → `data_quality`.
- Atribui `confidence` e `validation_status`.

### 07 — Deduplication
- **Transações (implementado, `dedup-txn-1`):** Eircode confiável → endereço normalizado idêntico → fuzzy (token_sort ≥ 95) só se as diferenças forem de digitação; palavra extra de um lado com score ≥ 85 → revisão. Vetos: números (rotulados) diferentes, distrito diferente, sem número, Eircodes diferentes, mesma data de venda. Eircode compartilhado por endereços com números diferentes é ignorado (placeholder). Precisão medida 99,50% contra Eircode.
- **Anúncios (quando houver fonte):** exata → blocking espacial → score → vetos (unidade, área ±10%, quartos, tipo) → decisão.
- Vínculo reversível (`property_id`); nada é apagado; ligações fuzzy ficam registradas como `AUTO_LINKED` em `dedup_candidates`.

### 08 — Market Analyst
- SQL/views materializadas: preço médio, preço/m² (por base de área), área média, médias de quartos/banheiros, distribuição de vagas, tipologia, comparativos bairro/cidade, séries históricas.
- **Sempre separa preço anunciado de preço transacionado.**

### 09 — Coverage Monitor
- **Implementado** (`app/agents/coverage_monitor.py`, CLI `expand`): primeiro coberturas vencidas (`next_due_at <= now()`), depois áreas de topo vizinhas de áreas COMPLETED nunca pesquisadas pela fonte, mais próximas primeiro, limitado por `--max` (o Collector ainda aplica rate limit e orçamento diário).
- Status das regiões recalculado com herança (cobertura do pai vale para os filhos) — `app/services/coverage.py`.
- Agendamento automático (Celery Beat) entra na Fase 6.

## 2. Subagentes de desenvolvimento (Claude Code)

Definidos em `.claude/agents/`. O agente principal coordena, revisa e integra; subagentes não editam os mesmos arquivos simultaneamente.

| Subagente | Arquivos sob sua responsabilidade | Foco |
|---|---|---|
| `architect` | `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` (revisão de todo o resto, somente leitura) | Modularidade, decisões, escalabilidade |
| `database-engineer` | `backend/app/models`, `backend/alembic`, `infrastructure/database`, `docs/DATABASE_SCHEMA.md` | Schema, migrations, índices, PostGIS |
| `data-engineer` | `backend/app/crawlers`, `agents`, `validators`, `geographic`, `docs/DATA_SOURCES.md` | Conectores, extração, normalização, dedup |
| `qa-engineer` | `backend/tests`, testes do frontend, `.github/workflows` | Testes, segurança, revisão |
