"""
Detector de fracionamento de empenhos — Sentinela RJ.

Método: janela deslizante de 30 dias por fornecedor na tabela
transparencia_rj_lancamentos. Identifica fornecedores recebendo muitos
empenhos pequenos em sequência — padrão clássico de fracionamento para
driblar tetos de modalidade licitatória.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from analisador.engine import AnomaliaResult

_JANELA_DIAS = 30
_MIN_EMPENHOS = 3
_MAX_VALOR_MEDIO = 50_000.0   # empenhos "pequenos" abaixo deste teto
_MIN_VALOR_TOTAL = 50_000.0   # acumulado mínimo para ser relevante


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    c = conn.cursor()
    c.execute("""
        SELECT l.fornecedor_ni, l.valor, l.data_lancamento, l.documento,
               COALESCE(f.razao_social, l.fornecedor_ni) AS fornecedor
        FROM transparencia_rj_lancamentos l
        LEFT JOIN fornecedores f ON f.ni = l.fornecedor_ni
        WHERE l.valor > 0 AND l.data_lancamento IS NOT NULL
        ORDER BY l.fornecedor_ni, l.data_lancamento
    """)
    rows = [dict(r) for r in c.fetchall()]

    por_forn: dict[str, list[dict]] = {}
    for r in rows:
        por_forn.setdefault(r["fornecedor_ni"], []).append(r)

    resultados: list[AnomaliaResult] = []

    for ni, empenhos in por_forn.items():
        if len(empenhos) < _MIN_EMPENHOS:
            continue

        # data_lancamento pode vir com timestamp ("2026-05-22T14:00:17") em
        # coletas recentes da Transparência RJ — só a porção de data importa.
        datas = [date.fromisoformat(e["data_lancamento"][:10]) for e in empenhos]

        melhor: dict | None = None
        melhor_score = 0.0

        for i, d_ini in enumerate(datas):
            d_fim = d_ini + timedelta(days=_JANELA_DIAS)
            janela = [empenhos[j] for j, d in enumerate(datas) if d_ini <= d <= d_fim]

            if len(janela) < _MIN_EMPENHOS:
                continue

            total = sum(e["valor"] for e in janela)
            if total < _MIN_VALOR_TOTAL:
                continue

            valor_medio = total / len(janela)
            if valor_medio >= _MAX_VALOR_MEDIO:
                continue

            score = round(
                0.40 * min(len(janela), 10) / 10
                + 0.60 * (1.0 - valor_medio / _MAX_VALOR_MEDIO),
                3,
            )

            if score > melhor_score:
                melhor_score = score
                melhor = {
                    "d_ini": d_ini,
                    "d_fim": d_fim,
                    "janela": janela,
                    "total": total,
                    "valor_medio": valor_medio,
                }

        if melhor is None:
            continue

        d_ini = melhor["d_ini"]
        d_fim = melhor["d_fim"]
        janela = melhor["janela"]
        total = melhor["total"]
        valor_medio = melhor["valor_medio"]
        qtd = len(janela)
        nome = janela[0]["fornecedor"]
        documentos = [e["documento"] for e in janela if e["documento"]]

        if melhor_score >= 0.65:
            severidade = "alta"
        elif melhor_score >= 0.35:
            severidade = "media"
        else:
            severidade = "baixa"

        resultados.append(AnomaliaResult(
            tipo="fracionamento_empenhos",
            severidade=severidade,
            score=melhor_score,
            titulo=(
                f"Fracionamento de empenhos: {qtd} em {_JANELA_DIAS} dias"
                f" — {nome[:50]}"
            ),
            descricao=(
                f"{nome} recebeu {qtd} empenhos entre {d_ini} e "
                f"{d_fim.strftime('%Y-%m-%d')} ({_JANELA_DIAS} dias), "
                f"com valor médio de R$ {valor_medio:,.2f} por empenho "
                f"e total de R$ {total:,.2f}. "
                f"Padrão pode indicar fracionamento para contornar tetos "
                f"de modalidade licitatória."
            ),
            metodologia=(
                f"Janela deslizante de {_JANELA_DIAS} dias. "
                f"Filtros: ≥{_MIN_EMPENHOS} empenhos, "
                f"valor médio < R$ {_MAX_VALOR_MEDIO:,.0f} e "
                f"total ≥ R$ {_MIN_VALOR_TOTAL:,.0f}. "
                f"Score = 0,40×(qtd/10) + 0,60×(1 − valor_médio"
                f"/R$ {_MAX_VALOR_MEDIO:,.0f})."
            ),
            contratos=documentos,
            metricas={
                "qtd_empenhos": qtd,
                "valor_medio": round(valor_medio, 2),
                "valor_total": round(total, 2),
                "janela_inicio": str(d_ini),
                "janela_fim": str(d_fim.strftime("%Y-%m-%d")),
            },
            valor_referencia=total,
        ))

    return resultados
