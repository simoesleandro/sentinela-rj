"""Flask REST API — Sentinela RJ dashboard + triagem de alertas.

Este módulo é o núcleo da aplicação: cria o app, configura CSRF/CORS/headers
de segurança e expõe os recursos compartilhados (get_db, filtros de município,
score SQL, conexão do Postgres de conflitos). As rotas vivem em blueprints por
domínio no pacote routes/ (alertas, fornecedores, painel, watchlists,
conflitos, casos, exportação), registrados no fim deste arquivo.
"""
import functools
import os
import sqlite3
import sys

# Executado como script (python web_app.py), este arquivo vira o módulo
# "__main__". Os blueprints fazem `import web_app` para resolver os recursos
# compartilhados em tempo de request — o alias abaixo garante que eles
# enxerguem ESTA instância do módulo, e não uma segunda cópia importada.
if __name__ == "__main__":
    sys.modules.setdefault("web_app", sys.modules[__name__])

from flask import Flask, jsonify, request, render_template, redirect
from flask_wtf.csrf import CSRFProtect, CSRFError
from dotenv import load_dotenv

load_dotenv()

from analise.score_composto import score_composto_sql
from db.conexao import DB_PATH, aplicar_migracoes

app = Flask(__name__, static_folder='static', template_folder='templates')

# Reexportados aqui de propósito: os blueprints (e os testes, via monkeypatch
# de web_app.checar_cota_ia / web_app.registrar_consumo_ia) resolvem esses
# nomes como atributos deste módulo em tempo de request.
from web_auth import checar_cota_ia, registrar_consumo_ia, requer_admin, requer_login, init_auth

init_auth(app)

# ---------------------------------------------------------------------------
# Proteção CSRF
# ---------------------------------------------------------------------------
# A app é uma SPA que conversa via fetch/JSON. As APIs de leitura e os endpoints
# de IA usam autenticação própria por sessão e ficam fora do CSRF. Só os
# endpoints de ESCRITA do admin (CRUD de /api/casos) — disparados de um
# formulário no navegador com cookie de sessão — recebem validação de token.
#
# WTF_CSRF_CHECK_DEFAULT = False desliga a proteção automática global; aplicamos
# explicitamente via @csrf_required nos endpoints que precisam. O token é
# exposto à página admin por csrf_token() (Jinja) e enviado no header
# X-CSRFToken pelos fetch().
app.config["WTF_CSRF_CHECK_DEFAULT"] = False
app.config.setdefault("WTF_CSRF_TIME_LIMIT", None)  # token válido enquanto a sessão durar
csrf = CSRFProtect(app)


@app.errorhandler(CSRFError)
def _handle_csrf_error(exc: CSRFError):
    return jsonify({"error": "Token CSRF inválido ou ausente.", "csrf": True}), 400


def csrf_required(fn):
    """Valida o token CSRF (campo csrf_token ou header X-CSRFToken) antes da view."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        csrf.protect()  # levanta CSRFError (400) se o token for inválido/ausente
        return fn(*args, **kwargs)

    return wrapper


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "app": "sentinela-rj"}), 200


# Mesma fórmula de calcular_score_composto, gerada a partir das mesmas
# constantes (fonte única em analise/score_composto.py).
_SCORE_SQL = score_composto_sql("a")
_migracoes_aplicadas = False


def get_db() -> sqlite3.Connection:
    global _migracoes_aplicadas
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if not _migracoes_aplicadas and DB_PATH.exists():
        aplicar_migracoes(conn)
        _migracoes_aplicadas = True
    return conn

@app.route('/dashboard')
def dashboard():
    return render_template('index.html')

@app.route('/fornecedor/<path:fornecedor_ni>')
def fornecedor_page(fornecedor_ni: str):
    # aceita CNPJ formatado (42.498.733/0001-90) e redireciona para forma canônica
    ni = fornecedor_ni.replace('.', '').replace('/', '').replace('-', '')
    if ni != fornecedor_ni:
        return redirect(f'/fornecedor/{ni}', 301)
    return render_template('fornecedor.html', ni=ni)

_CORS_METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


@app.after_request
def add_cors(response):
    # Só a leitura é exposta cross-origin (reuso de dados abertos). Escrita
    # (POST/PATCH/DELETE) fica same-origin — protegida por sessão e CSRF. O SPA
    # é servido pela própria app, então não depende de CORS para funcionar.
    if request.method in _CORS_METODOS_SEGUROS:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken"
    return response


# Content-Security-Policy — libera apenas as origens efetivamente usadas pelos
# templates: Chart.js (cdn.jsdelivr.net), vis-network (unpkg.com), Google Fonts.
# 'unsafe-inline' é necessário para os handlers onclick e <style> inline.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = _CSP
    return response


@app.route("/")
def index():
    return "Sentinela RJ API - OK", 200


# ---------------------------------------------------------------------------
# Município — filtro do dashboard (compartilhado pelos blueprints)
# ---------------------------------------------------------------------------

def _municipio_ibge_request() -> str | None:
    raw = (request.args.get("municipio_ibge") or "").strip()
    return raw if raw else None


def _aplicar_filtro_municipio(
    conditions: list[str],
    params: list,
    ibge: str | None,
    alias: str = "o",
) -> None:
    from db.filtro_municipio import filtro_municipio_sql

    clause, filtro_params = filtro_municipio_sql(ibge, alias=alias)
    if clause:
        conditions.append(clause)
        params.extend(filtro_params)


# ---------------------------------------------------------------------------
# Conexão Postgres — conflito de interesse (compartilhada pelos blueprints)
# ---------------------------------------------------------------------------

def get_conflito_conn():
    """Conexão Postgres/Supabase para candidatos_conflito_interesse.

    Cursor padrão (linhas como tupla), não RealDictCursor — é o que
    ConflitoTriagemRepository espera (acesso posicional, ex.: row[0]).
    """
    import psycopg2

    dsn = os.environ.get("CONFLITO_INTERESSE_DATABASE_URL")
    if not dsn:
        raise RuntimeError("CONFLITO_INTERESSE_DATABASE_URL não configurada.")
    return psycopg2.connect(dsn)


# ---------------------------------------------------------------------------
# Blueprints — um módulo por domínio (routes/)
# ---------------------------------------------------------------------------
# Importados no fim de propósito: os módulos fazem `import web_app` e precisam
# que todos os recursos compartilhados acima já estejam definidos.

from routes.alertas import bp as alertas_bp
from routes.casos import bp as casos_bp
from routes.conflitos import bp as conflitos_bp
from routes.exportacao import bp as exportacao_bp
from routes.fornecedores import bp as fornecedores_bp
from routes.painel import bp as painel_bp
from routes.watchlists import bp as watchlists_bp

app.register_blueprint(alertas_bp)
app.register_blueprint(casos_bp)
app.register_blueprint(conflitos_bp)
app.register_blueprint(exportacao_bp)
app.register_blueprint(fornecedores_bp)
app.register_blueprint(painel_bp)
app.register_blueprint(watchlists_bp)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from waitress import serve

    port = int(os.environ.get("PORT", 5055))
    serve(app, host="0.0.0.0", port=port)
