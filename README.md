<div align="center">

# Sentinela RJ

**PT:** Monitor autônomo de contratos públicos do município do Rio de Janeiro — detecção de anomalias com IA, investigação multi-fonte e dashboard em tempo real.  
**EN:** Autonomous public contracts monitor for Rio de Janeiro — AI-powered anomaly detection, multi-source investigation and real-time dashboard.

<br/>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?style=flat-square&logo=flask)](https://flask.palletsprojects.com)
[![Gemini](https://img.shields.io/badge/Gemini-2.5--Flash-4285F4?style=flat-square&logo=google)](https://aistudio.google.com)
[![Gemma](https://img.shields.io/badge/Gemma4-12B--local-8b5cf6?style=flat-square)](https://ollama.ai)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)
<br/>
[![CI](https://img.shields.io/github/actions/workflow/status/simoesleandro/sentinela-rj/ci.yml?style=flat-square&label=CI&logo=github)](https://github.com/simoesleandro/sentinela-rj/actions)
[![Deploy](https://img.shields.io/badge/deploy-Fly.io-7C3AED?style=flat-square&logo=fly.io)](https://sentinela-rj.fly.dev/dashboard)
[![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/simoesleandro/sentinela-rj?style=flat-square&color=8b5cf6)](https://github.com/simoesleandro/sentinela-rj/commits)
[![Issues](https://img.shields.io/github/issues/simoesleandro/sentinela-rj?style=flat-square&color=f59e0b)](https://github.com/simoesleandro/sentinela-rj/issues)

<br/>

[🔗 Demo ao vivo](https://sentinela-rj.fly.dev/dashboard) &nbsp;·&nbsp;
[📖 Documentação](docs/) &nbsp;·&nbsp;
[🐛 Reportar bug](https://github.com/simoesleandro/sentinela-rj/issues) &nbsp;·&nbsp;
[💡 Sugerir feature](https://github.com/simoesleandro/sentinela-rj/issues)

<br/>

<img src="docs/demo.gif" alt="Demonstração do Sentinela RJ — do alerta à narrativa investigativa" width="920">

<sub>Do alerta detectado à narrativa investigativa da IA · <a href="https://sentinela-rj.fly.dev/dashboard">experimente ao vivo</a></sub>

</div>

---

## 📋 Índice / Table of Contents

- [Sobre](#-sobre--about)
- [Por que importa](#-por-que-importa--why-it-matters)
- [Competências demonstradas](#-competências-demonstradas--skills-demonstrated)
- [Números atuais](#-números-atuais--current-stats)
- [Caso real documentado](#-caso-real-documentado--real-case)
- [Funcionalidades](#-funcionalidades--features)
- [Detectores de anomalia](#-detectores-de-anomalia--anomaly-detectors)
- [Pipeline de IA](#-pipeline-de-ia--ai-pipeline)
- [Agente Investigador](#-agente-investigador--investigation-agent)
- [Stack](#-stack)
- [Instalação](#-instalação--setup)
- [Uso](#-uso--usage)
- [Variáveis de Ambiente](#-variáveis-de-ambiente--environment-variables)
- [Arquitetura](#-arquitetura--architecture)
- [Deploy Fly.io](#-deploy-flyio)
- [Testes](#-testes--tests)
- [O que aprendi](#-o-que-aprendi--what-i-learned)
- [Roadmap](#-roadmap)
- [Autor](#-autor--author)

---

## 📌 Sobre / About

**PT:**  
O Sentinela RJ coleta automaticamente contratos públicos do Portal Nacional de Contratações Públicas (PNCP), aplica 9 detectores estatísticos e cadastrais para identificar anomalias, e usa IA local (Gemma 4) + Gemini para gerar narrativas investigativas com comparação A/B de vereditos. Um agente ReAct cruza múltiplas fontes externas para investigação profunda. Tudo disponível em dashboard público com dados abertos.

**EN:**  
Sentinela RJ automatically collects public contracts from Brazil's PNCP portal, applies 9 statistical and registry detectors to identify anomalies, and uses local AI (Gemma 4) + Gemini to generate investigative narratives with A/B verdict comparison. A ReAct agent crosses multiple external sources for deep investigation. All available on a public dashboard with open data.

---

## 🎯 Por que importa / Why it matters

**PT:**  
Contratos públicos são dados abertos, mas raramente são fáceis de analisar. O Sentinela RJ transforma milhares de registros do PNCP em alertas acionáveis, destacando valores atípicos, concentração de fornecedores, possíveis fracionamentos e sinais cadastrais que merecem auditoria humana.

O objetivo não é substituir controle institucional ou análise jurídica. É criar uma camada técnica de triagem: coletar, normalizar, cruzar, priorizar e explicar indícios para que pessoas consigam investigar mais rápido.

**EN:**  
Public contracts are open data, but they are rarely easy to analyze. Sentinela RJ turns thousands of PNCP records into actionable alerts, surfacing outliers, supplier concentration, possible contract splitting and registry signals that deserve human review.

The goal is not to replace institutional oversight or legal analysis. It is a technical triage layer: collect, normalize, cross-check, prioritize and explain signals so people can investigate faster.

---

## 🧠 Competências demonstradas / Skills demonstrated

| Área | Evidência no projeto |
|------|---------------------|
| Backend Python | CLI, Flask dashboard, pipeline agendado e serviços de análise |
| Dados e SQL | SQLite persistente, migrações, consultas para contratos, alertas e fornecedores |
| Análise de anomalias | Detectores estatísticos, cadastrais e regras de negócio aplicadas a dados reais |
| IA aplicada | Narrativas investigativas, comparação A/B de vereditos e fallback entre provedores |
| Civic tech | Uso de dados públicos para transparência e priorização de investigação |
| Deploy | Fly.io com volume SQLite persistente e configuração por variáveis de ambiente |
| Testes | 272 testes pytest cobrindo detectores, banco, pipeline, dashboard, dossiê, triagem e conflito de interesse |

---

## 📊 Números atuais / Current Stats

| Indicador | Valor |
|-----------|-------|
| 📄 Contratos analisados | **4.925+** |
| 💰 Valor total monitorado | **R$ 11,28 bilhões+** |
| 🚨 Anomalias detectadas | **1.497+** |
| 🔴 Risco alto | **174+** |
| 🏢 Fornecedores distintos | **1.549+** |
| 📅 Período coberto | Jul/2022 → hoje |

---

## 🔍 Caso real documentado / Real Case

> **MJRE Construtora** — contrato de R$ 315,9 milhões suspenso judicialmente 11 dias após assinatura

| Fato | Detalhe |
|------|---------|
| 🤖 Detecção automática | Outlier estatístico — 13 desvios padrão acima da média da categoria |
| ⚖️ Decisão judicial | 3ª Vara da Fazenda Pública do TJRJ — juíza Mirela Erbisti, 03/04/2026 |
| 💸 Prejuízo evitado | Concorrente R$ 25 milhões mais barato foi desclassificado sem análise |
| 📂 Fonte | Dados públicos PNCP + decisão judicial TJRJ |

---

## ✨ Funcionalidades / Features

- ✅ **Coleta automática** via API PNCP com pipeline agendado (cron)
- ✅ **9 detectores de anomalia** estatísticos e cadastrais
- ✅ **Narrativa investigativa** — Gemma 4 12B gera o corpo da análise
- ✅ **Vereditos A/B** — Gemini e Gemma4 emitem vereditos independentes para comparação
- ✅ **Agente Investigador ReAct** — coleta BrasilAPI, PNCP histórico, DataJud CNJ, TCM-RJ
- ✅ **Investigação profunda** em background com polling em tempo real
- ✅ **Dashboard interativo** — triagem, linha do tempo, rede de fornecedores
- ✅ **Dossiê exportável** — Markdown, PDF e JSON por alerta
- ✅ **Deploy público** — Fly.io com SQLite persistente em volume
- ✅ **Dados abertos** — export CSV de contratos e alertas
- ✅ **Multi-município** — monitoramento configurável por IBGE
- 🚧 **TJRJ processos** — aguardando API pública com campo `partes` (issue #2)

---

## 🔎 Detectores de anomalia / Anomaly Detectors

| Detector | O que detecta |
|----------|--------------|
| `outlier_valor` | Contratos com valor estatisticamente atípico (IQR + Z-score por categoria) |
| `concentracao_fornecedor` | Fornecedor concentrando contratos em janela de 90 dias |
| `fracionamento_ap` | Possível fracionamento por Área de Planejamento |
| `inexigibilidade` | Contratações sem licitação com valor elevado |
| `emergencia` | Contratações de emergência acima do limiar legal |
| `aceleracao_contratual` | Crescimento atípico de contratos por fornecedor |
| `capital_social_baixo` | Capital incompatível com valor contratado |
| `empresa_jovem_contrato_grande` | Empresa nova com contrato de alto valor |
| `socios_compartilhados` | Fornecedores com sócios em comum |

---

## 🤖 Pipeline de IA / AI Pipeline

```
Alerta detectado
      ↓
Gemma 4 12B (Ollama local) — gera corpo da narrativa investigativa
      ↓
┌──────────────────┬──────────────────┐
│  Gemma4 veredito  │  Gemini veredito  │  ← comparação A/B
│  (local, grátis)  │  (API, preciso)   │
└──────────────────┴──────────────────┘
      ↓
Auditor humano aplica o veredito preferido com 1 clique
```

---

## 🕵️ Agente Investigador / Investigation Agent

ReAct loop com 5 ferramentas — roda em background, resultado via polling:

| Ferramenta | Fonte | Dados coletados |
|------------|-------|-----------------|
| `brasilapi_enriquecido` | BrasilAPI | Cadastro, sócios, capital social, CNAE |
| `pncp_historico` | PNCP API | Histórico completo de contratos do fornecedor |
| `pncp_orgao` | PNCP API | Contratos recentes do órgão contratante |
| `datajud_tjrj` | DataJud CNJ | Processos judiciais (campo `partes` não exposto na API pública) |
| `tcm` | TCM-RJ | Decisões de auditoria via Playwright |

Gemma 4 sintetiza as evidências e emite conclusão estruturada:
- **Status:** `confirmar` / `arquivar` / `escalar` / `inconclusivo`
- **Grau de confiança:** `alto` / `medio` / `baixo`
- **Recomendação:** ação concreta baseada nos dados

---

## 🛠 Stack

| Camada | Tecnologia |
|--------|------------|
| Backend | Python 3.11+ · Flask · Waitress |
| Frontend | HTML/CSS/JS vanilla |
| Banco | SQLite (`data/sentinela_rj.db`) + Volume Fly.io |
| IA narrativa | Gemma 4 12B via Ollama (local) |
| IA veredito | Gemini 2.5 Flash + Gemma 4 (A/B) |
| Coleta | PNCP API REST (dados abertos) |
| Enriquecimento | BrasilAPI · DataJud CNJ |
| Scraping | Playwright (TCM-RJ) |
| Deploy | Fly.io · região gru · SQLite volume 1GB |
| Testes | pytest — 272 testes |

---

## 🚀 Instalação / Setup

### Pré-requisitos / Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) para IA local — `ollama pull llama3.1` e/ou `ollama pull gemma4:12b`
- Chave Gemini (gratuita em [aistudio.google.com](https://aistudio.google.com))

### Instalação / Installation

```bash
# Clone o repositório
git clone https://github.com/simoesleandro/sentinela-rj
cd sentinela-rj

# Instale as dependências
pip install -r requirements-web.txt
pip install -r requirements-ia.txt   # opcional: Gemini/Groq

# Configure as variáveis de ambiente
cp .env.example .env
# Edite .env com sua GEMINI_API_KEY

# Rode o dashboard
python web_app.py
# → http://localhost:5055/dashboard
```

---

## 💻 Uso / Usage

### Pipeline completo

```bash
python __main__.py coletar          # coleta contratos do PNCP
python __main__.py enriquecer       # enriquece com BrasilAPI
python __main__.py analisar         # detecta anomalias
python __main__.py investigar       # gera narrativas IA (Gemma4 + Gemini)
```

### Investigação profunda de um alerta

```bash
python __main__.py investigar_profundo <alerta_id>
```

### Pipeline automático (agendado)

```bash
python -m automacoes.pipeline --once    # uma execução
python -m automacoes.pipeline --daemon  # APScheduler contínuo
```

### Dossiê de um alerta

```bash
python __main__.py dossie --alerta 42 --formato md
python __main__.py dossie --alerta 42 --formato pdf
```

---

## 🔐 Variáveis de Ambiente / Environment Variables

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `GEMINI_API_KEY` | Gemini API (narrativas e vereditos) | — |
| `SENTINELA_IA_PROVIDER` | `gemini` no deploy, `ollama` local | `ollama` |
| `GROQ_API_KEY` | Groq (fallback opcional) | — |
| `DB_PATH` | Caminho do SQLite | `data/sentinela_rj.db` |
| `DATAJUD_API_KEY` | DataJud CNJ (chave pública disponível na wiki) | — |
| `SENTINELA_IA_REVISAO_GEMINI` | Habilita veredito Gemini | `true` |
| `SENTINELA_IA_REVISAO_GEMMA4` | Habilita veredito Gemma4 | `true` |
| `GEMMA4_MODEL` | Modelo Gemma4 no Ollama | `gemma4:12b` |
| `MUNICIPIO_IBGE` | Código IBGE do município | `3304557` (Rio) |
| `PIPELINE_CRON` | Expressão cron do pipeline | `0 8 * * 1` |

> Lista completa em: [`.env.example`](.env.example)

---

## 🏗 Arquitetura / Architecture

```
sentinela-rj/
├── web_app.py              # Dashboard Flask (:5055/dashboard)
├── __main__.py             # CLI (coletar, analisar, investigar...)
├── analise/
│   └── motor_ia.py         # Gemma4 + Gemini — narrativas e vereditos A/B
├── analisador/             # 9 detectores de anomalia
├── investigacao/           # Agente ReAct
│   ├── agente.py           # ReAct loop principal
│   └── ferramentas/        # BrasilAPI, PNCP, DataJud, TCM
├── automacoes/
│   └── pipeline.py         # Pipeline agendado
├── db/                     # SQLite — conexão e migrações
├── relatorios/
│   └── dossie.py           # Dossiê exportável (MD/PDF/JSON)
├── static/                 # UI web (HTML/CSS/JS)
├── tests/                  # 101+ testes pytest
├── Dockerfile              # Container para Fly.io
├── fly.toml                # Config deploy
└── .env.example            # Variáveis documentadas
```

**Fluxo principal:**

```
PNCP API → extrator → SQLite
                ↓
         9 detectores → alertas
                ↓
    Gemma4 (narrativa) + Gemini/Gemma4 (veredito A/B)
                ↓
         Dashboard Flask → Auditor humano
                ↓
    Agente ReAct (investigação profunda) → Dossiê
```

---

## ☁️ Deploy Fly.io

```bash
fly auth login
fly launch --no-deploy --name sentinela-rj --region gru
fly volumes create sentinela_data --region gru --size 1
fly secrets set GEMINI_API_KEY=... SENTINELA_IA_PROVIDER=gemini
fly deploy

# Upload do banco local
fly sftp shell
# >> put data/sentinela_rj.db /data/sentinela_rj.db
```

> ⚠️ Ollama/Gemma4 não disponíveis no Fly.io — IA via Gemini em produção.

---

## 🧪 Testes / Tests

```bash
# Instalar as dependências de desenvolvimento (inclui pytest + libs de todos os domínios)
pip install -r requirements-dev.txt

# Rodar todos os testes
pytest

# Com cobertura
pytest --cov=analise --cov-report=term-missing

# Teste específico
pytest tests/test_motor_ia.py -v
```

> **272 testes** cobrindo motor IA, detectores, pipeline, dashboard, dossiê e conflito de interesse.

---

## 📚 O que aprendi / What I learned

- Modelar um pipeline de dados públicos ponta a ponta: coleta, persistência, enriquecimento, análise e apresentação.
- Separar sinais estatísticos de conclusões: o sistema aponta indícios, mas mantém a decisão final como auditoria humana.
- Trabalhar com limitações reais de APIs públicas, dados incompletos e diferenças entre ambiente local e produção.
- Usar LLMs como apoio explicativo, não como única fonte de decisão.
- Criar testes para regras de negócio sensíveis, como detectores de anomalia, score composto, dossiês e triagem.
- Fazer deploy de uma aplicação orientada a dados com SQLite persistente em produção.

---

## 🗺 Roadmap

- [x] Dashboard Flask com triagem, dossiê, grafo e narrativa IA
- [x] 9 detectores de anomalia (IQR, concentração, fracionamento, etc.)
- [x] Pipeline agendado com notificações Discord
- [x] Gemma 4 12B como gerador principal de narrativas
- [x] Comparação A/B de vereditos Gemini vs Gemma4
- [x] Agente Investigador ReAct com 5 ferramentas
- [x] Investigação profunda em background com polling
- [x] Deploy público Fly.io com SQLite persistente
- [x] Multi-município via env
- [ ] TJRJ processos via Playwright com credencial (issue #2)
- [ ] Transparência RJ empenhos reais
- [ ] Busca natural em linguagem humana
- [ ] Alertas Telegram para cidadãos
- [ ] Mapa geográfico de contratos por bairro

---

## 👤 Autor / Author

<div align="center">

**Leandro Simões**

[![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=flat-square&logo=linkedin&logoColor=white)](https://linkedin.com/in/leandro-sim%C3%B5es-7a0b3537b)
[![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/simoesleandro)
[![Portfolio](https://img.shields.io/badge/Portfolio-06b6d4?style=flat-square&logo=safari&logoColor=white)](https://simoesleandro.github.io/portfolio)

*Fullstack · IA Aplicada · Civic Tech*

</div>

---

<div align="center">

Feito com ☕ e IA em / Made with ☕ and AI in 🇧🇷 Rio de Janeiro

> *Todos os dados são públicos e obtidos de fontes oficiais do governo brasileiro.*  
> *All data is public and sourced from official Brazilian government portals.*

</div>
