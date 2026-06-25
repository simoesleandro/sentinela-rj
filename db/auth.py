"""Camada de dados de autenticação — usuários, login e cota diária de IA.

Usa sessões assinadas do Flask (cookie) + hash de senha do Werkzeug.
A cota diária de IA é contada pela tabela ``ia_consumo`` (1 linha por chamada).
"""
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

TOKEN_VALIDADE_HORAS = 24


class AuthError(Exception):
    """Erro de validação/credencial de autenticação."""


def _normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def _novo_token() -> tuple[str, str]:
    """Gera (token, expira_em_iso) para confirmação de email."""
    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(hours=TOKEN_VALIDADE_HORAS)
    return token, expira.isoformat()


def criar_usuario(
    conn: sqlite3.Connection,
    email: str,
    senha: str,
    nome: str | None = None,
    is_admin: int = 0,
) -> dict:
    email = _normalizar_email(email)
    if "@" not in email or "." not in email.split("@")[-1]:
        raise AuthError("Informe um email válido.")
    if len(senha or "") < 6:
        raise AuthError("A senha deve ter ao menos 6 caracteres.")
    # Admin já nasce verificado; usuário comum recebe token de confirmação.
    token, expira = (None, None) if is_admin else _novo_token()
    try:
        cur = conn.execute(
            "INSERT INTO usuarios "
            "(email, nome, senha_hash, is_admin, email_verificado, "
            "token_verificacao, token_expira_em) VALUES (?,?,?,?,?,?,?)",
            (
                email,
                (nome or "").strip() or None,
                generate_password_hash(senha),
                int(is_admin),
                1 if is_admin else 0,
                token,
                expira,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise AuthError("Este email já está cadastrado.")
    usuario = obter_usuario(conn, cur.lastrowid)
    usuario["token_verificacao"] = token  # usado para montar o link de confirmação
    return usuario


def autenticar(conn: sqlite3.Connection, email: str, senha: str) -> dict:
    row = conn.execute(
        "SELECT id, email, nome, senha_hash, is_admin, email_verificado "
        "FROM usuarios WHERE email = ?",
        (_normalizar_email(email),),
    ).fetchone()
    if row is None or not check_password_hash(row["senha_hash"], senha or ""):
        raise AuthError("Email ou senha incorretos.")
    return {
        "id": row["id"],
        "email": row["email"],
        "nome": row["nome"],
        "is_admin": bool(row["is_admin"]),
        "email_verificado": bool(row["email_verificado"]),
    }


def obter_usuario(conn: sqlite3.Connection, usuario_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, email, nome, is_admin, email_verificado, criado_em "
        "FROM usuarios WHERE id = ?",
        (usuario_id,),
    ).fetchone()
    if row is None:
        return None
    dados = dict(row)
    dados["is_admin"] = bool(dados.get("is_admin"))
    dados["email_verificado"] = bool(dados.get("email_verificado"))
    return dados


def verificar_email(conn: sqlite3.Connection, token: str) -> dict:
    """Confirma o email a partir do token. Lança AuthError se inválido/expirado."""
    token = (token or "").strip()
    if not token:
        raise AuthError("Token de confirmação ausente.")
    row = conn.execute(
        "SELECT id, email_verificado, token_expira_em FROM usuarios "
        "WHERE token_verificacao = ?",
        (token,),
    ).fetchone()
    if row is None:
        raise AuthError("Link de confirmação inválido.")
    if row["email_verificado"]:
        return obter_usuario(conn, row["id"])
    expira = row["token_expira_em"]
    if expira and datetime.fromisoformat(expira) < datetime.now(timezone.utc):
        raise AuthError("Link de confirmação expirado. Solicite um novo.")
    conn.execute(
        "UPDATE usuarios SET email_verificado = 1, "
        "token_verificacao = NULL, token_expira_em = NULL WHERE id = ?",
        (row["id"],),
    )
    conn.commit()
    return obter_usuario(conn, row["id"])


def gerar_novo_token(conn: sqlite3.Connection, usuario_id: int) -> str | None:
    """Gera novo token para reenvio de confirmação. None se já verificado."""
    row = conn.execute(
        "SELECT email_verificado FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()
    if row is None or row["email_verificado"]:
        return None
    token, expira = _novo_token()
    conn.execute(
        "UPDATE usuarios SET token_verificacao = ?, token_expira_em = ? WHERE id = ?",
        (token, expira, usuario_id),
    )
    conn.commit()
    return token


def contar_uso_hoje(conn: sqlite3.Connection, usuario_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM ia_consumo "
        "WHERE usuario_id = ? AND date(criado_em) = date('now')",
        (usuario_id,),
    ).fetchone()[0]


def registrar_uso(conn: sqlite3.Connection, usuario_id: int, endpoint: str) -> None:
    conn.execute(
        "INSERT INTO ia_consumo (usuario_id, endpoint) VALUES (?, ?)",
        (usuario_id, endpoint),
    )
    conn.commit()


def garantir_admin(
    conn: sqlite3.Connection,
    email: str,
    senha: str,
    nome: str = "Administrador",
) -> None:
    """Cria (ou promove/atualiza) o usuário admin a partir das variáveis de ambiente.

    Idempotente: chamado no startup. Se o email já existe, atualiza a senha e
    garante is_admin = 1.
    """
    email = _normalizar_email(email)
    row = conn.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()
    if row is not None:
        conn.execute(
            "UPDATE usuarios SET senha_hash = ?, is_admin = 1, "
            "email_verificado = 1 WHERE id = ?",
            (generate_password_hash(senha), row["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO usuarios (email, nome, senha_hash, is_admin, email_verificado) "
            "VALUES (?,?,?,1,1)",
            (email, nome, generate_password_hash(senha)),
        )
    conn.commit()
