"""
Detector de outliers de valor — Sentinela RJ.

Método: IQR (Tukey) por categoria de processo. Para categorias com menos de
MIN_AMOSTRA contratos, cai no IQR global como fallback.
Score secundário por Z-score para calibrar severidade.
"""
from __future__ import annotations

import sqlite3
import statistics

from analisador.engine import AnomaliaResult

_MIN_AMOSTRA = 4   # mínimo de contratos por categoria para IQR local


def _stats(valores: list[float]) -> dict:
    n = len(valores)
    media = statistics.mean(valores)
    std = statistics.pstdev(valores)      # população completa, não amostra
    q1, _, q3 = statistics.quantiles(valores, n=4)
    iqr = q3 - q1
    return {
        "n": n,
        "media": media,
        "std": std,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "upper_fence": q3 + 1.5 * iqr,
        "extreme_fence": q3 + 3.0 * iqr,
    }


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    c = conn.cursor()
    c.execute("""
        SELECT c.numero_controle_pncp, c.valor_global, c.objeto,
               c.categoria_processo_nome, c.data_assinatura,
               c.unidade_nome, f.razao_social AS fornecedor
        FROM contratos c
        LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        WHERE c.valor_global > 0
        ORDER BY c.categoria_processo_nome, c.valor_global
    """)
    rows = [dict(r) for r in c.fetchall()]

    # Agrupa valores por categoria
    por_cat: dict[str, list[float]] = {}
    for r in rows:
        cat = r["categoria_processo_nome"] or "Não informado"
        por_cat.setdefault(cat, []).append(r["valor_global"])

    # Pré-calcula stats por categoria (fallback: global)
    global_stats = _stats([r["valor_global"] for r in rows])
    cat_stats: dict[str, dict] = {
        cat: _stats(vals) if len(vals) >= _MIN_AMOSTRA else global_stats
        for cat, vals in por_cat.items()
    }

    resultados: list[AnomaliaResult] = []

    for row in rows:
        v = row["valor_global"]
        cat = row["categoria_processo_nome"] or "Não informado"
        st = cat_stats[cat]

        if v <= st["upper_fence"]:
            continue

        zscore = (v - st["media"]) / st["std"] if st["std"] > 0 else 0.0

        # IQR e Z-score precisam concordar: em distribuições assimétricas,
        # a média (puxada pelos outliers) pode ficar acima da fence.
        # Exigir zscore > 1,0 descarta esses falsos positivos.
        if zscore < 1.0:
            continue

        multiplicador = v / st["upper_fence"]

        if zscore >= 5:
            severidade, score = "alta", min(1.0, 0.60 + zscore / 30)
        elif zscore >= 3:
            severidade, score = "media", min(0.70, 0.40 + zscore / 30)
        else:
            severidade, score = "baixa", 0.25

        nome_forn = (row["fornecedor"] or "fornecedor não informado")[:50]
        n_cat = st["n"] if st is not global_stats else len(rows)

        resultados.append(AnomaliaResult(
            tipo="outlier_valor",
            severidade=severidade,
            score=round(score, 3),
            titulo=f"Valor atípico — {nome_forn}",
            descricao=(
                f"Contrato de R$ {v:,.2f} está {multiplicador:.1f}× acima do limite IQR "
                f"da categoria '{cat}' (Q3 + 1,5×IQR = R$ {st['upper_fence']:,.2f}). "
                f"Z-score: {zscore:.1f}. "
                f"Objeto: {(row['objeto'] or 'não informado')[:120]}."
            ),
            metodologia=(
                f"IQR por categoria (n={n_cat}). "
                f"Q1=R${st['q1']:,.0f}, Q3=R${st['q3']:,.0f}, "
                f"IQR=R${st['iqr']:,.0f}, fence=R${st['upper_fence']:,.0f}. "
                f"Z-score={zscore:.1f} "
                f"(média=R${st['media']:,.0f}, DP=R${st['std']:,.0f})."
            ),
            contratos=[row["numero_controle_pncp"]],
            metricas={
                "valor_global": v,
                "upper_fence": round(st["upper_fence"], 2),
                "zscore": round(zscore, 2),
                "multiplicador_fence": round(multiplicador, 2),
                "n_categoria": n_cat,
                "media_categoria": round(st["media"], 2),
            },
            valor_referencia=v,
        ))

    return resultados
