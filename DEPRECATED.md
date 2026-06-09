# Entrypoints legados — removidos

Os dashboards Streamlit e Reflex foram **removidos do repositório** (Fase 0).

| Removido | Substituído por |
|----------|-----------------|
| `app.py` (Streamlit) | `web_app.py` + `/dashboard` |
| `sentinela_web/` (Reflex) | `web_app.py` + `static/app.js` |
| `rxconfig.py` | — |

**UI canônica:** `pip install -r requirements-web.txt` e `python web_app.py` → http://localhost:5055/dashboard

**Funcionalidades migradas para a SPA Flask:**
- Triagem de alertas (`PATCH /api/alertas/<id>`)
- Narrativa IA on-demand (`POST /api/alertas/<id>/investigar` — Ollama/Llama)
- Export dossiê (`GET /api/dossie/<id>?formato=md`)
- Grafo investigativo, ranking, exports CSV

**CLI canônica:** `python __main__.py status|coletar|analisar|investigar|relatorio|dossie|publicar|pipeline`
