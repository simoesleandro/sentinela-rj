# Roadmap estratégico — Sentinela como referência em fiscalização pública

**Atualizado:** julho/2026 · **Horizonte:** 6 meses · **Revisão:** ao fim de cada fase

## Visão

Transformar o Sentinela RJ de monitor de contratos em **referência de fiscalização
cidadã de contratações públicas**: a ferramenta que jornalistas de dados, órgãos de
controle e cidadãos consultam — e citam — quando o assunto é contratação pública
municipal no Rio de Janeiro.

O que separa uma referência de um scanner de dados não é quantidade de features:

1. **Credibilidade** — metodologia publicada, taxa de erro medida, resultados verificáveis;
2. **Profundidade** — cruzamentos que ninguém mais faz (lotação × órgão foi o primeiro);
3. **Distribuição** — os achados chegam a quem pode agir.

Todo item deste plano serve a um desses três.

## Princípios (não negociáveis)

- **Indício, não acusação.** Nada aqui muda o papel do sistema: triagem técnica
  que prepara evidência para decisão humana.
- **Explicabilidade por construção.** Todo sinal novo nasce com campo
  `metodologia`, limiar documentado e entrada em [DETECTORES.md](DETECTORES.md).
- **Validação empírica antes de produção.** Medir a distribuição real do sinal
  em modo leitura, reportar, só então persistir (o sinal de qualificação do sócio
  ficou fora da fórmula de prioridade porque a medição mostrou 84,7% de saturação
  — esse é o método).
- **Heurísticas explicáveis + IA generativa como apoio.** Sem ML treinado do zero
  enquanto não houver rótulos suficientes.

---

## Pilar 1 — Credibilidade científica

> Serenata de Amor, os robôs do TCU (Alice/Mônica) e o Tá de Pé viraram referência
> publicando **como** detectam e **quanto erram**. Este pilar é o que autoriza os outros.

| # | Item | Como | Esforço | Impacto |
|---|------|------|---------|---------|
| 1.1 | **Taxa de falso-positivo por detector, publicada** | Triagem por amostragem (50–100 rótulos/detector, começando pelos 118 prioritários do conflito de interesse) → página pública "Precisão medida", com intervalo de confiança e data da medição | M | **Altíssimo** — nenhuma ferramenta civic tech BR publica isso por detector |
| 1.2 ✅ | **Backtesting contra casos conhecidos** | Página `/backtesting` roda os detectores contra os casos investigados (MJRE, Bônus Track, Entre os Rios, Asfalto Fatiado): 4/4 detectados, com o detector temático disparando em todos. **Entregue jul/2026** (extensão: decisões públicas do TCM-RJ) | M | Alto — prova de valor verificável por terceiros |
| 1.3 | **Feedback loop de calibração** | Os motivos de descarte estruturados (já coletados na triagem) alimentam revisão periódica de limiares; cada revisão vira registro em DETECTORES.md | S | Médio — sistema que aprende com o auditor |
| 1.4 | **Versionamento de metodologia** | Campo `versao_detector` no alerta; mudou limiar → nova versão, alertas antigos preservam a sua | S | Médio — auditabilidade exigida para citação por MP/imprensa |

**Critério de sucesso do pilar:** página de precisão no ar com ≥ 3 detectores medidos.

## Pilar 2 — Novas fontes e cruzamentos

Em ordem de retorno por esforço:

