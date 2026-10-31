# Fontes de Dados

## 1. Política (obrigatória)

1. **Hierarquia de preferência:** API oficial → feed licenciado/parceria → dados abertos oficiais → crawling com permissão escrita ou ToS que permita explicitamente.
2. **Gate no código:** o Collector recusa qualquer job cuja fonte não tenha `source_permissions.status = APPROVED`, não expirada, com evidência registrada.
3. Proibido: contornar CAPTCHA, paywall, login, bloqueios ou rate limits; usar proxies/rotação de IP; serviços de "unblocking" (ex.: Bright Data); presumir permissão porque o conteúdo é público.
4. Bloqueio detectado (CAPTCHA, 403, 429 persistente) → fonte `BLOCKED`, sem retry, escalar ao responsável.
5. User-Agent identificado com contato (`SCRAPER_USER_AGENT` no `.env`).
6. Não armazenar dados pessoais de corretores/proprietários (nome, telefone, e-mail). Não armazenar fotos.
7. Respeitar atribuição exigida pela licença (exibida no dashboard).
8. Na UE, lembrar do **direito sui generis sobre bases de dados**: extrair parte substancial de uma base protegida é ilícito mesmo que os dados sejam públicos.

## 2. Checklist para cadastrar uma fonte

- [ ] Ler termos de uso / licença atuais e salvar link + data de leitura.
- [ ] Classificar `integration_type` e `permission_type`.
- [ ] Registrar escopo (campos, uso comercial, redistribuição), restrições e atribuição.
- [ ] Verificar robots.txt (se crawler).
- [ ] Definir `rate_limit_per_minute`, `daily_request_budget`, `min_refresh_interval` **abaixo** do permitido.
- [ ] ADMIN aprova em `source_permissions`.
- [ ] Criar conector em `backend/app/crawlers/<code>/` com testes de contrato e fixtures.
- [ ] Atualizar a tabela abaixo.

## 3. Fontes candidatas

> ⚠️ **Nenhuma destas fontes foi verificada ainda.** Status reflete conhecimento prévio; a Fase 3 começa pela verificação dos termos atuais.

### Anúncios (listings)

| Fonte | País | Tipo | Observações | Status |
|---|---|---|---|---|
| Daft.ie API | IE | OFFICIAL_API | Acesso historicamente via parceria/chave; responsável precisa solicitar | NÃO VERIFICADO |
| idealista API | ES/PT/IT | OFFICIAL_API | Exige solicitação e aprovação; cota gratuita baixa | NÃO VERIFICADO |
| RentCast API | US | OFFICIAL_API | Free tier limitado, planos pagos | NÃO VERIFICADO |
| Feeds XML de imobiliárias parceiras | BR (e outros) | LICENSED_FEED | CRMs de imobiliárias já exportam XML (formato VivaReal/ZAP, Kyero etc.); a imobiliária cede o próprio feed | Depende de parceria |
| Portais sem API (Zillow, Rightmove, ZAP, MyHome etc.) | vários | — | ToS geralmente proíbem coleta automatizada → **não usar** sem acordo escrito | BLOQUEADO por política |

### Transações (preço efetivamente pago)

| Fonte | País | Licença | Observações | Status |
|---|---|---|---|---|
| Property Price Register | IE | Dados abertos (PSI) | CSV oficial com vendas residenciais; candidata nº 1 para Dublin | NÃO VERIFICADO |
| HM Land Registry — Price Paid Data | UK (Ing./Gales) | OGL v3 | CSV mensal | NÃO VERIFICADO |
| DVF (Demandes de valeurs foncières) | FR | Licence Ouverte | — | NÃO VERIFICADO |
| ITBI — Prefeitura de São Paulo | BR | Dados abertos municipais | Guias de ITBI | NÃO VERIFICADO |

### Geografia

| Fonte | Uso | Licença | Observação |
|---|---|---|---|
| OpenStreetMap (Overpass API) | Limites administrativos, bairros | ODbL | Share-alike se publicarmos base derivada; uso moderado da instância pública |
| CSO / Tailte Éireann | Limites oficiais IE | CC-BY 4.0 (verificar) | Preferir ao OSM na Irlanda |
| ONS (UK), IBGE (BR) | Limites oficiais | Abertas (verificar) | — |
| Nominatim público | Geocodificação pontual | ODbL; política de uso | Máx. 1 req/s, sem uso em massa → self-host para volume |
| OpenFreeMap / Protomaps PMTiles | Tiles do mapa | Gratuito | Sem chave de API |
| Eircode (ECAD) | Endereço IE | **Pago** | Não usar; aproveitar Eircode só quando vier da fonte |

## 4. Fontes ativas

Nenhuma. (Atualizar ao concluir a Fase 3.)
