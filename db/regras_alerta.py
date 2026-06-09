"""Regras de alerta — filtro de notificações e CRUD leve."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

SEV_ORDEM: dict[str, int] = {"baixa": 1, "media": 2, "alta": 3}
SEVERIDADES_VALIDAS = frozenset(SEV_ORDEM)


class RegraAlertaError(ValueError):
    """Erro de validação em regra de alerta."""


@dataclass(frozen=True)
class RegraAlerta:
    id: int
    tipo: str | None
    severidade_min: str
    valor_min: float
    ativo: int


def _row_para_regra(row: sqlite3.Row) -> RegraAlerta:
    return RegraAlerta(
        id=int(row["id"]),
        tipo=row["tipo"],
        severidade_min=row["severidade_min"],
        valor_min=float(row["valor_min"]),
        ativo=int(row["ativo"]),
    )


def _validar_severidade(severidade: str) -> str:
    sev = severidade.strip().lower()
    if sev not in SEVERIDADES_VALIDAS:
        raise RegraAlertaError(
            f"severidade_min inválida: {severidade!r} (use baixa, media ou alta)."
        )
    return sev


def carregar_regras_ativas(conn: sqlite3.Connection) -> list[RegraAlerta]:
    rows = conn.execute(
        """
        SELECT id, tipo, severidade_min, valor_min, ativo
        FROM regras_alerta
        WHERE ativo = 1
        ORDER BY id
        """
    ).fetchall()
    return [_row_para_regra(row) for row in rows]


def alerta_atende_regra(
    alerta: dict[str, Any],
    valor_contrato: float,
    regra: RegraAlerta,
) -> bool:
    tipo_alerta = alerta.get("tipo")
    if regra.tipo and regra.tipo != tipo_alerta:
        return False
    severidade = (alerta.get("severidade") or "baixa").lower()
    if SEV_ORDEM.get(severidade, 0) < SEV_ORDEM.get(regra.severidade_min, 0):
        return False
    valor_ref = alerta.get("valor_referencia")
    valor_efetivo = float(valor_ref if valor_ref is not None else valor_contrato or 0)
    return valor_efetivo >= regra.valor_min


def _carregar_alertas_com_valor(
    conn: sqlite3.Connection,
    alerta_ids: list[int],
) -> list[dict[str, Any]]:
    if not alerta_ids:
        return []
    placeholders = ", ".join("?" * len(alerta_ids))
    rows = conn.execute(
        f"""
        SELECT a.id, a.tipo, a.severidade, a.valor_referencia,
               COALESCE(c.valor_global, 0) AS valor_contrato
        FROM alertas a
        LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
        WHERE a.id IN ({placeholders})
        """,
        alerta_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def filtrar_para_notificacao(
    conn: sqlite3.Connection,
    alerta_ids: list[int],
) -> list[int]:
    """Retorna IDs de alertas novos que qualificam para notificação."""
    if not alerta_ids:
        return []
    regras = carregar_regras_ativas(conn)
    alertas = _carregar_alertas_com_valor(conn, alerta_ids)
    if not regras:
        return [
            int(a["id"])
            for a in alertas
            if (a.get("severidade") or "").lower() == "alta"
        ]
    qualificados: list[int] = []
    for alerta in alertas:
        valor_contrato = float(alerta.get("valor_contrato") or 0)
        if any(
            alerta_atende_regra(alerta, valor_contrato, regra) for regra in regras
        ):
            qualificados.append(int(alerta["id"]))
    return qualificados


def listar_regras(conn: sqlite3.Connection, apenas_ativas: bool = False) -> list[dict]:
    sql = "SELECT * FROM regras_alerta"
    if apenas_ativas:
        sql += " WHERE ativo = 1"
    sql += " ORDER BY id"
    rows = conn.execute(sql).fetchall()
    return [dict(row) for row in rows]


def obter_regra(conn: sqlite3.Connection, regra_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM regras_alerta WHERE id = ?",
        (regra_id,),
    ).fetchone()
    return dict(row) if row else None


def criar_regra(
    conn: sqlite3.Connection,
    *,
    tipo: str | None,
    severidade_min: str,
    valor_min: float = 0.0,
    ativo: int = 1,
) -> dict:
    sev = _validar_severidade(severidade_min)
    cur = conn.execute(
        """
        INSERT INTO regras_alerta (tipo, severidade_min, valor_min, ativo)
        VALUES (?, ?, ?, ?)
        """,
        (tipo, sev, float(valor_min), int(ativo)),
    )
    conn.commit()
    regra = obter_regra(conn, int(cur.lastrowid))
    assert regra is not None
    return regra


def atualizar_regra(
    conn: sqlite3.Connection,
    regra_id: int,
    *,
    tipo: str | None = ...,
    severidade_min: str | None = None,
    valor_min: float | None = None,
    ativo: int | None = None,
) -> dict:
    existente = obter_regra(conn, regra_id)
    if existente is None:
        raise RegraAlertaError(f"Regra {regra_id} não encontrada.")

    novo_tipo = existente["tipo"] if tipo is ... else tipo
    novo_sev = (
        _validar_severidade(severidade_min)
        if severidade_min is not None
        else existente["severidade_min"]
    )
    novo_valor = float(valor_min) if valor_min is not None else existente["valor_min"]
    novo_ativo = int(ativo) if ativo is not None else existente["ativo"]

    conn.execute(
        """
        UPDATE regras_alerta
        SET tipo = ?, severidade_min = ?, valor_min = ?, ativo = ?
        WHERE id = ?
        """,
        (novo_tipo, novo_sev, novo_valor, novo_ativo, regra_id),
    )
    conn.commit()
    atualizada = obter_regra(conn, regra_id)
    assert atualizada is not None
    return atualizada


def desativar_regra(conn: sqlite3.Connection, regra_id: int) -> None:
    if obter_regra(conn, regra_id) is None:
        raise RegraAlertaError(f"Regra {regra_id} não encontrada.")
    conn.execute("UPDATE regras_alerta SET ativo = 0 WHERE id = ?", (regra_id,))
    conn.commit()
