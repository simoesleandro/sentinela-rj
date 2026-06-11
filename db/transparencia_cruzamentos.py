"""Consultas de cruzamento PNCP × Transparência RJ para a UI."""
from __future__ import annotations

import sqlite3


def listar_empenhos_vinculados(
    conn: sqlite3.Connection,
    numero_controle_pncp: str | None,
) -> list[dict]:
    """Retorna empenhos RJ vinculados ao contrato PNCP, ordenados por score."""
    pncp = (numero_controle_pncp or "").strip()
    if not pncp:
        return []
    rows = conn.execute(
        """
        SELECT cr.score, cr.detectado_em,
               l.valor, l.data_lancamento, l.descricao,
               l.orgao, l.documento, l.fornecedor_ni
        FROM transparencia_rj_cruzamentos cr
        JOIN transparencia_rj_lancamentos l ON l.id = cr.lancamento_id
        WHERE cr.numero_controle_pncp = ?
        ORDER BY cr.score DESC, l.data_lancamento DESC
        """,
        (pncp,),
    ).fetchall()
    return [dict(row) for row in rows]
