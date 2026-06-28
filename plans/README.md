# Proteções de Segurança Web — Sentinela RJ

Documento da auditoria de superfícies de entrada e das proteções aplicadas
(CSRF + security headers). Última revisão: 2026-06-27.

## 1. CSRF Protection

A app é uma SPA (fetch/JSON), sem formulários HTML server-rendered com POST
clássico. A única superfície de **escrita acionada de um formulário no
navegador com cookie de sessão** é o CRUD de Casos Investigados do admin.

Implementação (`web_app.py`):

- `Flask-WTF` (`CSRFProtect`) inicializado com `WTF_CSRF_CHECK_DEFAULT = False`
  — sem proteção automática global; aplicada explicitamente por endpoint.
- Decorator `@csrf_required` chama `csrf.protect()`, que valida o token vindo
  do campo `csrf_token` ou do header `X-CSRFToken`.
- Token exposto à página admin via `csrf_token()` (meta tag em
  `templates/admin_casos.html`) e enviado no header `X-CSRFToken` pelos fetch.
- `CSRFError` → resposta JSON `400 {"error": ..., "csrf": true}`.

### Rotas protegidas com CSRF

| Rota                         | Métodos             | Auth          | CSRF |
|------------------------------|---------------------|---------------|------|
| `/api/casos`                 | POST                | `@requer_admin` | ✅   |
| `/api/casos/<id>`            | PATCH, DELETE       | `@requer_admin` | ✅   |

> Obs.: `/admin/casos` é apenas a **página** (GET) que renderiza o formulário;
> as escritas vão para `/api/casos*`. A rota `/admin/apply-db` citada no pedido
> **não existe** no código — não há endpoint de aplicação de migrações via HTTP
> (migrações rodam no startup / sob demanda em `db.conexao.aplicar_migracoes`).

## 2. Security Headers

Injetados em **todas** as respostas via `after_request` `add_security_headers`:

| Header                      | Valor |
|-----------------------------|-------|
| `X-Frame-Options`           | `DENY` |
| `X-Content-Type-Options`    | `nosniff` |
| `X-XSS-Protection`          | `1; mode=block` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `Referrer-Policy`           | `strict-origin-when-cross-origin` |
| `Content-Security-Policy`   | ver abaixo |

CSP aplicada (ajustada às origens realmente usadas pelos templates):

```
default-src 'self';
script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com;
style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
font-src 'self' https://fonts.gstatic.com;
img-src 'self' data:;
connect-src 'self';
frame-ancestors 'none'
```

Diferenças vs. CSP do pedido original (intencionais, para não quebrar a UI):

- **`unpkg.com` adicionado a `script-src`** — `index.html` carrega
  `vis-network` do unpkg; sem isso o grafo de rede quebra.
- **`'unsafe-inline'` em `script-src`** — os templates usam handlers `onclick`
  inline e `<script>` embutidos.
- **`img-src 'self' data:`** — canvas/badges podem gerar data-URIs.

## 3. Auditoria de outros pontos de entrada

Varredura de **todas** as rotas POST/PATCH/DELETE de `web_app.py`. Após esta
revisão, nenhuma rota de escrita fica sem autenticação:

| Rota                                   | Métodos           | Proteção |
|----------------------------------------|-------------------|----------|
| `/api/alertas/<id>`                    | PATCH             | `@requer_login` ✅ |
| `/api/watchlists`                      | POST              | `@requer_login` ✅ |
| `/api/watchlists/<id>`                 | PATCH, DELETE     | `@requer_login` ✅ |
| `/api/regras-alerta`                   | POST              | `@requer_login` ✅ |
| `/api/regras-alerta/<id>`              | PATCH, DELETE     | `@requer_login` ✅ |
| `/api/alertas/<id>/investigar`         | POST              | `checar_cota_ia` (login + cota) |
| `/api/alertas/<id>/investigar_profundo`| POST              | `checar_cota_ia` |
| `/api/casos`, `/api/casos/<id>`        | POST/PATCH/DELETE | `@requer_admin` + `@csrf_required` |
| `/api/auth/login` `/registrar` `/logout` `/reenviar` | POST | autenticação própria |

### `@requer_login` (web_auth.py)

Decorator que exige sessão autenticada **apenas nos métodos de escrita**
(POST/PATCH/PUT/DELETE); GET/HEAD/OPTIONS passam direto, preservando o
dashboard público para leitura. Sem sessão → `401 {"auth": "login"}`. Usado nas
views que misturam leitura pública e escrita (triagem de alertas, watchlists,
regras), sem precisar quebrar a view em duas.

> Observação CSRF: estes endpoints de escrita são APIs JSON consumidas via
> `fetch` do próprio dashboard e seguem fora do escopo de CSRF de formulário
> (consistente com a decisão anterior); a proteção de token CSRF permanece
> restrita ao CRUD de `/api/casos`.

## Status

- [x] CSRF nos endpoints de escrita do admin (`/api/casos*`)
- [x] Security headers em todas as respostas
- [x] CSP ajustada às origens reais (sem quebrar grafo/charts/fontes)
- [x] `Flask-WTF` adicionado a `requirements-web.txt`
- [x] Auditoria das demais entradas documentada
