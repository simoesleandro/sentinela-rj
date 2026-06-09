# Entrypoints legados (substituídos por `web_app.py`)

| Arquivo | Substituído por | Comando legado |
|---------|-----------------|----------------|
| `app.py` | `web_app.py` + `/dashboard` | `streamlit run app.py` |
| `sentinela_web/sentinela_web.py` | `web_app.py` | `reflex run` |
| `relatorios/dashboard.py` | removido | — |

**UI canônica:** `pip install -r requirements-web.txt` e `python web_app.py` → http://localhost:5055/dashboard

**CLI canônica:** `python __main__.py status|coletar|analisar|investigar|relatorio|dossie|publicar|painel|enriquecer`
