# Entrypoints e módulos legados — removidos

## UI (Fase 0)

| Removido | Substituído por |
|----------|-----------------|
| `app.py` (Streamlit) | `web_app.py` + `/dashboard` |
| `sentinela_web/` (Reflex) | `web_app.py` + `static/app.js` |
| `rxconfig.py` | — |
| `.streamlit/`, `reflex.lock/` | — |
| `backend.zip`, `frontend.zip` | — |

**UI canônica:** `pip install -r requirements-web.txt` e `python web_app.py` → http://localhost:5055/dashboard

## Pipeline despesas API (removido)

Pipeline paralelo ao PNCP — nunca integrado ao CLI nem a `automacoes/pipeline.py`:

| Removido | Motivo |
|----------|--------|
| `automacoes/runners/orquestrador.py` | Morto; env `SENTINELA_API_*` / `PIPELINE_*` |
| `extrator/api_client.py` | Só usado pelo orquestrador |
| `analise/transformador.py` | Zero imports |
| `GerenciadorBanco.salvar_despesas()` | Substituído por `db/narrativa.py` (só narrativa IA) |

**Pipeline canônico:** `automacoes/pipeline.py` — PNCP coletar → enriquecer → analisar → investigar → Discord

## Extrator PNCP duplicado

| Removido | Substituído por |
|----------|-----------------|
| `extrator/extrator_pncp.py` | `extrator/pncp.py` |

## Scripts ad-hoc

| Removido | Nota |
|----------|------|
| `analise/analise_exploratoria.py` | EDA one-off com path hardcoded |

## Painel HTML estático (removido)

| Removido | Motivo |
|----------|--------|
| `relatorios/painel_html.py` + CLI `painel` | Export offline pré-SPA sem uso; a UI canônica é a SPA Flask (`/dashboard`) |

**CLI canônica:** `python __main__.py status|coletar|analisar|investigar|relatorio|dossie|publicar|pipeline`
