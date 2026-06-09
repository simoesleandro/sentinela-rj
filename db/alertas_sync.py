"""Persistência incremental de alertas — preserva triagem entre re-análises."""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Literal

from analisador.engine import AnomaliaResult

ChaveAlerta = tuple[str | None, str, int | None]
EscopoRemocao = Literal["detectores", "watchlist", "todos"]

_RE_WATCHLIST_ID = re.compile(r"watchlist_id=(\d+)")


def _extrair_watchlist_id(anomalia: AnomaliaResult) -> int | None:
    wl_id = anomalia.metricas.get("watchlist_id")
    if wl_id is not None:
        return int(wl_id)
    return None


def _parse_watchlist_id_metodologia(metodologia: str | None) -> int | None:
    if not metodologia:
        return None
    match = _RE_WATCHLIST_ID.search(metodologia)
    if not match:
        return None
    return int(match.group(1))


def _chave(
    pncp_id: str | None,
    tipo: str,
    watchlist_id: int | None = None,
) -> ChaveAlerta:
    wl = watchlist_id if tipo == "watchlist_match" else None
    return (pncp_id, tipo, wl)


def _chave_de_anomalia(pncp_id: str | None, anomalia: AnomaliaResult) -> ChaveAlerta:
    return _chave(pncp_id, anomalia.tipo, _extrair_watchlist_id(anomalia))


def _mapa_existentes(conn: sqlite3.Connection) -> dict[ChaveAlerta, int]:
    rows = conn.execute(
        "SELECT id, numero_controle_pncp, tipo, metodologia FROM alertas"
    ).fetchall()
    mapa: dict[ChaveAlerta, int] = {}
    for row in rows:
        tipo = row[2]
        wl_id = (
            _parse_watchlist_id_metodologia(row[3])
            if tipo == "watchlist_match"
            else None
        )
        mapa[(row[1], tipo, wl_id)] = int(row[0])
    return mapa


def _tipo_no_escopo_remocao(tipo: str, escopo: EscopoRemocao) -> bool:
    if escopo == "todos":
        return True
    if escopo == "watchlist":
        return tipo == "watchlist_match"
    return tipo != "watchlist_match"


def _atualizar_alerta(
    conn: sqlite3.Connection,
    alerta_id: int,
    anomalia: AnomaliaResult,
) -> None:
    conn.execute(
        """
        UPDATE alertas
        SET severidade = ?, score = ?, descricao = ?,
            metodologia = ?, valor_referencia = ?
        WHERE id = ?
        """,
        (
            anomalia.severidade,
            anomalia.score,
            anomalia.descricao,
            anomalia.metodologia,
            anomalia.valor_referencia,
            alerta_id,
        ),
    )


def _inserir_alerta(
    conn: sqlite3.Connection,
    anomalia: AnomaliaResult,
    pncp_id: str | None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO alertas (
            numero_controle_pncp, tipo, severidade, score,
            descricao, metodologia, valor_referencia, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'aberto')
        """,
        (
            pncp_id,
            anomalia.tipo,
            anomalia.severidade,
            anomalia.score,
            anomalia.descricao,
            anomalia.metodologia,
            anomalia.valor_referencia,
        ),
    )
    return int(cur.lastrowid)


def _remover_obsoletos(
    conn: sqlite3.Connection,
    existentes: dict[ChaveAlerta, int],
    novas_chaves: set[ChaveAlerta],
    escopo: EscopoRemocao,
) -> int:
    removidos = 0
    for chave, alerta_id in list(existentes.items()):
        if chave in novas_chaves:
            continue
        tipo = chave[1]
        if not _tipo_no_escopo_remocao(tipo, escopo):
            continue
        row = conn.execute(
            "SELECT status FROM alertas WHERE id = ?",
            (alerta_id,),
        ).fetchone()
        if row is None:
            continue
        status = (row[0] or "aberto").strip().lower()
        historico = conn.execute(
            "SELECT COUNT(*) FROM alertas_historico WHERE alerta_id = ?",
            (alerta_id,),
        ).fetchone()[0]
        if status != "aberto" or historico > 0:
            continue
        conn.execute("DELETE FROM alertas WHERE id = ?", (alerta_id,))
        removidos += 1
    return removidos


def _inferir_escopo(anomalias: list[AnomaliaResult]) -> EscopoRemocao:
    if not anomalias:
        return "detectores"
    tipos = {a.tipo for a in anomalias}
    if tipos == {"watchlist_match"}:
        return "watchlist"
    if "watchlist_match" in tipos:
        return "todos"
    return "detectores"


def sincronizar_alertas(
    conn: sqlite3.Connection,
    anomalias: list[AnomaliaResult],
    *,
    escopo_remocao: EscopoRemocao | None = None,
) -> dict[str, Any]:
    escopo = escopo_remocao or _inferir_escopo(anomalias)
    existentes = _mapa_existentes(conn)
    novas_chaves: set[ChaveAlerta] = set()
    inseridos = atualizados = 0
    ids_inseridos: list[int] = []
    ids_inseridos_alta: list[int] = []

    for anomalia in anomalias:
        for pncp_id in anomalia.contratos or [None]:
            chave = _chave_de_anomalia(pncp_id, anomalia)
            novas_chaves.add(chave)
            alerta_id = existentes.get(chave)
            if alerta_id:
                _atualizar_alerta(conn, alerta_id, anomalia)
                atualizados += 1
            else:
                novo_id = _inserir_alerta(conn, anomalia, pncp_id)
                existentes[chave] = novo_id
                ids_inseridos.append(novo_id)
                if anomalia.severidade == "alta":
                    ids_inseridos_alta.append(novo_id)
                inseridos += 1

    removidos = _remover_obsoletos(conn, existentes, novas_chaves, escopo)
    conn.commit()
    return {
        "inseridos": inseridos,
        "atualizados": atualizados,
        "removidos": removidos,
        "total": len(novas_chaves),
        "ids_inseridos": ids_inseridos,
        "ids_inseridos_alta": ids_inseridos_alta,
    }


def snapshot_ids_alta(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute(
        "SELECT id FROM alertas WHERE severidade = 'alta'"
    ).fetchall()
    return {int(r[0]) for r in rows}


def carregar_alertas(
    conn: sqlite3.Connection,
    ids: list[int],
) -> list[dict[str, Any]]:
    if not ids:
        return []
    placeholders = ", ".join("?" * len(ids))
    rows = conn.execute(
        f"""
        SELECT a.id, a.tipo, a.severidade, a.score, a.status,
               a.descricao, a.valor_referencia, a.numero_controle_pncp,
               a.narrativa_ia,
               COALESCE(f.razao_social, '') AS fornecedor
        FROM alertas a
        LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
        LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        WHERE a.id IN ({placeholders})
        ORDER BY a.score DESC, a.id DESC
        """,
        ids,
    ).fetchall()
    return [dict(r) for r in rows]
