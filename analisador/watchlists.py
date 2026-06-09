"""Detector pós-processamento — cruzamento de contratos com watchlists."""
from __future__ import annotations

import sqlite3
from typing import Any

from analisador.engine import AnomaliaResult

_TIPO = "watchlist_match"
_SCORE_BASE = 0.75
_SEVERIDADE_BASE = "media"

_SQL_MATCH = """
SELECT w.id AS watchlist_id,
       w.rotulo,
       w.fornecedor_ni AS wl_fornecedor,
       w.orgao_cnpj AS wl_orgao,
       w.palavra_chave_objeto AS wl_palavra,
       c.numero_controle_pncp,
       c.valor_global,
       c.objeto,
       c.fornecedor_ni,
       c.orgao_cnpj,
       f.razao_social AS fornecedor_nome,
       o.razao_social AS orgao_nome
FROM watchlists w
JOIN contratos c ON (
    (w.fornecedor_ni IS NULL OR c.fornecedor_ni = w.fornecedor_ni)
    AND (w.orgao_cnpj IS NULL OR c.orgao_cnpj = w.orgao_cnpj)
    AND (
        w.palavra_chave_objeto IS NULL
        OR TRIM(w.palavra_chave_objeto) = ''
        OR INSTR(LOWER(COALESCE(c.objeto, '')), LOWER(w.palavra_chave_objeto)) > 0
    )
)
LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
WHERE w.ativo = 1
  AND c.valor_global > 0
"""


def _montar_criterios(row: sqlite3.Row) -> str:
    partes: list[str] = []
    if row["wl_fornecedor"]:
        partes.append(f"fornecedor={row['wl_fornecedor']}")
    if row["wl_orgao"]:
        partes.append(f"orgao={row['wl_orgao']}")
    if row["wl_palavra"]:
        partes.append(f"palavra={row['wl_palavra']}")
    return ",".join(partes) or "wildcard"


def _montar_descricao(row: sqlite3.Row) -> str:
    fornecedor = row["fornecedor_nome"] or row["fornecedor_ni"] or "—"
    orgao = row["orgao_nome"] or row["orgao_cnpj"] or "—"
    objeto = (row["objeto"] or "")[:120]
    valor = row["valor_global"] or 0.0
    return (
        f"Watchlist «{row['rotulo']}» — contrato {row['numero_controle_pncp']} "
        f"({fornecedor} / {orgao}) — R$ {valor:,.2f}. Objeto: {objeto}"
    )


def _row_para_anomalia(row: sqlite3.Row) -> AnomaliaResult:
    wl_id = int(row["watchlist_id"])
    criterios = _montar_criterios(row)
    return AnomaliaResult(
        tipo=_TIPO,
        severidade=_SEVERIDADE_BASE,
        score=_SCORE_BASE,
        titulo=f"Watchlist: {row['rotulo']}",
        descricao=_montar_descricao(row),
        metodologia=f"watchlist_id={wl_id}; criterios={criterios}",
        contratos=[row["numero_controle_pncp"]],
        metricas={"watchlist_id": wl_id, "rotulo": row["rotulo"]},
        valor_referencia=float(row["valor_global"] or 0),
    )


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    """Cruza contratos com watchlists ativas; retorna alertas watchlist_match."""
    rows = conn.execute(_SQL_MATCH).fetchall()
    return [_row_para_anomalia(row) for row in rows]


def executar_watchlists_e_persistir(
    conn: sqlite3.Connection,
) -> tuple[list[AnomaliaResult], dict[str, Any]]:
    """Detecta matches e sincroniza alertas watchlist_match (escopo isolado)."""
    from db.alertas_sync import sincronizar_alertas

    matches = detectar(conn)
    resumo = sincronizar_alertas(
        conn,
        matches,
        escopo_remocao="watchlist",
    )
    return matches, resumo
