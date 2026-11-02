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
| 2026-11-01 | Limites Tailte Éireann (CC BY 4.0) aprovados; escopo do `ie_ppr` ampliado para expansão aos condados vizinhos | Responsável |

### Pendentes (bloqueiam a fase indicada)

| Decisão | Bloqueia |
|---|---|
| Solicitar acesso a APIs de anúncios (Daft.ie / idealista) — ação do responsável | Primeira fonte de **anúncios** (Fase 4 usa transações enquanto isso) |
| Provedor de LLM (nenhum / Ollama local / API paga) | Primeira fonte com texto livre |
| Geocodificação de vendas (Nominatim local / base Eircode paga / casamento por localidade) | Estatísticas abaixo do nível de condado |

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

### Fase 5 — Geografia (~2 semanas) ✅

Entregue (2026-11-01):
- ✅ Limites oficiais **Tailte Éireann** (National Statutory Boundaries 2019, generalizados 20 m, CC BY 4.0, aprovados): 26 condados (áreas de pesquisa de topo) + Dublin subdividida em 4 áreas administrativas e 322 divisões eleitorais (`app.cli import-boundaries`).
- ✅ Vizinhança: `region_neighbors` tolerante à generalização (mesmo nível, até ~100 m; `ST_Touches` perdia Kildare e Meath). Dublin com Kildare, Meath, Wicklow; 58 pares de condados; média 6,3 vizinhas por divisão eleitoral.
- ✅ Status derivado **com herança**: cobertura de um condado vale para suas sub-regiões (o PPR pesquisa por condado).
- ✅ **Coverage Monitor** (`app/agents/coverage_monitor.py`, `app.cli expand`): refreshes vencidos primeiro, depois vizinhos não pesquisados de áreas concluídas, mais próximos primeiro, dentro do orçamento.
- ✅ **Expansão automática real** a partir de Dublin (escopo ampliado aprovado): Meath (33.894 vendas), Kildare (44.496), Wicklow (27.542). Próxima fronteira: Louth, Carlow, Laois, Westmeath, Wexford, Monaghan, Cavan, Offaly. Cache condicional (If-Modified-Since, resposta 304) evita baixar 19 MB por condado.
- ✅ Deduplicação refeita nos 4 condados com veto por condado: 361.174 vendas viraram 320.037 imóveis; precisão medida 99,40% (114 mil vendas com Eircode).
- ✅ API: `GET /regions` (GeoJSON), `GET /regions/{id}`, `GET /coverage/summary` (VIEWER).
- ✅ Mapa MapLibre (`/map`): cor por status ou mediana (transacionado, mercado pleno, com IVA, 12 meses), clique mostra detalhes/cobertura/vizinhos, sub-regiões, atribuições PSRA + Tailte + OpenFreeMap/OSM. Testado no navegador.
- ✅ 54 testes.
- Correções no caminho: orçamento consumido por tentativas recusadas (corrigido; contador do dia ajustado de 5 para as 3 requisições reais); view de vizinhança de 3 min para ~50 s.
- ⏳ Vendas por divisão eleitoral exigem **geocodificação** (o PPR não traz coordenadas) — decisão pendente (Nominatim local / base Eircode paga / casamento por localidade).
- ⏳ Skill `seed-city`: adiada — a importação ficou genérica por CLI (`import-boundaries`); escrever a skill quando houver um segundo país.

Escopo original:
- Importar Dublin (limites oficiais/OSM), hierarquia, vizinhança.
- Cobertura por polígono; status derivado; expansão BFS com orçamento.
- Mapa MapLibre com status das regiões e clique para detalhes.
- Skill de projeto `seed-city`, escrita a partir da importação de Dublin.
**Saída:** expansão automática observável no mapa a partir de uma semente.

### Fase 6 — Agentes (~1 semana) ✅

Entregue (2026-11-01):
- ✅ **Master Orchestrator** (`app/agents/orchestrator.py`), ciclo a cada 5 min pelo Celery Beat: recupera jobs travados em IN_PROGRESS há mais de 30 min (volta à fila, ou FAILED após 3 tentativas); retenta falhas transitórias com backoff exponencial (10, 20, 40 min); **nunca** retenta bloqueios (`blocked`), recusas do gate nem fontes não ACTIVE; pede ao Coverage Monitor novos jobs dentro do orçamento restante de cada fonte; despacha os jobs vencidos por prioridade.
- ✅ Tasks Celery finas (`app/tasks/agents.py`) em filas separadas: `default` (orquestrador), `collect` (Collector), `process` (validação + deduplicação após coleta com dados novos). Locks consultivos do Postgres evitam dois ciclos do orquestrador ou dois processamentos da mesma fonte ao mesmo tempo (validado ao vivo: a segunda tarefa foi reagendada em 60 s).
- ✅ **Orçamento diário contado no Postgres** (`crawl_logs`), não no Redis: um reinício do Redis (aconteceu) zerava o contador. Redis fica só com a janela por minuto.
- ✅ Recuperação sem mexer no banco: `POST /jobs/{id}/retry` (ADMIN), CLI `set-source-status` (revisão humana de fonte bloqueada), CLI `orchestrate`.
- ✅ Visibilidade: `GET /jobs`, `GET /agents/executions` (ANALYST), `GET /sources` (permissão, orçamento restante hoje), todas as execuções em `agent_executions`, **Flower** em http://localhost:5555 (só localhost, senha em `.env`).
- ✅ 62 testes (travados, backoff, bloqueio nunca retentado, fonte bloqueada, despacho, orçamento, retry manual, orçamento sobrevivendo ao Redis).
- Em operação: com o orçamento de hoje esgotado, a expansão automática continua após 00:00 UTC (fronteira atual: Louth, Carlow, Laois...). Para só atualizar o que já existe: `ORCHESTRATOR_EXPANSION=false`.

