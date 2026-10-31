# Real Estate Intelligence

Plataforma de inteligência imobiliária internacional: coleta de fontes **autorizadas**, padronização, deduplicação de imóveis entre portais, histórico de preços, controle de cobertura geográfica com PostGIS e dashboard com mapas interativos.

> **Status:** Fase 1 (arquitetura) concluída. Ainda não há código de aplicação — ver [docs/ROADMAP.md](docs/ROADMAP.md).

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

Disponível a partir da Fase 2 (`docker compose up`).
