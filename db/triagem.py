"""Workflow de triagem de alertas — status e histórico."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from analise.motivos_descarte import MOTIVOS_FALSO_POSITIVO, formatar_nota_descarte
from db.triagem_core import (  # noqa: F401 — reexport: consumidores importam os status daqui
    STATUS_ABERTO,
    STATUS_CONFIRMADO,
    STATUS_DESCARTADO,
    STATUS_INVESTIGANDO,
    STATUS_VALIDOS,
    TriagemError,
    normalizar_status,
    status_permitidos,
    validar_transicao,
)

_FILA_STATUS = (STATUS_ABERTO, STATUS_INVESTIGANDO)


class AlertaNaoEncontradoError(LookupError):
    """Alerta inexistente."""


def listar_historico(conn: sqlite3.Connection, alerta_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, alerta_id, status_anterior, status_novo, nota, criado_em
        FROM alertas_historico
        WHERE alerta_id = ?
        ORDER BY id DESC
        """,
        (alerta_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def atualizar_status_alerta(
    conn: sqlite3.Connection,
    alerta_id: int,
    *,
    status: str,
    nota: str | None = None,
    motivo_descarte: str | None = None,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, status, notas_triagem FROM alertas WHERE id = ?",
        (alerta_id,),
    ).fetchone()
    if row is None:
        raise AlertaNaoEncontradoError(f"Alerta não encontrado: id={alerta_id}")

    anterior = normalizar_status(row["status"])
    novo = normalizar_status(status)
    nota_limpa = (nota or "").strip()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    if novo == STATUS_DESCARTADO and anterior != STATUS_DESCARTADO:
        motivo = (motivo_descarte or "").strip().lower()
        if not motivo:
            raise TriagemError(
                "Informe o motivo do descarte (feedback de falso positivo)."
            )
        if motivo not in MOTIVOS_FALSO_POSITIVO:
            raise TriagemError(
                f"Motivo inválido: '{motivo}'. "
                f"Use: {', '.join(sorted(MOTIVOS_FALSO_POSITIVO))}."
            )
        nota_limpa = formatar_nota_descarte(motivo, nota_limpa)

    if anterior == novo:
        if not nota_limpa:
            raise TriagemError(
                "Selecione um novo status ou informe uma nota para registrar."
            )
        conn.execute(
            "UPDATE alertas SET notas_triagem = ? WHERE id = ?",
            (nota_limpa, alerta_id),
        )
        conn.execute(
            """
            INSERT INTO alertas_historico (
                alerta_id, status_anterior, status_novo, nota, criado_em
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (alerta_id, anterior, novo, nota_limpa, agora),
        )
        conn.commit()
        return {
            "id": alerta_id,
            "status": novo,
            "status_anterior": anterior,
            "notas_triagem": nota_limpa,
            "status_atualizado_em": row["status_atualizado_em"],
            "historico": listar_historico(conn, alerta_id),
        }

    validar_transicao(anterior, novo)

    conn.execute(
        """
        UPDATE alertas
        SET status = ?, status_atualizado_em = ?, notas_triagem = ?
        WHERE id = ?
        """,
        (
            novo,
            agora,
            nota_limpa or row["notas_triagem"],
            alerta_id,
        ),
    )
    conn.execute(
        """
        INSERT INTO alertas_historico (
            alerta_id, status_anterior, status_novo, nota, criado_em
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (alerta_id, anterior, novo, nota_limpa or None, agora),
    )
    conn.commit()

    return {
        "id": alerta_id,
        "status": novo,
        "status_anterior": anterior,
        "notas_triagem": nota_limpa or row["notas_triagem"],
        "status_atualizado_em": agora,
        "historico": listar_historico(conn, alerta_id),
    }


def resumo_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(status), ''), ?) AS st, COUNT(*) AS n
        FROM alertas
        GROUP BY st
        """,
        (STATUS_ABERTO,),
    ).fetchall()
    base = {s: 0 for s in STATUS_VALIDOS}
    for row in rows:
        st = normalizar_status(row["st"])
        base[st] = int(row["n"])
    base["fila"] = base[STATUS_ABERTO] + base[STATUS_INVESTIGANDO]
    return base


def filtro_status_sql(param_status: str | None) -> tuple[str, list[str]]:
    if not param_status or param_status.strip().lower() in ("", "todos", "all"):
        return "", []
    valor = param_status.strip().lower()
    if valor in ("fila", "pendentes", "triagem"):
        placeholders = ", ".join("?" * len(_FILA_STATUS))
        return f"COALESCE(NULLIF(TRIM(a.status), ''), '{STATUS_ABERTO}') IN ({placeholders})", list(_FILA_STATUS)
    if valor not in STATUS_VALIDOS:
        raise TriagemError(f"Filtro de status inválido: '{param_status}'.")
    return f"COALESCE(NULLIF(TRIM(a.status), ''), '{STATUS_ABERTO}') = ?", [valor]


class AlertaTriagemRepository:
    """Implementação de TriagemRepository (db.triagem_core) para alertas de
    contrato em SQLite. Encapsula as funções acima sem alterar seu
    comportamento — usada por consumidores que querem tratar a triagem de
    forma genérica (via o Protocol); web_app.py continua chamando as funções
    livres diretamente.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def atualizar_status(
        self,
        id: int,
        novo_status: str,
        nota: str | None = None,
        motivo_descarte: str | None = None,
    ) -> None:
        atualizar_status_alerta(
            self._conn, id, status=novo_status, nota=nota, motivo_descarte=motivo_descarte
        )

    def registrar_historico(
        self,
        id: int,
        status_anterior: str,
        status_novo: str,
        nota: str | None = None,
    ) -> None:
        """Insere uma linha de histórico avulsa, fora do fluxo de
        atualizar_status (que já grava histórico atomicamente junto com a
        mudança de status)."""
        agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._conn.execute(
            """
            INSERT INTO alertas_historico (
                alerta_id, status_anterior, status_novo, nota, criado_em
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (id, status_anterior, status_novo, nota, agora),
        )
        self._conn.commit()

    def resumo_status(self) -> dict[str, int]:
        return resumo_status(self._conn)
