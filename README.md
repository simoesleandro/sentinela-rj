# Sentinela RJ

[![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=flat-square&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/leandro-sim%C3%B5es-7a0b3537b/)
[![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/simoesleandro)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)

> Sistema de monitoramento automatizado de contratos públicos do município do Rio de Janeiro, com detecção de anomalias e geração de relatórios investigativos.

---

## O que é

O Sentinela RJ coleta contratos publicados no [Portal Nacional de Contratações Públicas (PNCP)](https://pncp.gov.br), filtra os do município do Rio de Janeiro e aplica seis detectores estatísticos e cadastrais. O painel Flask (`/dashboard`) concentra triagem de alertas, dossiês, grafo investigativo e exportações.

**Caso de uso real:** na base de 328 contratos coletados (mar/2023–mai/2026, R$ 1,24 bilhão), o sistema identificou automaticamente a suspensão judicial do contrato de R$ 315,9 milhões da MJRE Construtora (13 desvios-padrão acima da média da categoria), a inexigibilidade de R$ 45 milhões do Bonus Track Entretenimento e a concentração de R$ 86,4 milhões em 4 contratos para a Construtora Entre os Rios em 30 dias.

---

## Arquitetura

```
PNCP API → extrator/pncp.py → data/sentinela_rj.db
                                    ↓
              analisador/engine.py (6 detectores + sync de alertas)
                                    ↓
         alertas + triagem + narrativa_ia (Ollama/Gemini/Groq)
                                    ↓
    web_app.py (Flask)  |  relatorios/builder.py  |  relatorios/dossie.py
    /dashboard          |  CLI publicar           |  PATCH triagem
```

**Detectores:** outliers, concentração, licitação, fracionamento, sanções, sócios compartilhados.

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Core | Python 3.10+, SQLite, `requests` |
| Análise | `statistics`, regex — sem Pandas no pipeline |
| UI canônica | Flask + SPA estática (`web_app.py`) |
| IA | Ollama `llama3.1` (padrão), fallback Gemini/Groq |
| CLI | `python __main__.py` |
| Testes | `pytest` |

Dashboards Streamlit/Reflex estão **deprecados** — ver [DEPRECATED.md](DEPRECATED.md).

---

## Instalação

```bash
git clone https://github.com/simoesleandro/sentinela-rj
cd sentinela-rj
pip install -r requirements-web.txt   # core + Flask + fpdf2 (PDF dossiê)
pip install -r requirements-ia.txt    # opcional: Gemini/Groq
cp .env.example .env                  # opcional
```

---

## Uso

### CLI

```bash
python __main__.py status
python __main__.py coletar [data_ini data_fim]
python __main__.py analisar              # sync incremental — preserva triagem
python __main__.py investigar [--limite N]
python __main__.py relatorio [--dir DIR]
python __main__.py dossie --alerta ID [--formato md|json|pdf] [--gerar-ia]
python __main__.py publicar [--dir DIR] [--limite-ia N]
python __main__.py enriquecer [--reset]
python __main__.py painel
```

### Dashboard Flask

```bash
python web_app.py
# → http://localhost:5055/dashboard
```

| Aba | Função |
|-----|--------|
| **Visão Geral** | KPIs, gráficos e card de status do pipeline (`GET /api/pipeline/status`) |
| **Triagem** | Fila de alertas + `PATCH /api/alertas/{id}` com `{ "status", "nota" }` |
| **Monitoramento** | CRUD de watchlists e regras de alerta (filtros Discord) |
| **Rede** | Comparador multi-fornecedor, sócios compartilhados e grafo investigativo |

Export dossiê na API: `GET /api/dossie/{id}?formato=md|json|pdf`.

### Testes

```bash
python -m pytest
```

### Pipeline agendado (monitoramento contínuo)

```bash
python -m automacoes.pipeline --once      # uma execucao (Task Scheduler)
python __main__.py pipeline --once        # alias CLI
python -m automacoes.pipeline --daemon    # APScheduler embutido
```

Esteira: **coletar → enriquecer → analisar → investigar (Top N Ollama) → Discord**.

Logs em `logs/pipeline_YYYYMMDD.txt`. Agendar no Windows: `scripts\agendar.ps1`.

Variáveis principais do pipeline (`.env`):

| Variável | Uso |
|----------|-----|
| `PIPELINE_CRON` | Expressão cron (modo `--daemon`) |
| `PIPELINE_JANELA_DIAS` | Janela retroativa de coleta |
| `PIPELINE_INVESTIGAR_LIMITE` | Top N alertas para narrativa IA |
| `DISCORD_WEBHOOK_URL` | Notificações filtradas por regras de alerta |
| `MUNICIPIO_IBGE` | Código IBGE do município monitorado |

---

## Exemplos de output

### `status`

```
--------------------------------------------------------
  SENTINELA RJ  |  status
--------------------------------------------------------

  Banco        : data/sentinela_rj.db
  Contratos    : 327  |  R$ 1,245,655,956.52
  Fornecedores : 191  |  Orgaos: 4
  Periodo      : 2023-03-20 -> 2026-05-05

  Ultima coleta: nao registrada (coletas_log vazio)

  Alertas abertos: 48
```

### `analisar`

```
--------------------------------------------------------
  SENTINELA RJ  |  analisar
--------------------------------------------------------

  ..   Executando detectores...
  OK   outliers        21 anomalias
  OK   concentracao     3 anomalias
  OK   licitacao       16 anomalias

--------------------------------------------------------
  RESUMO DA ANALISE
--------------------------------------------------------
  Total de anomalias : 40
  ALTA               : 8
  MEDIA              : 4
  BAIXA              : 28

  Por tipo:
     21  outlier valor
     11  inexigibilidade
      3  dispensa
      3  concentracao fornecedor
      2  emergencia

  Alertas salvos no banco: 48

  Top anomalias:
     1. 0.891  [ALTA ]  Inexigibilidade — R$ 45,000,000 — BONUS TRACK ENTRETENIMENTO
     2. 0.884  [ALTA ]  Valor atipico — PRODUMIX COMERCIO E SERVICOS LTDA
     3. 0.878  [ALTA ]  Contrato emergencial — R$ 12,928,979 — AZOS VIGILANCIA
     4. 0.873  [ALTA ]  Dispensa — R$ 8,018,696 — MATRIZ CONSTRUCOES E SERVICOS
     5. 0.827  [ALTA ]  Valor atipico — GAIA COMERCIO E PRODUTOS QUIMICOS LTDA
     6. 0.820  [ALTA ]  Concentracao: 4 contratos em 90 dias — ENTRE OS RIOS LTDA
     7. 0.796  [ALTA ]  Valor atipico — PRONTO EXPRESS LOGISTICA SA
     8. 0.777  [ALTA ]  Valor atipico — BONUS TRACK ENTRETENIMENTO LTDA

  Tempo total: 24ms
```

---

## Metodologia

### Por que análise por categoria?

Contratos de diferentes categorias têm distribuições de valor completamente distintas. Na base do Rio, a mediana de "Compras" é ~R$ 10 mil; a de "Serviços de Engenharia" é ~R$ 15 milhões. Usar um limiar global único geraria centenas de falsos positivos em engenharia e cegaria o sistema para anomalias em compras.

A solução é calcular os limiares dentro de cada categoria — o que um contrato de R$ 5 milhões significa em "Compras" (500× a mediana, anomalia crítica) é completamente diferente do que significa em "Serviços de Engenharia" (abaixo da média, normal).

---

### Tipo 1 — Outlier de valor (`outlier_valor`)

**Método:** IQR de Tukey com Z-score como calibrador de severidade.

```
Q1, Q3  = quartis da distribuição de valor_global na categoria
IQR     = Q3 - Q1
fence   = Q3 + 1,5 × IQR          (limiar clássico de Tukey)
zscore  = (valor - média) / desvio_padrão

Flagrado se: valor > fence  E  zscore > 1,0
Severidade: alta se zscore ≥ 5 | média se zscore ≥ 3 | baixa caso contrário
```

O requisito duplo (acima da fence **e** zscore positivo) descarta falsos positivos gerados pela assimetria das distribuições — situações onde a média é puxada pelos próprios outliers e fica acima da fence.

Categorias com menos de 4 contratos usam as estatísticas globais como fallback.

---

### Tipo 2 — Concentração de fornecedor (`concentracao_fornecedor`)

**Método:** janela deslizante de 90 dias por fornecedor.

```
Para cada fornecedor com 2+ contratos:
  Para cada data de assinatura como âncora:
    janela = contratos nos próximos 90 dias
    se len(janela) >= 3  e  total >= R$ 1.000.000:
      score = 0,30 × min(qtd, 10)/10  +  0,70 × min(total / R$50M, 1,0)

Flagrada a janela de maior score por fornecedor.
```

Os pesos (30% quantidade, 70% valor) foram calibrados para distinguir dois padrões reais presentes na base:

| Fornecedor | Contratos | Total | Score |
|-----------|-----------|-------|-------|
| Cristália (farmacêutica) | 20 em 60 dias | R$ 316K | 0,13 (baixa) — filtrado |
| Entre os Rios (construtora) | 4 em 30 dias | R$ 86,4M | 0,82 (alta) — flagrado |

O limite de R$ 1 milhão descarta compras rotineiras fracionadas (medicamentos, materiais de escritório) que são operacionalmente normais.

---

### Tipo 3 — Sem licitação competitiva (`sem_licitacao_*`)

**Método:** detecção por expressão regular nos campos `informacao_complementar` e `objeto`.

A API do PNCP não retorna diretamente a modalidade licitatória no endpoint `/contratos`. A modalidade é inferida pelo texto das justificativas legais registradas no contrato.

| Subtipo | Padrões detectados | Lei de referência |
|---------|-------------------|-------------------|
| `inexigibilidade` | `art. 74`, `inexigibilidade`, `inviabilidade de competição` | Lei 14.133/2021, art. 74 |
| `emergencia` | `emergência`, `calamidade`, `art. 75 VIII` | Lei 14.133/2021, art. 75, VIII |
| `dispensa` | `dispensa`, `art. 75` | Lei 14.133/2021, art. 75 |

Limiares de severidade por subtipo (baseados nos limites legais da Lei 14.133/2021):

| Subtipo | Alta | Média | Baixa |
|---------|------|-------|-------|
| Inexigibilidade | ≥ R$ 10M | ≥ R$ 1M | < R$ 1M |
| Emergência | ≥ R$ 5M | ≥ R$ 500K | < R$ 500K |
| Dispensa | ≥ R$ 1M | ≥ R$ 200K | < R$ 200K |

---

## Estrutura do projeto

```
sentinela/
├── __main__.py              # CLI: coletar, analisar, dossie, pipeline…
├── web_app.py               # Flask SPA — UI canônica (:5055/dashboard)
├── automacoes/
│   ├── pipeline.py          # Coleta agendada + Discord
│   └── utils/notificador.py
├── db/
│   ├── schema.sql           # DDL SQLite
│   ├── conexao.py           # get_conn(), init_db()
│   ├── alertas_sync.py      # Sync incremental (preserva triagem)
│   ├── triagem.py           # Workflow de status
│   ├── watchlists.py        # CRUD watchlists
│   ├── regras_alerta.py     # Filtros de notificação
│   └── narrativa.py         # Persistência narrativa IA
├── extrator/
│   ├── pncp.py              # Coleta PNCP paginada
│   ├── enriquecedor.py      # BrasilAPI cadastral
│   ├── sancoes_ingestao.py  # CEIS/CNEP
│   └── transparencia_rj.py  # Cruzamento empenhos RJ
├── analisador/
│   ├── engine.py            # Orquestração dos detectores
│   ├── outliers.py          # IQR por categoria
│   ├── concentracao.py      # Janela 90 dias
│   ├── licitacao.py         # Regex modalidade
│   ├── fracionamento.py     # Fracionamento por AP
│   ├── sancoes.py           # Empresas inativas
│   ├── socios.py            # Sócios compartilhados
│   └── watchlists.py        # Detector de matches
├── analise/
│   ├── motor_ia.py          # Ollama / Gemini / Groq
│   └── grafo.py             # Rede investigativa
├── relatorios/
│   ├── builder.py           # Relatório Markdown
│   └── dossie.py            # Dossiê MD/JSON/PDF
├── static/ + templates/     # SPA do dashboard
├── tests/                   # pytest
└── data/sentinela_rj.db     # SQLite local (.gitignore)
```

---

## Roadmap

- [x] Dashboard Flask com triagem, dossiê, grafo e narrativa IA on-demand
- [x] Sync incremental de alertas (preserva triagem e narrativa IA)
- [x] Pipeline agendado (`coletar → enriquecer → analisar → investigar → notificar`)
- [x] Watchlists e alertas Discord (backend + UI na aba Monitoramento)
- [x] Card de status do pipeline na Visão Geral
- [x] Export PDF do dossiê (`?formato=pdf`)
- [x] Multi-município via env + backfill histórico + CEIS/CNEP + Transparência RJ
- [x] Cross-ref Transparência RJ no painel de detalhes do alerta
- [x] Comparador multi-fornecedor com lista de fornecedores investigados (`GET /api/fornecedores/investigados`)
- [x] Detector de evolução temporal (`evolucao_temporal_fornecedor`)
- [x] Score composto na listagem de alertas (coluna Prioridade + ordenação padrão)
- [x] Feedback estruturado ao descartar alertas (`motivo_descarte` + `GET /api/alertas/feedback/descartes`)
- [x] Seletor de município no dashboard (`GET /api/municipios` + filtro `municipio_ibge`)

---

## Fonte de dados

**PNCP — Portal Nacional de Contratações Públicas**
`GET https://pncp.gov.br/api/consulta/v1/contratos`

Filtros aplicados via env: `MUNICIPIO_IBGE` (padrão `3304557` — Rio de Janeiro) + `MUNICIPIO_ESFERA=M` (Municipal).
A API é pública e não requer autenticação.

---

*Sentinela RJ — monitoramento independente de contratos públicos municipais*
