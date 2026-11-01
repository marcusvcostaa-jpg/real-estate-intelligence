# CLAUDE.md — Real Estate Intelligence

Plataforma de inteligência imobiliária: coleta de fontes **autorizadas**, normalização, deduplicação, histórico de preços, cobertura geográfica com PostGIS e dashboard com mapas.

Idioma: converse e documente em **português (pt-BR)**; código, identificadores e mensagens de commit em inglês.

## Leia antes de trabalhar
- `docs/ARCHITECTURE.md` — decisões e componentes
- `docs/DATABASE_SCHEMA.md` — schema (a fonte da verdade, após a Fase 2, é o Alembic)
- `docs/AGENT_ROLES.md` — agentes de runtime e subagentes de desenvolvimento
- `docs/DATA_SOURCES.md` — política de fontes (obrigatória)
- `docs/ROADMAP.md` — fase atual, decisões tomadas e pendentes

## Regras inegociáveis
1. Nenhuma fonte é consultada sem `source_permissions` APPROVED com evidência. Nada de contornar CAPTCHA, paywall, login, bloqueios; nada de proxies ou serviços de unblocking (o plugin Bright Data disponível no ambiente **não** deve ser usado neste projeto).
2. Não contratar/usar serviço pago (API, LLM, hosting, geocoding) sem aprovação explícita do responsável.
3. Não inventar dados. Não apresentar dados demonstrativos como reais. Fixtures de teste ficam em `backend/tests` e nunca são carregadas no banco de operação.
4. Imóvel físico (`properties`) ≠ anúncio (`property_listings`). Dedup só vincula; nunca apaga anúncio.
5. Preservar valor original + normalizado + método + confiança por campo. Estimativas marcadas (`is_estimated`).
6. Não confundir área construída, útil, total e de terreno; `price_per_m2_basis` sempre preenchido.
7. Anúncio sumido ≠ vendido. Preço anunciado ≠ preço transacionado.
8. Toda mudança de schema via migration Alembic. Toda lógica não trivial com teste.
9. Não avançar de fase sem o critério de saída da anterior (ver ROADMAP). Não entregar funcionalidade simulada como funcional.
10. Informar quando algo depende de API/serviço externo. Manter `docs/` atualizado no mesmo commit da mudança.
11. Não armazenar dados pessoais desnecessários (contatos de corretores/proprietários, fotos).

## Stack
Backend Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · Celery + Redis · PostgreSQL 16 + PostGIS 3.
Coleta: httpx (APIs), Scrapy (sites autorizados), Playwright (só se fonte autorizada exigir JS).
Frontend: Next.js (App Router) · React · TypeScript · Tailwind · MapLibre GL JS.
Infra: Docker Compose · GitHub Actions.

## Convenções
- Monólito modular: tarefas Celery em `backend/app/tasks` são finas e chamam `agents/`/`services/`.
- Conector novo = módulo em `backend/app/crawlers/<source_code>/` + testes de contrato com fixtures; gate/rate limit ficam no Collector, nunca no conector.
- Dinheiro `numeric` + moeda ISO 4217; geometria SRID 4326; `timestamptz` UTC.
- Simplicidade: sem abstração especulativa. Simplificação deliberada com teto conhecido leva comentário `# ponytail: <teto e caminho de upgrade>`.

## Comandos
Ver tabela em `README.md` (§ Como rodar). Essenciais:
- `docker compose up -d --build` · `docker compose exec api pytest` · `docker compose exec api ruff check .`
- Migrations: `docker compose exec api alembic revision --autogenerate -m "..."` — **revise o arquivo gerado** (enums, PostGIS, views) antes de commitar.
- Backend sem Docker (só testes unitários): `cd backend && uv run pytest tests/test_security.py`.
- Frontend: Next.js 16 — leia `frontend/AGENTS.md` e `frontend/node_modules/next/dist/docs/` antes de escrever código (APIs mudaram: `proxy.ts` em vez de middleware, Cache Components ativo → leitura de cookies só dentro de `<Suspense>`).

## Fluxo de trabalho
- Plugin **superpowers** (habilitado em `.claude/settings.json`): usar brainstorming/writing-plans para features, TDD, systematic-debugging, verification-before-completion antes de declarar algo pronto.
- Skills do projeto em `.claude/skills/` (origem e licenças em `.claude/skills/VENDORED.md`): `supabase-postgres-best-practices` antes de qualquer schema/SQL; `react-best-practices`, `composition-patterns`, `frontend-design` no frontend; `webapp-testing` para testes de UI; `add-source-connector` para qualquer fonte nova.
- Subagentes em `.claude/agents/` (architect, database-engineer, data-engineer, qa-engineer) têm donos de arquivos definidos — não rodar dois em paralelo sobre os mesmos arquivos. O agente principal revisa antes de integrar.
- Commits pequenos, por etapa validada.
