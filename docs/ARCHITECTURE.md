# Arquitetura — Real Estate Intelligence

> Status: **Fase 1 aprovada (2026-10-31)**. Nenhum código de aplicação existe ainda.
> Este documento descreve a arquitetura alvo; cada fase atualiza a seção "Estado de implementação".

## 1. Princípios

1. **Legalidade antes de cobertura.** Nenhuma fonte é consultada sem permissão registrada (`source_permissions`). Ver [DATA_SOURCES.md](DATA_SOURCES.md).
2. **Imóvel físico ≠ anúncio.** `properties` 1→N `property_listings`. Anúncios nunca são apagados por deduplicação.
3. **Proveniência em tudo.** Valor original + valor normalizado + método + confiança, por campo.
4. **Determinístico primeiro, IA só onde há ambiguidade.** IA nunca decide permissões, nunca inventa campos (evidência obrigatória).
5. **Postgres é a fonte da verdade** — inclusive do estado de filas e cobertura. Redis é descartável.
6. **Gratuito e open source por padrão.** Qualquer custo exige aprovação explícita do responsável.

## 2. Decisões arquiteturais (ADR resumido)

| # | Decisão | Motivo | Revisitar quando |
|---|---|---|---|
| 1 | Monólito modular (um pacote Python, processos separados p/ API e workers) | Uma equipe pequena; deploy e debug simples; módulos isolados por pasta | Um módulo precisar escalar de forma independente |
| 2 | "Agentes" = tarefas Celery com responsabilidade única | 80% do trabalho é determinístico; testável; barato | — |
| 3 | LangGraph **adiado** | Nenhum fluxo exige loop de raciocínio multi-etapa | Um agente precisar planejar/iterar com LLM |
| 4 | Browser Use **não instalado** | Caro, não determinístico, tende a usos proibidos por ToS | Fonte autorizada sem API/feed exigir navegação guiada |
| 5 | Playwright só para fonte autorizada que exija JS | Mínimo necessário | — |
| 6 | Grade hexagonal via `ST_HexagonGrid` (PostGIS), sem H3 | Recurso nativo, zero dependência | Precisar de índices H3 interoperáveis |
| 7 | Normalização de endereço com regras + rapidfuzz, sem libpostal | libpostal ≈ 2 GB | Taxa de erro de dedup por endereço ficar alta |
| 8 | Monitoramento: logs estruturados + `agent_executions` + Flower | Suficiente para 1 operador | Operação contínua em produção → Prometheus/Grafana |
| 9 | LLM: **nenhum** na partida; interface plugável (Ollama local / API paga com aprovação) | Fontes estruturadas não precisam de LLM | Primeira fonte com texto livre relevante |
| 10 | Tiles: OpenFreeMap ou PMTiles self-hosted | Gratuito, sem chave | — |
| 11 | SQLAlchemy **síncrono** (psycopg 3) na API e nos workers | Celery é síncrono; FastAPI roda deps síncronas em threadpool; um só estilo de código | Gargalo medido de I/O na API |
| 12 | Frontend como *backend-for-frontend*: o navegador só fala com o Next.js; tokens JWT ficam em cookies httpOnly; `proxy.ts` renova o access token | Tokens nunca expostos ao JavaScript; CORS irrelevante | — |
| 13 | Dependências Python com **uv** (lockfile `backend/uv.lock`) | Rápido, reprodutível, já instalado | — |

## 3. Componentes

```
                    ┌──────────────────────────────┐
                    │   Next.js Dashboard          │
                    │   (MapLibre, filtros, KPIs)  │
                    └──────────────┬───────────────┘
                                   │ REST + JWT
                    ┌──────────────▼───────────────┐
                    │        FastAPI (api)         │
                    └──────┬───────────────┬───────┘
                           │ SQL           │ enfileira
   ┌───────────────────────▼──┐      ┌─────▼──────┐     ┌──────────────┐
   │  PostgreSQL + PostGIS    │◄─────┤   Redis    │◄────┤ Celery Beat  │
   │  (dados, filas, cobert.) │      │ broker+RL  │     │ (agendador)  │
   └───────────▲──────────────┘      └─────┬──────┘     └──────────────┘
               │                           │
   ┌───────────┴───────────────────────────▼───────────────────────────┐
   │                      Celery Workers (agentes)                     │
   │  Orchestrator · RegionExplorer · Collector · Extractor ·          │
   │  Validator · Dedup · MarketAnalyst · CoverageMonitor · SourceDisc │
   └───────┬─────────────────┬──────────────────┬──────────────────────┘
           │                 │                  │
   ┌───────▼───────┐ ┌───────▼────────┐ ┌───────▼─────────────┐
   │ Conectores    │ │ Geo externos   │ │ LLM (opcional)      │
   │ API/feed/open │ │ OSM/Overpass,  │ │ Ollama local ou     │
   │ data/crawler* │ │ limites oficiais│ │ API paga (aprovar)  │
   └───────────────┘ └────────────────┘ └─────────────────────┘
   * crawler só com permissão APPROVED em source_permissions
```

