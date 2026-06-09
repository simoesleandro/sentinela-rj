"""CRUD de watchlists — critérios de monitoramento configuráveis."""
from __future__ import annotations

import sqlite3
from typing import Any


class WatchlistError(ValueError):
    """Erro de validação em watchlist."""


def _validar_criterios(
    fornecedor_ni: str | None,
    orgao_cnpj: str | None,
    palavra_chave_objeto: str | None,
) -> None:
    palavra = (palavra_chave_objeto or "").strip()
    if not fornecedor_ni and not orgao_cnpj and not palavra:
        raise WatchlistError(
            "Informe ao menos um critério: fornecedor_ni, orgao_cnpj ou palavra_chave_objeto."
        )


def listar_watchlists(conn: sqlite3.Connection, apenas_ativas: bool = False) -> list[dict]:
    sql = "SELECT * FROM watchlists"
    if apenas_ativas:
        sql += " WHERE ativo = 1"
    sql += " ORDER BY id"
    rows = conn.execute(sql).fetchall()
    return [dict(row) for row in rows]


def obter_watchlist(conn: sqlite3.Connection, watchlist_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM watchlists WHERE id = ?",
        (watchlist_id,),
    ).fetchone()
    return dict(row) if row else None


def criar_watchlist(
    conn: sqlite3.Connection,
    *,
    rotulo: str,
    fornecedor_ni: str | None = None,
    orgao_cnpj: str | None = None,
    palavra_chave_objeto: str | None = None,
    ativo: int = 1,
) -> dict:
    rotulo_limpo = rotulo.strip()
    if not rotulo_limpo:
        raise WatchlistError("Campo rotulo é obrigatório.")
    _validar_criterios(fornecedor_ni, orgao_cnpj, palavra_chave_objeto)
    palavra = (palavra_chave_objeto or "").strip() or None
    cur = conn.execute(
        """
        INSERT INTO watchlists (
            fornecedor_ni, orgao_cnpj, palavra_chave_objeto, rotulo, ativo
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (fornecedor_ni, orgao_cnpj, palavra, rotulo_limpo, int(ativo)),
    )
    conn.commit()
    item = obter_watchlist(conn, int(cur.lastrowid))
    assert item is not None
    return item


def atualizar_watchlist(
    conn: sqlite3.Connection,
    watchlist_id: int,
    campos: dict[str, Any],
) -> dict:
    existente = obter_watchlist(conn, watchlist_id)
    if existente is None:
        raise WatchlistError(f"Watchlist {watchlist_id} não encontrada.")

    fornecedor = campos.get("fornecedor_ni", existente["fornecedor_ni"])
    orgao = campos.get("orgao_cnpj", existente["orgao_cnpj"])
    palavra_raw = campos.get("palavra_chave_objeto", existente["palavra_chave_objeto"])
    palavra = (palavra_raw or "").strip() or None
    rotulo = (campos.get("rotulo") or existente["rotulo"]).strip()
    ativo = int(campos.get("ativo", existente["ativo"]))

    if not rotulo:
        raise WatchlistError("Campo rotulo é obrigatório.")
    _validar_criterios(fornecedor, orgao, palavra)

    conn.execute(
        """
        UPDATE watchlists
        SET fornecedor_ni = ?, orgao_cnpj = ?, palavra_chave_objeto = ?,
            rotulo = ?, ativo = ?
        WHERE id = ?
        """,
        (fornecedor, orgao, palavra, rotulo, ativo, watchlist_id),
    )
    conn.commit()
    atualizada = obter_watchlist(conn, watchlist_id)
    assert atualizada is not None
    return atualizada


def desativar_watchlist(conn: sqlite3.Connection, watchlist_id: int) -> None:
    if obter_watchlist(conn, watchlist_id) is None:
        raise WatchlistError(f"Watchlist {watchlist_id} não encontrada.")
    conn.execute("UPDATE watchlists SET ativo = 0 WHERE id = ?", (watchlist_id,))
    conn.commit()