| # | Item | Fonte | O que detecta | Esforço | Impacto |
|---|------|-------|---------------|---------|---------|
| 2.1 ✅ | **Competição fraca** (proxy de licitante único) | PNCP (API de contratações) | `desconto_zero_licitacao` + `licitacao_itens_desertos` — a API não expõe nº de propostas, então usa proxies. **Entregue jul/2026** | M | **Altíssimo** — indicador de competição é dos mais fortes da literatura |
| 2.2 ✅ | **Sanções federais** | Portal da Transparência (API CEIS/CNEP) | Fornecedor inidôneo/punido em qualquer esfera, consulta por CNPJ. **Entregue jul/2026** (CEPIM fica como extensão) | S | Alto — expande o `fornecedor_sancoes` local |
| 2.3 ✅ | **Atas e adesões ("carona")** | PNCP (flag + texto do objeto) | `adesao_carona` — contrato firmado por adesão a ata alheia acima de R$ 500 mil. O flag `fruto_adesao` vinha vazio; o texto do objeto entrega. **Entregue jul/2026** | S–M | Alto — vetor clássico de abuso pós-14.133 |
| 2.4 ✅ | **Doações de campanha × sócios** | TSE (prestação de contas de candidatos) | `socio_doou_campanha` — sócio-PF de fornecedor que doou a campanha municipal, confirmado por nome + 6 dígitos do CPF; fecha o CPF do sócio no conflito de interesse. **Entregue jul/2026** | M | Alto — resolve o "sem CPF"; ver pivô abaixo |
| 2.5 | **Diário Oficial do Rio (ferramenta do agente)** | doweb.rio.rj.gov.br (scraper, padrão do TCM/Playwright) | Nomeações/exonerações do servidor; extratos de contrato | M | Médio — automatiza o passo manual da triagem guiada |
| 2.6 | **Preço unitário por item** | PNCP (API de itens de contrato) | Sobrepreço vs. mediana de outros municípios na mesma categoria/item | **L** | Altíssimo, mas pesado — fica para a fase 3 |

**Critério de sucesso do pilar:** 2.1 e 2.2 em produção com alertas na triagem.