| Serviço (docker-compose) | Imagem/base | Função |
|---|---|---|
| `db` | `postgis/postgis:16-3.4` | Banco |
| `redis` | `redis:7-alpine` | Broker Celery, rate limit |
| `api` | Python 3.12 | FastAPI |
| `worker` | mesma imagem da API | Celery, filas `collect`, `process`, `geo`, `ai` |
| `beat` | mesma imagem da API | Agendamentos |
| `frontend` | Node 22 LTS | Next.js |
| `backup` | `postgis/postgis` | `pg_dump` agendado para volume local |

## 4. Fluxo principal

1. Usuário cadastra cidade semente.
2. **RegionExplorer** importa polígonos (oficial > OSM > grade), monta hierarquia e vizinhança.
3. **CoverageMonitor** cria `search_jobs` para pares (região × fonte aprovada × filtros) nunca pesquisados ou vencidos.
4. **Orchestrator** prioriza e despacha respeitando rate limit e orçamento diário por fonte.
5. **Collector** executa o conector com paginação e cursor retomável; grava payload bruto e `crawl_logs`.
6. **Extractor** mapeia campos (determinístico; LLM só para texto livre, com evidência).
7. **Validator** normaliza unidades/moeda, aplica regras de coerência, atribui confiança, grava `data_quality`.
8. **Dedup** vincula ao imóvel existente, cria novo, ou envia para `dedup_candidates`.
9. Mudanças de preço/status → `property_history`.
10. Fim do job → status da região **recalculado a partir da cobertura** (nunca setado manualmente).
11. Região concluída → vizinhos entram na fila conforme política de expansão.
12. **MarketAnalyst** atualiza views materializadas consumidas pelo dashboard.

## 5. Contrato de conector

Cada fonte é um módulo em `backend/app/crawlers/<codigo_fonte>/`. Adicionar uma fonte não altera as outras.

```python
class SourceConnector(Protocol):
    code: str                       # = sources.code
    def search(self, region: RegionRef, filters: SearchFilters,
               cursor: Cursor | None) -> SearchPage: ...
    # SearchPage = itens brutos (RawListing/RawTransaction) + next_cursor + total_esperado?
```

Regras aplicadas **fora** do conector (no Collector), para que nenhum conector possa ignorá-las:
- gate de permissão (`source_permissions` APPROVED e não expirada);
- rate limit por fonte (token bucket no Redis) e orçamento diário;
- robots.txt para integrações do tipo `CRAWLER`;
- User-Agent identificado com contato;
- parada imediata em CAPTCHA/403/bloqueio → fonte `BLOCKED`, sem retry.

Cada conector tem testes de contrato com fixtures gravadas (respostas reais anonimizadas).

## 6. Mapeamento de módulos → pastas

| Pasta | Conteúdo |
|---|---|
| `backend/app/api` | Rotas FastAPI (v1) |
| `backend/app/core` | Config (pydantic-settings), segurança, logging |
| `backend/app/database` | Engine/sessão, base declarativa |
| `backend/app/models` | Modelos SQLAlchemy |
| `backend/app/schemas` | Schemas Pydantic (entrada/saída da API e payloads internos) |
| `backend/app/services` | Regras de negócio reutilizáveis (cobertura, consolidação de imóvel) |
| `backend/app/agents` | Lógica de cada agente (funções puras + orquestração) |
| `backend/app/crawlers` | Conectores por fonte |
| `backend/app/geographic` | Importação de limites, vizinhança, geocodificação |
| `backend/app/analytics` | Agregações e relatórios |
| `backend/app/tasks` | Definições Celery (finas; chamam `agents`/`services`) |
| `backend/app/validators` | Normalização e regras de qualidade |
| `backend/alembic` | Migrations (criado na Fase 2) |
| `infrastructure/docker` | Dockerfiles |
| `infrastructure/database` | Init SQL (extensões), scripts de backup/restore |
| `infrastructure/scripts` | Utilitários operacionais (seed de cidade, etc.) |

## 7. Transversal

| Tema | Abordagem |
|---|---|
| Autenticação | JWT (access curto + refresh), senhas com argon2; papéis ADMIN / ANALYST / VIEWER |
| Controle de acesso | Dependências FastAPI por papel; aprovação de fontes e merges só ADMIN |
| Credenciais | `.env` fora do git; chaves de fontes só em variáveis de ambiente; nunca logadas |
| Rate limiting da API | `slowapi` por IP/usuário |
| Logs | JSON estruturado (structlog), com `job_id`/`task_id` |
| Backups | `pg_dump` diário em volume local, retenção configurável; restore testado na Fase 2 |
| Testes | pytest + testcontainers/compose para Postgres real; Vitest/Playwright no frontend; CI no GitHub Actions |
| GDPR | Não armazenar nome/telefone/e-mail de corretores ou proprietários; retenção de payload bruto; DPIA em `docs/` antes de operar na UE |
| Erros | Retries com backoff só para erros transitórios (timeouts, 5xx); 4xx de bloqueio nunca é retentado |

## 8. Estado de implementação

| Fase | Status |
|---|---|
| 1 — Arquitetura | ✅ documentação e estrutura |
| 2 — Fundação | ✅ validada localmente e no CI |
| 3–8 | Pendente — ver [ROADMAP.md](ROADMAP.md) |
