"""Precisão medida por detector — reutilizável pela página /precisao e pela API pública.

Precisão = confirmados / (confirmados + descartados), lida da triagem humana real
(coluna alertas.status). Só reporta a taxa quando há amostra rotulada suficiente;
senão marca 'amostra_insuficiente'. Fonte única para /api/precisao e /api/v1/precisao.
"""
from __future__ import annotations

import sqlite3

# Mínimo de alertas rotulados (confirmado + descartado) para exibir uma taxa —
# abaixo disso o número não é confiável.
MIN_AMOSTRA_PRECISAO = 10


def calcular_precisao(
    conn: sqlite3.Connection, min_amostra: int = MIN_AMOSTRA_PRECISAO
) -> dict:
    """Agrega a triagem por tipo de detector e devolve a precisão medida.

    Retorna {itens: [...], min_amostra, rotulados_total}, onde cada item tem
    tipo, total, confirmados, descartados, pendentes, rotulados, precisao
    (float 0–1 ou None) e amostra_status ('medida' | 'amostra_insuficiente').
    """
    rows = conn.execute(
        """
        SELECT tipo,
               COUNT(*) AS total,
               SUM(CASE WHEN status = 'confirmado' THEN 1 ELSE 0 END) AS confirmados,
               SUM(CASE WHEN status = 'descartado' THEN 1 ELSE 0 END) AS descartados,
               SUM(CASE WHEN COALESCE(status, 'aberto') IN ('aberto', 'investigando')
                        THEN 1 ELSE 0 END) AS pendentes
        FROM alertas
        GROUP BY tipo
        ORDER BY total DESC
        """
    ).fetchall()

    itens = []
    rotulados_total = 0
    for r in rows:
        d = dict(r)
        rotulados = (d["confirmados"] or 0) + (d["descartados"] or 0)
        rotulados_total += rotulados
        if rotulados >= min_amostra:
            d["precisao"] = round(d["confirmados"] / rotulados, 3)
            d["amostra_status"] = "medida"
        else:
            d["precisao"] = None
            d["amostra_status"] = "amostra_insuficiente"
        d["rotulados"] = rotulados
        itens.append(d)

    return {
        "itens": itens,
        "min_amostra": min_amostra,
        "rotulados_total": rotulados_total,
    }
