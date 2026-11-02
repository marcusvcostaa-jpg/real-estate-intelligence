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
| Property Price Register | IE | Política de reutilização PSRA / CC BY 4.0 | CSV oficial com vendas residenciais | ✅ ATIVA (`ie_ppr`) |
| HM Land Registry — Price Paid Data | UK (Ing./Gales) | OGL v3 | CSV mensal | NÃO VERIFICADO |
| DVF (Demandes de valeurs foncières) | FR | Licence Ouverte | — | NÃO VERIFICADO |
| ITBI — Prefeitura de São Paulo | BR | Transparência ativa obrigatória (Lei SP 18.161/2024, art. 18-A); sem licença explícita | XLSX anual (aba por mês de pagamento), 2006–2026 | ✅ ATIVA (`br_sp_itbi`) |
| ITBI — Recife | BR | ODbL (portal dados.recife.pe.gov.br) | CSV anual | Candidata (portal inacessível daqui em 2026-11-01) |
| ITBI — Porto Alegre | BR | Portal de dados abertos (verificar licença) | Bases 2020–2025; robots `Crawl-Delay: 10` | Candidata |

### Geografia

| Fonte | Uso | Licença | Observação |
|---|---|---|---|
| OpenStreetMap (Overpass API) | Limites administrativos, bairros | ODbL | Share-alike se publicarmos base derivada; uso moderado da instância pública |
| **Tailte Éireann** — National Statutory Boundaries 2019, gen. 20 m (condados, áreas administrativas, divisões eleitorais) | Limites oficiais IE | **CC BY 4.0** — atribuição "© Tailte Éireann" (no mapa) | ✅ EM USO (aprovado 2026-11-01). Serviço ArcGIS `services-eu1.arcgis.com/FH5XCsx8rYXqnjF5`; não serve para fins legais/cadastrais |
| **IBGE** — malha municipal 2025 (`CGMAT:qg_2025_030_munic`) e distritos Censo 2022 (`CGMAT:qg_2022_630_distrito_agreg`) | Limites oficiais BR | Uso livre citando a fonte "IBGE"; IBGE não tem atribuição legal de demarcar limites | ✅ EM USO (aprovado 2026-11-01). WFS `geoservicos.ibge.gov.br/geoserver/ows` (o `servicodados.ibge.gov.br` não respondia daqui). São Paulo: 1 município + 96 distritos |
| ONS (UK) | Limites oficiais | Abertas (verificar) | — |
| Nominatim público | Geocodificação pontual | ODbL; política de uso | Máx. 1 req/s, sem uso em massa → self-host para volume |
| OpenFreeMap / Protomaps PMTiles | Tiles do mapa | Gratuito | Sem chave de API |
| Eircode (ECAD) | Endereço IE | **Pago** | Não usar; aproveitar Eircode só quando vier da fonte |

## 4. Fontes ativas

| Código | Fonte | Tipo | Dados | Escopo | Permissão | Atualização |
|---|---|---|---|---|---|---|
| `ie_ppr` | Residential Property Price Register (PSRA, Irlanda) | OPEN_DATA (ZIP oficial `PPR-ALL.zip`) | Preços **transacionados** → `property_transactions` | Dublin + expansão a condados vizinhos (aprovada 2026-11-01): Meath, Kildare, Wicklow | APPROVED em 2026-11-01 pelo responsável (chat) | 7 dias; 1 download/execução; máx. 4 req/dia |
| `br_sp_itbi` | Transações com ITBI — Prefeitura de São Paulo (Secretaria Municipal da Fazenda) | OPEN_DATA (XLSX anual) | Valores **declarados** de transação → `property_transactions` | Município de São Paulo (IBGE 3550308), últimos 5 anos | APPROVED em 2026-11-01 pelo responsável (chat: "Aprovo os dois") | 30 dias; 1 arquivo por página (página de índice + GET condicional); máx. 4 páginas/dia |

