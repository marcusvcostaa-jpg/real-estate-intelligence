# Roadmap

Regra: **não avançar de fase sem cumprir o critério de saída da anterior.** Estimativas são grosseiras.

## Decisões

| Data | Decisão | Origem |
|---|---|---|
| 2026-10-31 | Plano da Fase 1 aprovado: monólito modular, agentes como tarefas Celery, LangGraph e Browser Use adiados | Responsável |
| 2026-10-31 | Padrões adotados até decisão contrária: cidade piloto **Dublin**; primeira fonte **Property Price Register (IE)**; **sem LLM** na partida | Recomendação aprovada com o plano |

### Pendentes (bloqueiam a fase indicada)

| Decisão | Bloqueia |
|---|---|
| Runtime de containers: Docker Desktop (verificar licença) vs Podman/Rancher Desktop | Fase 2 |
| Criar repositório GitHub privado `real-estate-intelligence`? | Fase 2 (CI) |
| Solicitar acesso a APIs de anúncios (Daft.ie / idealista) — ação do responsável | Fase 3 (anúncios) |
| Provedor de LLM (nenhum / Ollama local / API paga) | Primeira fonte com texto livre |

## Fases

### Fase 1 — Arquitetura ✅
Estrutura de pastas, documentação, CLAUDE.md, subagentes, skills, git.
**Saída:** aprovação dos documentos.

### Fase 2 — Fundação (~1 semana)
- `docker-compose.yml` (db, redis, api, worker, beat, frontend, backup).
- Backend: FastAPI, config, logging, sessão SQLAlchemy, Alembic com **migration inicial do schema completo**.
- Autenticação JWT + papéis; rate limiting; `/health`.
- Frontend: Next.js + TS + Tailwind, layout base, login.
- CI: lint + testes (Postgres real) no GitHub Actions.
- Backup/restore testado.
**Saída:** `docker compose up` sobe tudo; migration aplica e reverte; CI verde.

### Fase 3 — Primeira fonte (~1 semana)
- Verificar termos da fonte escolhida; registrar `source_permissions`.
- Conector + Collector com gate, rate limit, paginação/cursor, `crawl_logs`.
- Extração determinística; armazenamento.
- Skill de projeto `add-source-connector` (`.claude/skills/`), escrita a partir do primeiro conector real.
**Saída:** dados reais no banco com proveniência completa; testes de contrato com fixtures.

### Fase 4 — Tratamento dos dados (1–2 semanas)
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