Escopo original:
- Consolidar orquestrador (prioridade, jobs travados, retries), `agent_executions`, Flower.
**Saída:** falhas visíveis e recuperáveis sem intervenção manual no banco.

### Fase 7 — Dashboard (~2 semanas) ✅

Entregue (2026-11-01), sobre dados reais (4 condados, 361 mil vendas, 320 mil imóveis):
- ✅ **Início**: indicadores (imóveis, vendas, anúncios, áreas e regiões pesquisadas/pendentes/em processamento, imóveis novos no sistema, fontes, última atualização, revisões pendentes, saúde) com atribuições obrigatórias.
- ✅ **Análises**: comparação entre áreas (barras + tabela: vendas, mediana e média de 12 meses, variação anual, % novos, revendidos), histórico de preços (mediana mensal, 10 anos, até 4 áreas, meses recentes marcados como provisórios), distribuição por faixa de preço; painel explícito de análises **indisponíveis** (preço/m², área, quartos, banheiros, garagem — a fonte não informa; nada estimado).
- ✅ **Imóveis**: busca com filtros (área, preço, datas, novo/usado, valor de mercado pleno, revendidos, endereço) sobre a última venda; paginação por cursor; detalhe com histórico de vendas (eixo temporal real).
- ✅ **Revisão**: fila de possíveis duplicados com motivo e vetos; ADMIN decide "mesmo imóvel" (move a venda; nenhuma venda apagada) ou "diferentes"; decisões respeitadas pelas deduplicações seguintes.
- ✅ Gráficos SVG próprios seguindo o guia de visualização: paleta validada em ordem fixa (cor segue a área), um eixo, linhas de 2 px, tooltip, legenda + rótulos diretos, tabela acessível, modo escuro.
- ✅ Desempenho: view materializada `property_sales_summary` (refresh ~2,4 s após cada dedup); busca de imóveis < 10 ms, áreas ~360 ms, série de 10 anos ~130 ms.
- ✅ 66 testes; validado no navegador.
- Mapa (Fase 5) integrado à navegação.
- ⏳ Indicadores de anúncios (preço anunciado, área, quartos, garagem) dependem de uma fonte autorizada de anúncios.
- KPIs, mapa de calor/concentração, preços médios por região, análises, filtros, comparativos, histórico.
**Saída:** todas as métricas da especificação, sobre dados reais.

### Fase 8 — Escalabilidade (contínuo)
- Novas fontes/países (skill `add-source-connector`), particionamento de tabelas grandes, Nominatim self-hosted, otimização.

Andamento (2026-11-01) — **Brasil, começando por São Paulo** (escolha do responsável):
- ✅ Fontes aprovadas pelo responsável: ITBI da Prefeitura de São Paulo (`br_sp_itbi`) e malhas do IBGE (município + 96 distritos).
- ✅ Conector `br_sp_itbi`: XLSX anual descoberto na página da Fazenda, GET condicional com cache, 5 anos (cursor por ano), linhas malformadas descartadas sem gravar; testes com planilha sintética.
- ✅ Separação por fonte/país sem alterar a Irlanda: dedup por identificador da fonte (SQL) quando existe, validação de código postal por país (CEP × Eircode), base estatística por país, áreas do IPTU (`built_area_m2`, `land_area_m2`) e categoria por transação (migration `279ef3428b22`; PPR marcado como residencial).
- ✅ Dashboard por país (Análises, Mapa, Imóveis): moeda própria, preço/m² para São Paulo (base: área construída IPTU), indicadores indisponíveis por país.
- ✅ Primeira coleta validada (2026 e 2025): 386.397 vendas → 374.020 imóveis, contagem e soma conferidas contra as planilhas. ⏳ 2024–2022 pelo orquestrador (4 arquivos/dia); até lá a variação anual de São Paulo usa um ano anterior incompleto.
- Pendências: localizar vendas nos distritos (CEP → coordenadas exige fonte aprovada); outras capitais (Recife ODbL, Porto Alegre); compactação do `raw_payload`.
