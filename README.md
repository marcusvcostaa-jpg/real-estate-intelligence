# Real Estate Intelligence

Plataforma de inteligência imobiliária internacional: coleta de fontes **autorizadas**, padronização, deduplicação de imóveis entre portais, histórico de preços, controle de cobertura geográfica com PostGIS e dashboard com mapas interativos.

> **Status:** Fase 5 concluída — limites oficiais da Irlanda, expansão automática de Dublin para Meath, Kildare e Wicklow (361 mil vendas, 320 mil imóveis) e mapa de cobertura em `/map`. Ver [docs/ROADMAP.md](docs/ROADMAP.md).

## Documentação

| Documento | Conteúdo |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Princípios, decisões, componentes, fluxo, contrato de conector |
| [DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | Tabelas, enums, índices, regras de derivação |
| [AGENT_ROLES.md](docs/AGENT_ROLES.md) | Agentes de runtime e subagentes de desenvolvimento |
| [DATA_SOURCES.md](docs/DATA_SOURCES.md) | Política de fontes, checklist, candidatas |
| [API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) | Endpoints planejados |
| [ROADMAP.md](docs/ROADMAP.md) | Fases, critérios de saída, decisões |

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · Celery · Redis · PostgreSQL 16 + PostGIS 3 · Next.js · TypeScript · Tailwind · MapLibre GL JS · Docker Compose · GitHub Actions.

## Estrutura

```
backend/        API, agentes, conectores, geografia, analytics (app/) e testes
frontend/       Dashboard Next.js
infrastructure/ Dockerfiles, scripts de banco e operação
docs/           Documentação do projeto
.claude/        Subagentes e skills do Claude Code
```

## Princípios

- Só fontes com permissão documentada; sem contornar proteções.
- Imóvel físico separado do anúncio; proveniência de cada campo preservada.
- Nada de dados inventados ou demonstrativos apresentados como reais.
- Ferramentas gratuitas/open source; qualquer custo exige aprovação.

## Como rodar

Pré-requisitos: Docker Desktop (com WSL2 no Windows).

```bash
cp .env.example .env          # depois troque POSTGRES_PASSWORD (também nas URLs) e JWT_SECRET
docker compose up -d --build  # db, redis, api, worker, beat, frontend, backup
docker compose exec api python -m app.cli create-user --email voce@exemplo.com --role ADMIN
```

- Frontend: http://localhost:3000 · API: http://localhost:8000/api/v1 · OpenAPI: http://localhost:8000/docs
- Gerar um `JWT_SECRET`: `python -c "import secrets; print(secrets.token_urlsafe(64))"`

| Tarefa | Comando |
|---|---|
| Testes backend | `docker compose exec api pytest` |
| Lint backend | `docker compose exec api ruff check .` |
| Nova migration | `docker compose exec api alembic revision --autogenerate -m "descricao"` |
| Aplicar migrations | `docker compose exec api alembic upgrade head` |
| Lint/build frontend | `cd frontend && npm run lint && npm run build` |
| Importar limites oficiais | `docker compose exec api python -m app.cli import-boundaries --source-location ie_ppr --subdivide Dublin` |
| Expandir cobertura | `docker compose exec api python -m app.cli expand --source ie_ppr --max 3 --run` |
| Cadastrar cidade/região | `docker compose exec api python -m app.cli add-city --iso2 IE --country-name Ireland --currency EUR --city Dublin --admin1 "County Dublin" --region-name "County Dublin" --lat 53.3498 --lon -6.2603 --source-location ie_ppr=Dublin` |
| Registrar / aprovar fonte | `... app.cli register-source ie_ppr` · `... app.cli approve-permission ie_ppr --note "..." [--reviewer admin@...]` |
| Coletar | `docker compose exec api python -m app.cli collect --source ie_ppr --region-id 1` |
| Validar / deduplicar | `... app.cli validate --source ie_ppr` · `... app.cli dedup --source ie_ppr` |
| Medir precisão do dedup | `docker compose exec api python -m app.cli dedup-eval --source ie_ppr` |
| Restaurar backup | `docker compose run --rm --entrypoint sh backup /scripts/restore.sh /backups/<arquivo>.dump [banco]` |

Backups diários ficam em `./backups/` (fora do git).

> **Hot reload no Windows:** o `next dev` dentro do container não detecta mudanças pelo bind mount (Turbopack). Para desenvolver o frontend, rode `npm run dev` no host (com `API_INTERNAL_URL=http://localhost:8000/api/v1`) ou `docker compose restart frontend` após editar.

> **Git Bash no Windows:** prefixe comandos que passam caminhos para dentro do container com `MSYS_NO_PATHCONV=1` (ex.: o restore), senão `/scripts/...` vira um caminho do Windows. PowerShell não precisa disso.