**`ie_ppr` — evidências e regras de uso** (registradas em `source_permissions`):
- Política de reutilização da PSRA ([psr.ie](https://www.psr.ie/re-use-of-public-sector-information/), atualizada 2022-07-29): reutilização gratuita em qualquer formato, inclusive publicação, desde que: citar a fonte e o copyright da PSRA; reproduzir com exatidão; não usar de forma enganosa; não usar principalmente para publicidade; não usar para fins ilegais.
- [data.gov.ie](https://data.gov.ie/dataset/dublin-residential-property-price-register): subconjunto de Dublin publicado pela PSRA sob **CC BY 4.0**.
- `propertypriceregister.ie/robots.txt` → 404 (sem restrições declaradas).
- **Atribuição obrigatória no dashboard:** "Source: Residential Property Price Register, Property Services Regulatory Authority (PSRA). © PSRA."
- Avisos que a interface deve respeitar: não é índice de preços; preços com `is_full_market_price = false` não são valor de mercado; `vat_exclusive = true` indica preço sem IVA; sem área nem número de cômodos (a faixa "Property Size Description" fica só no `raw_payload`).
- Formato: CSV cp1252, 9 colunas; linhas idênticas são legítimas (unidades vendidas juntas) e recebem `external_id` distinto (hash da linha + nº da ocorrência).
- Qualidade observada: 179 Eircodes compartilhados por endereços com números diferentes (placeholders como "A123456" ou erros de digitação) — ignorados na deduplicação e marcados `EIRCODE_SHARED`.
- Primeira coleta (2026-11-01): 255.242 vendas (2010-01-01 a 2026-10-23), conferidas contra contagem independente do arquivo.

**`br_sp_itbi` — evidências e regras de uso** (registradas em `source_permissions`):
- Página da Fazenda ([acesso à informação](https://prefeitura.sp.gov.br/web/fazenda/w/acesso_a_informacao/31501)): um XLSX/ODS por ano de 2006 a 2026; o ano corrente é atualizado todo mês. O anúncio da prefeitura diz que os dados servem à população e a pesquisadores e omitem nomes de compradores e vendedores.
- [Lei municipal 18.161/2024](https://www.saopaulo.sp.leg.br/iah/fulltext/leis/L18161.pdf), art. 18-A: publicação mensal, "para consulta geral dos interessados", dos últimos 5 anos (SQL, matrícula, cartório, endereço, valor declarado, valor venal de referência, data e natureza), **sem identificação** de compradores e vendedores. A página **não declara licença**: o uso se apoia nessa transparência obrigatória e na Lei 17.901/2023 (dados abertos); confirmação formal pode ser pedida pelo responsável via LAI.
- robots.txt de `prefeitura.sp.gov.br` e `drive.prefeitura.sp.gov.br` permitem `/`.
- **Atribuição obrigatória:** "Fonte: Prefeitura de São Paulo — Secretaria Municipal da Fazenda (transações imobiliárias com ITBI)."
- Avisos que a interface respeita: valor **declarado** ao fisco (pode ser menor que o negociado; a base de cálculo é o maior entre ele e o valor venal de referência); linhas agrupadas pelo **mês de pagamento** do imposto, não da transação; excluídos imóveis rurais, parcelamentos (PPI) e autos de infração.
- Formato: abas mensais `MMM-AAAA` com 28 colunas (cabeçalho com `N°`/`Nº` e erros de digitação variáveis → colunas casadas por nome normalizado); abas LEGENDA/EXPLICAÇÕES/tabelas ignoradas. Linhas deslocadas (complemento partido em duas colunas + nome de empresa) são **descartadas sem gravar** (3 em 155.906 em 2026); mais de 1% malformado interrompe a coleta (`SourceFormatChanged`).
- Normalização (valores originais sempre em `raw_payload`):
  - `is_full_market_price`: `true` só para natureza "1.Compra e venda" com 100% transmitido; `false` para outras naturezas (dação, integralização de capital, leilão, permuta…); `NULL` para frações (parte do imóvel ou lançamento declarado no SQL do terreno — indistinguíveis). `vat_exclusive = false` (não há IVA na transmissão de imóveis no Brasil).
  - `source_property_key = "sql:<SQL>"` só quando o SQL identifica o imóvel: transmissão de 100% e não uma unidade ("AP 12", "CJ 5"…) declarada num lote sem condomínio (fração ideal 1). Frações e unidades no lote ficam sem chave (cada venda = um imóvel).
  - `built_area_m2` = área construída do **IPTU do exercício atual** (inclui a quota de áreas comuns do condomínio; base `BUILT`), só quando o SQL identifica o imóvel; `land_area_m2` só fora de condomínio (em condomínio a área do terreno é a do lote inteiro).
  - `property_type`/`category` do uso do IPTU (apartamento, casa, terreno, garagem, não residencial), só quando o SQL identifica o imóvel.
- Identidade (`external_id`): hash de SQL, data, valor, natureza, complemento e proporção + nº da ocorrência no arquivo. Linhas idênticas em arquivos de anos diferentes (24 entre 2025 e 2026, iguais até na matrícula) são a mesma declaração republicada e contam uma vez. Arquivos antigos guardam números como float (`100800297.0`) e algumas abas vêm sem cabeçalho (2024: JAN e OUT) — tratados sem mudar a identidade.
- Primeira coleta (2026-11-01): arquivos 2026 e 2025 → **386.397 vendas** (386.431 linhas − 10 malformadas − 24 repetidas entre anos), soma conferida ao centavo contra contagem independente das planilhas (R$ 249.360.339.427,09); deduplicação por SQL → 374.020 imóveis, 0 pares para revisão; validação: 3.202 `PRICE_VERY_LOW`, 523 `PRICE_VERY_HIGH`. Mediana residencial 12 meses R$ 459.000; preço/m² (área construída IPTU) R$ 4.857 em 70.958 vendas. Concluída em 2026-11-02 pelo orquestrador (2024–2022): **943.471 vendas de 2022 a 2026** (2024: 217.746 linhas − 3 malformadas; 2023: 175.459 − 2; 2022: 163.903; 53 declarações repetidas entre anos contadas uma vez) → **888.526 imóveis**, 49.069 com mais de uma venda, 0 conflitos/revisões. Validação: 7.727 `PRICE_VERY_LOW`, 1.188 `PRICE_VERY_HIGH`, 1 `PRICE_NON_POSITIVE`. Últimos 12 meses: mediana R$ 459.000 (+2,0% sobre os 12 anteriores), R$ 4.857/m² em 70.951 vendas.
- Limites conhecidos: repetições de venda de lançamentos não são ligadas; algumas linhas declaram vagas/depósitos no SQL do apartamento; datas de transação antigas aparecem em arquivos recentes (pagamento atrasado).
