"""
Detector de concentração de fornecedor — Sentinela RJ.

Método: janela deslizante de JANELA_DIAS dias por fornecedor.
Busca a janela de maior score (combinação de quantidade e valor).

Calibração: farmacêuticas com 20 contratos de R$ 316K total ficam em 'baixa'
(valor < MIN_VALOR). Construtora com 4 contratos de R$ 86M fica em 'alta'.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from analisador.engine import AnomaliaResult

_JANELA_DIAS = 90       # tamanho da janela deslizante
_MIN_CONTRATOS = 3      # contratos mínimos na janela para disparar
_MIN_VALOR = 1_000_000  # valor total mínimo para não filtrar compras rotineiras


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    c = conn.cursor()
    c.execute("""
        SELECT c.numero_controle_pncp, c.valor_global, c.objeto,
               c.categoria_processo_nome, c.data_assinatura,
               c.unidade_nome, c.fornecedor_ni,
               f.razao_social AS fornecedor
        FROM contratos c
        LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        WHERE c.valor_global > 0 AND c.data_assinatura IS NOT NULL
        ORDER BY c.fornecedor_ni, c.data_assinatura
    """)
    rows = [dict(r) for r in c.fetchall()]

    # Agrupa por fornecedor
    por_forn: dict[str, list[dict]] = {}
    for r in rows:
        por_forn.setdefault(r["fornecedor_ni"], []).append(r)

    resultados: list[AnomaliaResult] = []

    for ni, contratos in por_forn.items():
        if len(contratos) < _MIN_CONTRATOS:
            continue

        datas = [date.fromisoformat(c["data_assinatura"]) for c in contratos]

        # Janela deslizante: ancora em cada contrato e avança _JANELA_DIAS
        melhor: dict | None = None
        melhor_score = 0.0

        for i, d_ini in enumerate(datas):
            d_fim = d_ini + timedelta(days=_JANELA_DIAS)
            janela = [contratos[j] for j, d in enumerate(datas) if d_ini <= d <= d_fim]

            if len(janela) < _MIN_CONTRATOS:
                continue

            total = sum(c["valor_global"] for c in janela)
            if total < _MIN_VALOR:
                continue

            # Score: 30 % quantidade, 70 % valor
            # quantidade normalizada por 10, valor normalizado por R$ 50M
            count_f = min(len(janela), 10) / 10
            value_f = min(total / 50_000_000, 1.0)
            score = round(0.30 * count_f + 0.70 * value_f, 3)

            if score > melhor_score:
                melhor_score = score
                melhor = {"d_ini": d_ini, "d_fim": d_fim, "janela": janela, "total": total}

        if melhor is None:
            continue

        d_ini = melhor["d_ini"]
        d_fim = melhor["d_fim"]
        janela = melhor["janela"]
        total = melhor["total"]
        qtd = len(janela)
        nome = janela[0]["fornecedor"] or ni

        if melhor_score >= 0.65:
            severidade = "alta"
        elif melhor_score >= 0.35:
            severidade = "media"
        else:
            severidade = "baixa"

        categorias = sorted({c["categoria_processo_nome"] for c in janela if c["categoria_processo_nome"]})
        pncp_ids = [c["numero_controle_pncp"] for c in janela]
        orgaos = sorted({c["unidade_nome"] for c in janela if c["unidade_nome"]})

        resultados.append(AnomaliaResult(
            tipo="concentracao_fornecedor",
            severidade=severidade,
            score=melhor_score,
            titulo=f"Concentração: {qtd} contratos em {_JANELA_DIAS} dias — {nome[:50]}",
            descricao=(
                f"{nome} recebeu {qtd} contratos entre {d_ini} e "
                f"{d_fim.strftime('%Y-%m-%d')} ({_JANELA_DIAS} dias), "
                f"totalizando R$ {total:,.2f}. "
                f"Órgãos: {', '.join(orgaos[:3]) or 'não informado'}. "
                f"Categorias: {', '.join(categorias) or 'não informada'}."
            ),
            metodologia=(
                f"Janela deslizante de {_JANELA_DIAS} dias. "
                f"Score = 0,30×(qtd/10) + 0,70×(total/R$50M). "
                f"Filtros: ≥{_MIN_CONTRATOS} contratos e total ≥ R${_MIN_VALOR:,.0f}."
            ),
            contratos=pncp_ids,
            metricas={
                "qtd_contratos_janela": qtd,
                "total_janela": round(total, 2),
                "janela_inicio": str(d_ini),
                "janela_fim": str(d_fim.strftime("%Y-%m-%d")),
                "categorias": categorias,
                "orgaos": orgaos[:5],
            },
            valor_referencia=total,
        ))

    return resultados
