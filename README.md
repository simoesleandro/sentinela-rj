# Sentinela RJ

[![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=flat-square&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/leandro-sim%C3%B5es-7a0b3537b/)
[![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/simoesleandro)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)

> Sistema de monitoramento automatizado de contratos públicos do município do Rio de Janeiro, com detecção de anomalias e geração de relatórios investigativos.

---

## O que é

O Sentinela RJ coleta contratos publicados no [Portal Nacional de Contratações Públicas (PNCP)](https://pncp.gov.br), filtra os do município do Rio de Janeiro e aplica três tipos de análise estatística para detectar padrões suspeitos: outliers de valor, concentração atípica de fornecedor e contratos sem licitação competitiva.

O resultado é um relatório Markdown estruturado com score de risco por anomalia, métricas de suporte e placeholders para narrativa investigativa.

**Caso de uso real:** na base de 328 contratos coletados (mar/2023–mai/2026, R$ 1,24 bilhão), o sistema identificou automaticamente a suspensão judicial do contrato de R$ 315,9 milhões da MJRE Construtora (13 desvios-padrão acima da média da categoria), a inexigibilidade de R$ 45 milhões do Bonus Track Entretenimento e a concentração de R$ 86,4 milhões em 4 contratos para a Construtora Entre os Rios em 30 dias.

---

## Arquitetura

```
  [PNCP API]
  pncp.gov.br/api/consulta/v1
       |
       |  HTTP com retry/backoff
       v
  +--------------------+
  |  extrator/         |  Filtra: IBGE 3304557 (Rio) + esfera Municipal
  |  pncp.py           |  Pagina em janelas mensais de ate 500 registros
  +--------+-----------+
           |
           |  SQLite upsert
           v
  +--------------------+
  |  data/             |  contratos   fornecedores   orgaos
  |  sentinela_rj.db   |  alertas     coletas_log
  +--------+-----------+
           |
           v
  +-------------------------------------------+
  |  analisador/                              |
  |                                           |
  |  outliers.py      IQR + Z-score/categ.   |
  |  concentracao.py  janela deslizante 90d  |
  |  licitacao.py     regex art. 74 / 75     |
  |                                           |
  |  engine.py  ->  list[AnomaliaResult]      |
  +--------+----------------------------------+
           |
           v
  +--------------------+
  |  relatorios/       |  relatorio_YYYY-MM-DD.md
  |  builder.py        |  (Markdown com {NARRATIVA} placeholders)
  +--------------------+

  __main__.py  -  CLI unificado
  status | coletar | analisar | relatorio
```

---

## Stack

| Camada | Tecnologia | Motivo |
|--------|-----------|--------|
| Linguagem | Python 3.10+ | `statistics.quantiles`, `dataclasses`, `match` |
| Banco | SQLite via `sqlite3` (stdlib) | Zero dependências externas, auditável, portátil |
| HTTP | `requests` | Retry/backoff manual para API instável do PNCP |
| Análise | `statistics` (stdlib) | IQR, Z-score — sem Pandas, sem NumPy |
| Regex | `re` (stdlib) | Detecção de modalidade de contratação |
| CLI | `argparse` (stdlib) | Sub-comandos sem frameworks externos |
| Relatório | Markdown gerado em string | Abre em qualquer editor, commit-friendly |

**Dependência externa única:** `requests` (para o extrator).

---

## Instalação

```bash
git clone https://github.com/simoesleandro/sentinela-rj
cd sentinela-rj
pip install requests
```

Não há outros pacotes. O banco SQLite é criado automaticamente na primeira coleta.

---

## Uso

Todos os comandos são executados a partir da raiz do projeto.

### `status` — visão geral do banco

```bash
python __main__.py status
```

Mostra quantos contratos estão no banco, período coberto, data da última coleta e número de alertas ativos.

### `coletar` — busca contratos no PNCP

```bash
python __main__.py coletar                    # últimos 90 dias (padrão)
python __main__.py coletar 20230101 20261231  # intervalo customizado (AAAAMMDD)
```

Varre a API do PNCP pagina a pagina, filtra pelo município do Rio (IBGE 3304557) e esfera municipal, e faz upsert no banco. Tolera falhas de página isoladas sem perder o restante da coleta.

### `analisar` — detecta anomalias e salva alertas

```bash
python __main__.py analisar
```

Executa os três detectores, persiste os resultados na tabela `alertas` e imprime o resumo com top anomalias por score.

### `relatorio` — gera Markdown investigativo

```bash
python __main__.py relatorio               # salva em relatorios/
python __main__.py relatorio --dir /saida  # diretório customizado
```

Gera `relatorio_YYYY-MM-DD.md` com tabela completa de anomalias, seções detalhadas para score ≥ 0,70 (com placeholders `{NARRATIVA}`) e próximos passos dinâmicos baseados nos tipos encontrados.

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
├── __main__.py            # Entry point: python __main__.py <cmd>
├── db/
│   ├── schema.sql         # Tabelas e índices (CREATE TABLE IF NOT EXISTS)
│   └── conexao.py         # get_conn(), init_db()
├── extrator/
│   └── pncp.py            # Coleta paginada com retry/backoff
├── analisador/
│   ├── engine.py          # AnomaliaResult (dataclass) + analisar() + persistir_alertas()
│   ├── outliers.py        # Detector IQR por categoria
│   ├── concentracao.py    # Detector janela deslizante
│   └── licitacao.py       # Detector regex modalidade
├── relatorios/
│   └── builder.py         # Gerador de relatório Markdown
└── data/
    └── sentinela_rj.db    # SQLite — não versionado (.gitignore)
```

---

## Roadmap

- [ ] `main.py` com agendamento automático (coleta + análise semanal)
- [ ] Detector de fracionamento por Área de Planejamento (padrão "Asfalto Fatiado")
- [ ] Cruzamento com Portal da Transparência da Prefeitura (empenhos realizados)
- [ ] Série histórica 2019–2022 para comparação entre gestões
- [ ] Exportação para CSV/JSON para integração com ferramentas de visualização

---

## Fonte de dados

**PNCP — Portal Nacional de Contratações Públicas**
`GET https://pncp.gov.br/api/consulta/v1/contratos`

Filtros aplicados: `municipio_ibge = 3304557` (Rio de Janeiro) + `esfera_id = M` (Municipal).
A API é pública e não requer autenticação.

---

*Sentinela RJ — monitoramento independente de contratos públicos municipais*
