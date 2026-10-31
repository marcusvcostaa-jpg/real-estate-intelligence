# Skills de terceiros

Copiadas sem modificação em 2026-10-31. Para atualizar: clonar o repositório, revisar o diff, substituir a pasta e atualizar o commit aqui.

| Skill | Origem (commit) | Licença | Por quê |
|---|---|---|---|
| `react-best-practices` | vercel-labs/agent-skills @ `1a2c79d` | MIT | Frontend Next.js/React |
| `composition-patterns` | vercel-labs/agent-skills @ `1a2c79d` | MIT | Componentes React |
| `supabase-postgres-best-practices` | supabase/agent-skills @ `c9be0e9` | MIT | Boas práticas Postgres (genéricas, sem Supabase Cloud) |
| `frontend-design` | anthropics/skills @ `ca45fc4` | Apache-2.0 | Qualidade visual do dashboard |
| `webapp-testing` | anthropics/skills @ `ca45fc4` | Apache-2.0 | Testes de UI com Playwright |

## Plugin

- **superpowers** (obra/superpowers, MIT) — habilitado via `.claude/settings.json` a partir do marketplace oficial (`superpowers@claude-plugins-official`). Não copiado: as skills se referenciam pelo namespace `superpowers:` e incluem hook de SessionStart.

## Avaliadas e não instaladas

| Skill | Motivo |
|---|---|
| vercel: `deploy-to-vercel`, `vercel-cli-with-tokens`, `vercel-optimize` | Hosting Vercel não faz parte da stack (custo/serviço externo) |
| vercel: `react-native-skills`, `react-view-transitions`, `writing-guidelines` | Fora do escopo |
| vercel: `web-design-guidelines` | Busca instruções remotas a cada uso (conteúdo muda sem revisão) |
| supabase: `supabase` | Específica da plataforma Supabase Cloud |
| anthropics: `skill-creator`, `mcp-builder` etc. | Já disponíveis no ambiente via plugin `anthropic-skills` |
| anthropics: `docx`, `pdf`, `pptx`, `xlsx` | Licença proprietária ("All rights reserved"); desnecessárias |
