"""Autenticação por sessão + cota diária de IA para o Sentinela RJ.

Protege apenas os endpoints que consomem a API de IA (Gemini/Groq) e a área
admin. Todo o resto do dashboard continua público (somente leitura).

- Visitante (sem login): navega tudo e lê narrativas já geradas.
- Usuário cadastrado: até ``SENTINELA_IA_LIMITE_DIARIO`` investigações de IA/dia.
- Admin (definido via Fly secrets): investigações ilimitadas + CRUD de casos.
"""
import os
import secrets
import sqlite3
import functools
import threading
import time

from flask import jsonify, render_template, request, session

from db import auth as auth_db
from db.conexao import DB_PATH, aplicar_migracoes

IA_LIMITE_DIARIO = int(os.getenv("SENTINELA_IA_LIMITE_DIARIO", "3"))

# ---------------------------------------------------------------------------
# Rate limiting dos endpoints de autenticação (anti brute-force / spam)
# ---------------------------------------------------------------------------
# Janela deslizante em memória por IP. Suficiente para o deploy single-instance
# (Fly.io + waitress); reinicia com o processo. Ajustável por env.
_AUTH_RATE_MAX = int(os.getenv("SENTINELA_AUTH_RATE_MAX", "10"))
_AUTH_RATE_JANELA_S = int(os.getenv("SENTINELA_AUTH_RATE_JANELA_S", "300"))
_AUTH_RATE_LOCK = threading.Lock()
_AUTH_RATE_HITS: dict[str, list[float]] = {}


def _cliente_ip() -> str:
    fwd = request.headers.get("X-Forwarded-For", "").strip()
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "desconhecido"


def _rate_limit_excedido(chave: str) -> bool:
    """Registra 1 tentativa e diz se a janela estourou o limite."""
    agora = time.time()
    with _AUTH_RATE_LOCK:
        if len(_AUTH_RATE_HITS) > 5000:  # poda defensiva contra crescimento sob ataque
            _AUTH_RATE_HITS.clear()
        hits = [t for t in _AUTH_RATE_HITS.get(chave, []) if agora - t < _AUTH_RATE_JANELA_S]
        hits.append(agora)
        _AUTH_RATE_HITS[chave] = hits
        return len(hits) > _AUTH_RATE_MAX


def _erro_rate_limit():
    return (
        jsonify({
            "error": "Muitas tentativas seguidas. Aguarde alguns minutos e tente de novo.",
            "auth": "rate_limit",
        }),
        429,
    )


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def usuario_atual(conn: sqlite3.Connection) -> dict | None:
    uid = session.get("usuario_id")
    if not uid:
        return None
    return auth_db.obter_usuario(conn, uid)


def _erro_login():
    return jsonify({"error": "Faça login para usar a investigação por IA.", "auth": "login"}), 401


def _erro_quota():
    return (
        jsonify({
            "error": (
                f"Você atingiu o limite de {IA_LIMITE_DIARIO} investigações de IA por dia. "
                "Tente novamente amanhã."
            ),
            "auth": "quota",
            "limite": IA_LIMITE_DIARIO,
        }),
        429,
    )


def _erro_verificar():
    return (
        jsonify({
            "error": "Confirme seu email para liberar as investigações por IA.",
            "auth": "verificar",
        }),
        403,
    )


def checar_cota_ia():
    """Valida login, confirmação de email e cota ANTES de chamar a IA.

    Retorna ``(usuario, None)`` quando liberado, ou ``(None, resposta_erro)``.
    O consumo só é contabilizado depois, via :func:`registrar_consumo_ia`.
    """
    conn = _conn()
    try:
        usuario = usuario_atual(conn)
        if usuario is None:
            return None, _erro_login()
        if not usuario.get("is_admin"):
            if not usuario.get("email_verificado"):
                return None, _erro_verificar()
            if auth_db.contar_uso_hoje(conn, usuario["id"]) >= IA_LIMITE_DIARIO:
                return None, _erro_quota()
        return usuario, None
    finally:
        conn.close()


def registrar_consumo_ia(usuario: dict | None, endpoint: str) -> None:
    """Contabiliza 1 uso de IA. Admin não consome cota."""
    if not usuario or usuario.get("is_admin"):
        return
    conn = _conn()
    try:
        auth_db.registrar_uso(conn, usuario["id"], endpoint)
    finally:
        conn.close()


_METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def requer_login(fn):
    """Decorator: exige sessão autenticada nos métodos de ESCRITA.

    Métodos seguros (GET/HEAD/OPTIONS) passam direto — o dashboard continua
    público para leitura. Use em views que misturam leitura pública e escrita
    (ex.: PATCH de triagem, CRUD de watchlists/regras) para proteger só as
    mutações sem bloquear o GET.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method not in _METODOS_SEGUROS:
            conn = _conn()
            try:
                usuario = usuario_atual(conn)
            finally:
                conn.close()
            if usuario is None:
                return _erro_login()
        return fn(*args, **kwargs)

    return wrapper


def requer_admin(fn):
    """Decorator: bloqueia o endpoint para não-admins."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        conn = _conn()
        try:
            usuario = usuario_atual(conn)
        finally:
            conn.close()
        if usuario is None:
            return _erro_login()
        if not usuario.get("is_admin"):
            return jsonify({"error": "Acesso restrito ao administrador."}), 403
        return fn(*args, **kwargs)

    return wrapper


