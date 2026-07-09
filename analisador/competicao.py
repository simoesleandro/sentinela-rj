"""Detector de competição fraca em licitações — Sentinela RJ.

Dois sinais sobre a tabela `licitacoes` (extrator/licitacoes.py):

1. desconto_zero_licitacao
   Certame competitivo (pregão/concorrência) homologado praticamente no valor
   estimado. Medido em jul/2026 sobre 230 pregões homologados da PCRJ: o
   desconto MEDIANO é 22,6% — homologar com desconto <= 0,5% acontece em só
   10% dos certames e é indicador clássico de combinação de preços ou
   orçamento direcionado (o "desconto zero" dos painéis do TCU).

2. licitacao_itens_desertos
   Maioria dos itens do certame deserta ou fracassada. Ter ALGUM item
   fracassado é comum (35% das compras da PCRJ na amostra medida) — o sinal
   só dispara quando a MAIORIA falhou, indício de edital mal dimensionado ou
   afastamento deliberado de competidores.

Limitação documentada: a API de consulta do PNCP não expõe a quantidade de
propostas recebidas (fica no sistema de origem) — "licitante único" literal
não é computável por esta fonte; estes dois sinais são os proxies disponíveis.
"""
from __future__ import annotations

import sqlite3

from analisador.engine import AnomaliaResult

# desconto_zero — calibrado na medição de jul/2026 (mediana 22,6%; <=0,5% = 10%)
_DESCONTO_MAX = 0.005          # desconto <= 0,5% dispara
_VALOR_MIN_DESCONTO = 500_000  # ignora certames pequenos
_LIMIAR_ALTA_VALOR = 5_000_000
_LIMIAR_MEDIA_VALOR = 1_000_000

# itens desertos — "ter algum" satura (35%); exigimos maioria
_PROPORCAO_MIN_DESERTOS = 0.5
_MIN_ITENS = 4
_VALOR_MIN_DESERTOS = 500_000
_SITUACOES_FALHA = ("Deserto", "Fracassado")


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    resultados: list[AnomaliaResult] = []
    resultados.extend(_detectar_desconto_zero(conn))
    resultados.extend(_detectar_itens_desertos(conn))
    return resultados


