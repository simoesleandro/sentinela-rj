"""Filtro por município (IBGE) nas consultas do dashboard."""
from __future__ import annotations

import sqlite3
from typing import Any

from extrator.config_municipio import municipio_ibge, municipio_nome, municipios_monitorados


def listar_municipios(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Municípios com contratos no banco + município ativo da coleta (env)."""
    rows = conn.execute(
        """
        SELECT o.municipio_ibge AS ibge,
               MAX(o.municipio_nome) AS nome,
               COUNT(DISTINCT c.numero_controle_pncp) AS contratos
        FROM orgaos o
        INNER JOIN contratos c ON c.orgao_cnpj = o.cnpj
        WHERE o.municipio_ibge IS NOT NULL AND TRIM(o.municipio_ibge) != ''
        GROUP BY o.municipio_ibge
        ORDER BY contratos DESC, nome
        """
    ).fetchall()
    por_ibge = {r["ibge"]: dict(r) for r in rows}
    for alvo in municipios_monitorados():
        if alvo.ibge not in por_ibge:
            por_ibge[alvo.ibge] = {
                "ibge": alvo.ibge,
                "nome": alvo.nome,
                "contratos": 0,
                "monitorado": True,
                "prioridade": alvo.prioridade,
            }
        else:
            por_ibge[alvo.ibge]["monitorado"] = True
            por_ibge[alvo.ibge]["prioridade"] = alvo.prioridade
    items = sorted(
        por_ibge.values(),
        key=lambda i: (not i.get("monitorado"), i.get("prioridade", 9), -(i.get("contratos") or 0)),
    )
    ativo = municipio_ibge()
    if not any(i["ibge"] == ativo for i in items):
        items.insert(0, {
            "ibge": ativo,
            "nome": municipio_nome(),
            "contratos": 0,
            "monitorado": True,
            "prioridade": 1,
        })
    return items


def filtro_municipio_sql(
    ibge: str | None,
    *,
    alias: str = "o",
) -> tuple[str, list[str]]:
    """Retorna cláusula SQL e parâmetros para filtrar por IBGE."""
    if not ibge or not str(ibge).strip():
        return "", []
    return f"{alias}.municipio_ibge = ?", [str(ibge).strip()]


def resumo_triagem_municipio(conn: sqlite3.Connection, ibge: str) -> dict[str, int]:
    """Resumo de status de alertas filtrado por município do órgão."""
    from db.triagem import STATUS_VALIDOS, STATUS_ABERTO, STATUS_INVESTIGANDO

    rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(a.status), ''), ?) AS st, COUNT(*) AS n
        FROM alertas a
        JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
        JOIN orgaos o ON o.cnpj = c.orgao_cnpj
        WHERE o.municipio_ibge = ?
        GROUP BY st
        """,
        (STATUS_ABERTO, ibge),
    ).fetchall()
    base = {s: 0 for s in STATUS_VALIDOS}
    for row in rows:
        st = (row["st"] or STATUS_ABERTO).strip().lower()
        if st in base:
            base[st] = int(row["n"])
    base["fila"] = base[STATUS_ABERTO] + base[STATUS_INVESTIGANDO]
    return base
