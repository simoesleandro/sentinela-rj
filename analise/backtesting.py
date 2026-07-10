"""Backtesting contra casos conhecidos — Sentinela RJ.

Responde, de forma verificável por terceiros: **"o Sentinela teria detectado?"**

Roda os detectores (já persistidos em `alertas`) contra os casos investigados e
noticiados da tabela `casos` — cada um com um `tipo_anomalia` esperado (a
natureza pública do caso). Para cada caso, reporta quais detectores dispararam
sobre os contratos daquele fornecedor, e se o **detector temático** (o que casa
com a natureza conhecida do caso) foi um deles.

Não é auto-avaliação circular: os casos foram apurados/noticiados de forma
independente (suspensão judicial da MJRE, inexigibilidade da Bônus Track,
concentração da Entre os Rios). O backtest mostra se os detectores automáticos,
sem conhecer esses desfechos, sinalizam os mesmos atores.

Um caso sem CNPJ único (padrão Asfalto Fatiado, distribuído entre empresas) é
avaliado pelo detector dedicado que a sua descoberta motivou.
"""
from __future__ import annotations

import sqlite3
from typing import Any

_SEV_ORDEM = {"baixa": 1, "media": 2, "alta": 3}


def _detectores_do_fornecedor(conn: sqlite3.Connection, cnpj: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT a.tipo,
               COUNT(*) AS n,
               MAX(CASE a.severidade WHEN 'alta' THEN 3 WHEN 'media' THEN 2 ELSE 1 END) AS sev_num
        FROM alertas a
        JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
        WHERE c.fornecedor_ni = ?
        GROUP BY a.tipo
        ORDER BY sev_num DESC, n DESC
        """,
        (cnpj,),
    ).fetchall()
    sev_label = {3: "alta", 2: "media", 1: "baixa"}
    return [
        {"tipo": r[0], "n": r[1], "severidade": sev_label.get(r[2], "baixa")}
        for r in rows
    ]


def _detector_global(conn: sqlite3.Connection, tipo: str) -> list[dict[str, Any]]:
    """Para casos-padrão sem CNPJ único: o detector dedicado disparou na base?"""
    row = conn.execute(
        """
        SELECT COUNT(*) AS n,
               MAX(CASE severidade WHEN 'alta' THEN 3 WHEN 'media' THEN 2 ELSE 1 END) AS sev_num
        FROM alertas WHERE tipo = ?
        """,
        (tipo,),
    ).fetchone()
    if not row or not row[0]:
        return []
    sev_label = {3: "alta", 2: "media", 1: "baixa"}
    return [{"tipo": tipo, "n": row[0], "severidade": sev_label.get(row[1], "baixa")}]


def _valor_flagrado(conn: sqlite3.Connection, cnpj: str) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(valor), 0) FROM (
            SELECT DISTINCT c.numero_controle_pncp, c.valor_global AS valor
            FROM alertas a
            JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            WHERE c.fornecedor_ni = ? AND c.valor_global > 0
        )
        """,
        (cnpj,),
    ).fetchone()
    return float(row[0] or 0)


def executar_backtest(conn: sqlite3.Connection) -> dict[str, Any]:
    casos = conn.execute(
        """
        SELECT titulo, fornecedor_nome, fornecedor_cnpj, tipo_anomalia, valor, resumo
        FROM casos ORDER BY ordem, id
        """
    ).fetchall()

    resultados: list[dict[str, Any]] = []
    for caso in casos:
        cnpj = caso["fornecedor_cnpj"]
        tipo_esperado = caso["tipo_anomalia"]

        if cnpj:
            detectores = _detectores_do_fornecedor(conn, cnpj)
            valor_flagrado = _valor_flagrado(conn, cnpj)
            base = "cnpj"
        else:
            detectores = _detector_global(conn, tipo_esperado)
            valor_flagrado = 0.0
            base = "padrao"

        tipos = {d["tipo"] for d in detectores}
        tematico = tipo_esperado in tipos
        n_alertas = sum(d["n"] for d in detectores)

        if not detectores:
            veredito = "nao_detectado"
        elif tematico:
            veredito = "detectado"
        else:
            veredito = "parcial"  # sinalizado, mas não pelo detector temático

        resultados.append({
            "titulo": caso["titulo"],
            "fornecedor": caso["fornecedor_nome"],
            "cnpj": cnpj,
            "tipo_esperado": tipo_esperado,
            "base": base,
            "detectores": detectores,
            "n_detectores": len(detectores),
            "n_alertas": n_alertas,
            "valor_flagrado": valor_flagrado,
            "detector_tematico_disparou": tematico,
            "veredito": veredito,
        })

    detectados = sum(1 for r in resultados if r["veredito"] == "detectado")
    parciais = sum(1 for r in resultados if r["veredito"] == "parcial")
    return {
        "casos": resultados,
        "resumo": {
            "total": len(resultados),
            "detectados": detectados,
            "parciais": parciais,
            "nao_detectados": len(resultados) - detectados - parciais,
        },
    }