def _payload_sessao(conn: sqlite3.Connection) -> dict:
    usuario = usuario_atual(conn)
    if usuario is None:
        return {"usuario": None, "ia": {"limite": IA_LIMITE_DIARIO}}
    if usuario.get("is_admin"):
        ia = {"limite": None, "usados_hoje": 0, "restante": None, "ilimitado": True}
    elif not usuario.get("email_verificado"):
        ia = {"limite": IA_LIMITE_DIARIO, "usados_hoje": 0,
              "restante": 0, "ilimitado": False, "verificar": True}
    else:
        usados = auth_db.contar_uso_hoje(conn, usuario["id"])
        ia = {
            "limite": IA_LIMITE_DIARIO,
            "usados_hoje": usados,
            "restante": max(0, IA_LIMITE_DIARIO - usados),
            "ilimitado": False,
        }
    return {"usuario": usuario, "ia": ia}


def _base_url() -> str:
    """URL base para montar links de confirmação (honra proxy do Fly/https)."""
    base = os.getenv("SENTINELA_BASE_URL", "").strip()
    if base:
        return base.rstrip("/")
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    return f"{proto}://{request.host}"


def _enviar_email_confirmacao(usuario: dict) -> dict:
    """Envia o email de confirmação. Retorna {'enviado': bool, 'erro': str|None}."""
    import email_envio

    token = usuario.get("token_verificacao")
    if not token:
        return {"enviado": False, "erro": None}
    link = f"{_base_url()}/verificar?token={token}"
    try:
        enviado = email_envio.enviar_confirmacao(
            usuario["email"], usuario.get("nome"), link
        )
        return {"enviado": enviado, "erro": None}
    except email_envio.EmailError as exc:
        return {"enviado": False, "erro": str(exc)}


def init_auth(app) -> None:
    """Configura SECRET_KEY, faz bootstrap do admin e registra as rotas."""
    secret = os.getenv("SENTINELA_SECRET_KEY") or os.getenv("SECRET_KEY")
    if not secret:
        secret = secrets.token_hex(32)
        print(
            "[auth] AVISO: SENTINELA_SECRET_KEY não definida — usando chave efêmera. "
            "As sessões serão invalidadas a cada restart. "
            "Defina via: fly secrets set SENTINELA_SECRET_KEY=...",
            flush=True,
        )
    app.secret_key = secret

    # Garante tabelas + admin no startup (idempotente). Só roda se o banco existe;
    # caso contrário as migrações rodam sob demanda no primeiro request.
    if DB_PATH.exists():
        conn = _conn()
        try:
            aplicar_migracoes(conn)
            admin_email = os.getenv("SENTINELA_ADMIN_EMAIL", "").strip()
            admin_senha = os.getenv("SENTINELA_ADMIN_SENHA", "")
            if admin_email and admin_senha:
                auth_db.garantir_admin(conn, admin_email, admin_senha)
                print(f"[auth] Admin garantido: {admin_email.lower()}", flush=True)
            else:
                print(
                    "[auth] SENTINELA_ADMIN_EMAIL/SENTINELA_ADMIN_SENHA não definidos — "
                    "nenhum admin criado.",
                    flush=True,
                )
        finally:
            conn.close()

    @app.route("/login")
    def login_page():
        return render_template("login.html")

    @app.route("/api/auth/me", methods=["GET"])
    def auth_me():
        conn = _conn()
        try:
            return jsonify(_payload_sessao(conn))
        finally:
            conn.close()

    @app.route("/api/auth/registrar", methods=["POST"])
    def auth_registrar():
        if _rate_limit_excedido(f"registrar:{_cliente_ip()}"):
            return _erro_rate_limit()
        body = request.get_json(silent=True) or {}
        conn = _conn()
        try:
            aplicar_migracoes(conn)
            usuario = auth_db.criar_usuario(
                conn,
                email=body.get("email", ""),
                senha=body.get("senha", ""),
                nome=body.get("nome"),
            )
            envio = _enviar_email_confirmacao(usuario)
            session["usuario_id"] = usuario["id"]
            session.permanent = True
            payload = _payload_sessao(conn)
            payload["email_enviado"] = envio["enviado"]
            payload["email_erro"] = envio["erro"]
            return jsonify(payload), 201
        except auth_db.AuthError as exc:
            return jsonify({"error": str(exc)}), 422
        finally:
            conn.close()

    @app.route("/verificar", methods=["GET"])
    def verificar_page():
        token = request.args.get("token", "")
        conn = _conn()
        try:
            try:
                usuario = auth_db.verificar_email(conn, token)
                sucesso, mensagem = True, "Email confirmado com sucesso!"
                # já loga a pessoa após confirmar
                session["usuario_id"] = usuario["id"]
                session.permanent = True
            except auth_db.AuthError as exc:
                sucesso, mensagem = False, str(exc)
        finally:
            conn.close()
        return render_template(
            "verificar.html", sucesso=sucesso, mensagem=mensagem
        )

    @app.route("/api/auth/reenviar", methods=["POST"])
    def auth_reenviar():
        conn = _conn()
        try:
            usuario = usuario_atual(conn)
            if usuario is None:
                return _erro_login()
            if usuario.get("email_verificado"):
                return jsonify({"ok": True, "ja_verificado": True})
            token = auth_db.gerar_novo_token(conn, usuario["id"])
            usuario["token_verificacao"] = token
            envio = _enviar_email_confirmacao(usuario)
            return jsonify({
                "ok": True,
                "email_enviado": envio["enviado"],
                "email_erro": envio["erro"],
            })
        finally:
            conn.close()

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        if _rate_limit_excedido(f"login:{_cliente_ip()}"):
            return _erro_rate_limit()
        body = request.get_json(silent=True) or {}
        conn = _conn()
        try:
            usuario = auth_db.autenticar(conn, body.get("email", ""), body.get("senha", ""))
            session["usuario_id"] = usuario["id"]
            session.permanent = True
            return jsonify(_payload_sessao(conn))
        except auth_db.AuthError as exc:
            return jsonify({"error": str(exc)}), 401
        finally:
            conn.close()

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        session.clear()
        return jsonify({"ok": True})
