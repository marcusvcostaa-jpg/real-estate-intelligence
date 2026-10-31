# Real Estate Intelligence

Plataforma de inteligência imobiliária internacional: coleta de fontes **autorizadas**, padronização, deduplicação de imóveis entre portais, histórico de preços, controle de cobertura geográfica com PostGIS e dashboard com mapas interativos.

> **Status:** Fase 2 (fundação) em andamento — ver [docs/ROADMAP.md](docs/ROADMAP.md). Ainda não há coleta de dados.

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
| Restaurar backup | `docker compose run --rm --entrypoint sh backup /scripts/restore.sh /backups/<arquivo>.dump [banco]` |

Backups diários ficam em `./backups/` (fora do git).