def _detectar_desconto_zero(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    rows = conn.execute(
        """
        SELECT numero_controle_pncp, orgao_cnpj, modalidade_nome, objeto,
               valor_estimado, valor_homologado, srp, data_publicacao
        FROM licitacoes
        WHERE valor_homologado IS NOT NULL
          AND valor_estimado > 0
          AND valor_homologado >= ?
          AND valor_homologado <= valor_estimado * 1.05
        """,
        (_VALOR_MIN_DESCONTO,),
    ).fetchall()

    resultados = []
    for row in rows:
        pncp, orgao, modalidade, objeto, est, hom, srp, data_pub = row
        desconto = 1 - hom / est
        if desconto > _DESCONTO_MAX:
            continue

        if hom >= _LIMIAR_ALTA_VALOR:
            severidade, base = "alta", 0.70
        elif hom >= _LIMIAR_MEDIA_VALOR:
            severidade, base = "media", 0.45
        else:
            severidade, base = "baixa", 0.25
        score = round(min(1.0, base + min(hom / 50_000_000, 0.25)), 3)

        resultados.append(AnomaliaResult(
            tipo="desconto_zero_licitacao",
            severidade=severidade,
            score=score,
            titulo=(
                f"Desconto ~zero em {modalidade or 'certame'} — "
                f"R$ {hom/1e6:.1f}M homologado no estimado"
            ),
            descricao=(
                f"Certame homologado por R$ {hom:,.2f} com valor estimado de "
                f"R$ {est:,.2f} — desconto de {desconto*100:.2f}%. Num pregão "
                f"competitivo da PCRJ o desconto mediano medido é 22,6%; "
                f"homologar no preço estimado sugere ausência de disputa real "
                f"(combinação de preços ou orçamento direcionado). "
                f"Objeto: {(objeto or 'não informado')[:120]}."
            ),
            metodologia=(
                f"Compara valorTotalEstimado × valorTotalHomologado do PNCP em "
                f"modalidades competitivas. Dispara com desconto ≤ {_DESCONTO_MAX*100:.1f}% "
                f"e homologado ≥ R$ {_VALOR_MIN_DESCONTO:,.0f}. Calibração jul/2026: "
                f"mediana de desconto 22,6% (n=230); ≤0,5% ocorre em 10% dos certames. "
                f"A API não expõe nº de propostas — este é o proxy disponível."
            ),
            contratos=[pncp],
            metricas={
                "valor_estimado": est,
                "valor_homologado": hom,
                "desconto_pct": round(desconto * 100, 3),
                "modalidade": modalidade,
                "srp": bool(srp),
                "orgao_cnpj": orgao,
            },
            valor_referencia=hom,
        ))
    return resultados


def _detectar_itens_desertos(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    placeholders = ",".join("?" * len(_SITUACOES_FALHA))
    rows = conn.execute(
        f"""
        SELECT l.numero_controle_pncp, l.modalidade_nome, l.objeto,
               l.valor_estimado, l.orgao_cnpj,
               COUNT(i.numero_item) AS n_itens,
               SUM(CASE WHEN i.situacao_nome IN ({placeholders}) THEN 1 ELSE 0 END) AS n_falha
        FROM licitacoes l
        JOIN licitacao_itens i ON i.numero_controle_pncp = l.numero_controle_pncp
        WHERE l.valor_estimado >= ?
        GROUP BY l.numero_controle_pncp
        HAVING n_itens >= ?
        """,
        (*_SITUACOES_FALHA, _VALOR_MIN_DESERTOS, _MIN_ITENS),
    ).fetchall()

    resultados = []
    for pncp, modalidade, objeto, est, orgao, n_itens, n_falha in rows:
        proporcao = n_falha / n_itens
        if proporcao < _PROPORCAO_MIN_DESERTOS:
            continue

        if proporcao >= 0.8 and est >= _LIMIAR_ALTA_VALOR:
            severidade, base = "alta", 0.65
        elif est >= _LIMIAR_MEDIA_VALOR:
            severidade, base = "media", 0.40
        else:
            severidade, base = "baixa", 0.25
        score = round(min(1.0, base + 0.3 * proporcao), 3)

        resultados.append(AnomaliaResult(
            tipo="licitacao_itens_desertos",
            severidade=severidade,
            score=score,
            titulo=(
                f"{n_falha}/{n_itens} itens desertos/fracassados — "
                f"R$ {est/1e6:.1f}M estimados"
            ),
            descricao=(
                f"{n_falha} de {n_itens} itens do certame ({proporcao*100:.0f}%) "
                f"terminaram desertos ou fracassados, com valor estimado de "
                f"R$ {est:,.2f}. Maioria de itens sem vencedor sugere edital mal "
                f"dimensionado, exigências restritivas ou afastamento de "
                f"competidores — e costuma preceder contratação direta. "
                f"Objeto: {(objeto or 'não informado')[:120]}."
            ),
            metodologia=(
                f"Situação dos itens via API de itens do PNCP. Dispara com "
                f"proporção ≥ {_PROPORCAO_MIN_DESERTOS*100:.0f}% de itens "
                f"desertos/fracassados, ≥ {_MIN_ITENS} itens e estimado ≥ "
                f"R$ {_VALOR_MIN_DESERTOS:,.0f}. Ter ALGUM item fracassado é comum "
                f"(35% das compras na amostra de jul/2026) — só a maioria dispara."
            ),
            contratos=[pncp],
            metricas={
                "n_itens": n_itens,
                "n_desertos_fracassados": n_falha,
                "proporcao": round(proporcao, 3),
                "valor_estimado": est,
                "modalidade": modalidade,
                "orgao_cnpj": orgao,
            },
            valor_referencia=est,
        ))
    return resultados