> **Pivô empírico do 2.4 (jul/2026).** A premissa "empresa doou para quem a
> contrata" está morta por lei: doação de PJ é proibida desde 2015 (Lei 13.165 +
> ADI 4650/STF). Medição no RJ 2024: 0 fornecedores doadores; só 531 CNPJs no
> estado, todos comitês/transferências partidárias. O valor migrou para o **sócio
> pessoa física**: cruzando o QSA com as doações de PF do TSE e confirmando por
> nome + 6 dígitos do CPF, 11 sócios-administradores confirmados — incluindo os
> casos MJRE (R$ 363M) e Entre os Rios (R$ 126M). Doação de PF é legal, então o
> sinal é de **alinhamento político** (contexto), não de ilegalidade. O bônus se
> confirmou: o cruzamento devolve o **CPF completo** do sócio, fechando a lacuna
> "sem CPF" do conflito de interesse. Detalhes em [DETECTORES.md](DETECTORES.md#12-sócio-doador-de-campanha--socio_doou_campanha).

## Pilar 3 — IA aplicada

Reusa a cascata existente (Gemma4 → Gemini → Groq) e a cota por usuário.

| # | Item | Como | Esforço | Impacto |
|---|------|------|---------|---------|
| 3.1 | **Boletim semanal gerado por IA** | Job no pipeline: resume os alertas novos da semana em linguagem jornalística; página `/boletim` + assinatura (item 5.1) | S–M | Alto — feature de IA mais visível pelo menor custo |
| 3.2 | **RAG sobre a Lei 14.133** | Base local dos artigos; narrativas e pareceres citam artigo com trecho literal, não de memória | M | Médio–alto — elimina alucinação legal, diferencial técnico |
| 3.3 | **Evals dos pareceres** | Conjunto de casos rotulados (sai da triagem 1.1) medindo qualidade da opinião da IA; publicar junto com a precisão dos detectores | M | Alto — credibilidade da IA + habilidade de mercado |
| 3.4 | **Busca em linguagem natural** | Text-to-SQL com guardrails (schema fixo, SELECT only, allowlist de tabelas) | M–L | Alto para demo; fase 3 |

## Pilar 4 — Escala multi-município

A arquitetura já é multi-município (`MUNICIPIO_IBGE`; Niterói, Caxias, Belford Roxo
já têm dados coletados). O produto único é o **comparativo**:

- 4.1 — Onboarding formal de 5–10 municípios da região metropolitana (config + volume de coleta) — **M**
- 4.2 ✅ — **Benchmark municipal**: página `/benchmark` compara os municípios em
  % sem licitação, concentração (top-1 e HHI) e valor médio, cada um vs. a mediana
  regional. Medido jul/2026: Japeri 34% sem licitação (6× a mediana de 5,7%).
  **Entregue jul/2026** — impacto altíssimo (nenhum painel público entrega isso em
  nível municipal)

## Pilar 5 — Distribuição e impacto

| # | Item | Como | Esforço | Impacto |
|---|------|------|---------|---------|
| 5.1 | **Alertas por assinatura** | E-mail (infra de email_envio já existe) e/ou Telegram, por órgão/fornecedor/tema — watchlists públicas | M | Alto — transforma visitantes em audiência |
| 5.2 | **API pública documentada** | Os endpoints REST já existem; documentar (OpenAPI), rate limit público, página para desenvolvedores | S–M | Alto — jornalistas de dados citam quem os serve |
| 5.3 | **Representação pré-formatada** | Botão "gerar ofício" no dossiê: documento estruturado com evidências, pronto para protocolar no TCM/MP | M | **Altíssimo** — converte alerta em ação institucional |
| 5.4 | **Parcerias ativas** | Apresentar o projeto a Open Knowledge BR, Transparência Brasil, cursos de jornalismo de dados | S (contínuo) | Alto — referência é status conferido por terceiros |

## Pilar 6 — Solidez institucional

Pré-requisitos para ser levado a sério (e proteção jurídica):

- 6.1 — **Página LGPD/uso de dados**: base legal do tratamento (dados públicos,
  interesse público, art. 7º/23 LGPD), o que é coletado, retenção — **S, obrigatório antes de crescer**
- 6.2 — **Mecanismo de contestação**: canal para pessoa/empresa citada pedir revisão,
  com fluxo definido e prazo — **S–M**
- 6.3 — CHANGELOG + releases versionadas — **S**
- 6.4 — Backups documentados e status page — **S**

---

## Sequência de execução

### Fase 1 — Fundação de credibilidade (≈ 30 dias)
| Ordem | Item | Pilar |
|-------|------|-------|
| 1 | Detector de licitante único (2.1) | Profundidade |
| 2 | Sanções federais CEIS/CNEP (2.2) | Profundidade |
| 3 | Triagem por amostra + página de precisão (1.1) | Credibilidade |
| 4 | Páginas LGPD + metodologia no site (6.1) | Institucional |

### Fase 2 — Profundidade + distribuição (≈ 90 dias)
| Ordem | Item | Pilar |
|-------|------|-------|
| 5 ✅ | Cruzamento TSE — sócio-doador + fecha CPF (2.4) | Profundidade |
| 6 | Boletim semanal por IA + assinatura (3.1 + 5.1) | IA/Distribuição |
| 7 | Ferramenta Diário Oficial no agente ReAct (2.5) | Profundidade |
| 8 | API pública documentada (5.2) | Distribuição |
| 9 | Atas e adesões (2.3) · Backtesting (1.2) | Profundidade/Credibilidade |

### Fase 3 — Plataforma (≈ 180 dias)
| Ordem | Item | Pilar |
|-------|------|-------|
| 10 | Benchmark multi-município (4.1 + 4.2) | Escala |
| 11 | Preço unitário por item (2.6) | Profundidade |
| 12 | Busca em linguagem natural (3.4) · Representação/ofício (5.3) | IA/Impacto |
| 13 | Evals de IA publicados (3.3) · Contestação (6.2) | Credibilidade/Institucional |

## Métricas de "referência" (como saber que chegou lá)

- **Precisão publicada** para ≥ 5 detectores, com metodologia aberta
- **≥ 1 citação externa** (matéria, relatório de órgão de controle ou trabalho acadêmico usando dados do Sentinela)
- **≥ 100 assinantes** de alertas/boletim
- **≥ 5 municípios** com cobertura ativa e benchmark comparativo
- **≥ 1 representação protocolada** gerada pela ferramenta
- **API pública** com consumidores externos reais

## O que NÃO fazer (guarda contra overengineering)

- **ML treinado do zero** — sem rótulos suficientes; heurísticas explicáveis + IA
  generativa são mais defensáveis perante órgão de controle.
- **App mobile** — a web responsiva atende; esforço não paga.
- **Blockchain/notarização** — não resolve nenhum problema real do domínio.
- **Migração de stack** (FastAPI, Postgres no core, microserviços) — decisões atuais
  documentadas no [ADR 001](decisoes/001-sqlite-core-postgres-dominios.md); revisitar
  só com dor real.
- **Cobertura nacional de largada** — profundidade no RJ primeiro; escala vem depois
  da credibilidade, não antes.

## Manutenção deste plano

Ao fim de cada fase: marcar o que foi entregue, registrar o que a validação empírica
derrubou (com o porquê — os "misses" documentados valem tanto quanto os acertos) e
repriorizar a fase seguinte. Este documento é versionado; mudanças de rumo ficam no
histórico do git.
