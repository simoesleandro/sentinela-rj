"""Detector de carona (adesão a ata de registro de preços) — Sentinela RJ.

Carona é a adesão de um órgão à ata de registro de preços de OUTRO órgão
(Lei 14.133/2021, art. 86). É legal, mas concentra risco: o órgão aderente
pula a própria licitação, herda preços que não negociou (risco de sobrepreço)
e o instituto é vetor clássico de direcionamento pós-14.133.

Detecção — duas fontes, porque o flag do PNCP vem quase sempre vazio:
1. ``fruto_adesao = 1`` no contrato (quando o PNCP preenche);
2. o TEXTO do objeto menciona adesão a ata alheia — medido em jul/2026: o flag
   estava 0, mas 23 contratos (R$ 34M) diziam "Adesão à Ata" no objeto.

Distingue-se de prorrogação/saldo da PRÓPRIA ata do órgão (que não é carona):
o padrão casa "adesão a ata / ao registro" e "carona", não "ata de registro"
genérico.

Calibração (jul/2026): mediana das caronas é R$ 98 mil — a maioria é rotina
administrativa de baixo risco. O sinal só dispara acima de R$ 500 mil, onde a
adesão passa a ser material; severidade sobe com o valor.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata

from analisador.engine import AnomaliaResult

_VALOR_MIN = 500_000        # abaixo disso, carona é rotina administrativa
_LIMIAR_ALTA = 5_000_000
_LIMIAR_MEDIA = 1_000_000

# Padrões (já normalizados: sem acento, minúsculo). "adesao a ata" casa
# "Adesão à Ata de Registro de Preços"; não casa "prorrogação da ata" (própria).
_PADROES_CARONA = (
    "adesao a ata",
    "adesao ao registro",
    "adesao a registro",
    "carona",
)


def _normalizar(texto: str | None) -> str:
    sem_acento = (
        unicodedata.normalize("NFKD", texto or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def _e_carona(objeto: str | None, fruto_adesao: int | None) -> bool:
    if fruto_adesao == 1:
        return True
    norm = _normalizar(objeto)
    return any(p in norm for p in _PADROES_CARONA)


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    rows = conn.execute(
        """
        SELECT c.numero_controle_pncp, c.valor_global, c.objeto, c.fruto_adesao,
               c.data_assinatura, c.categoria_processo_nome,
               f.razao_social AS fornecedor
        FROM contratos c
        LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        WHERE c.valor_global >= ?
        """,
        (_VALOR_MIN,),
    ).fetchall()

    resultados: list[AnomaliaResult] = []
    for row in rows:
        pncp, valor, objeto, fruto, data, categoria, fornecedor = row
        if not _e_carona(objeto, fruto):
            continue

        if valor >= _LIMIAR_ALTA:
            severidade, base = "alta", 0.60
        elif valor >= _LIMIAR_MEDIA:
            severidade, base = "media", 0.40
        else:
            severidade, base = "baixa", 0.22
        score = round(min(1.0, base + min(valor / 50_000_000, 0.3)), 3)

        via = "flag PNCP" if fruto == 1 else "objeto"
        fornecedor_txt = fornecedor or "fornecedor não identificado"

        resultados.append(AnomaliaResult(
            tipo="adesao_carona",
            severidade=severidade,
            score=score,
            titulo=(
                f"Carona (adesão a ata) — R$ {valor/1e6:.1f}M · {fornecedor_txt[:38]}"
            ),
            descricao=(
                f"Contrato de R$ {valor:,.2f} firmado por adesão a ata de registro "
                f"de preços (carona), com {fornecedor_txt}. A carona é permitida "
                f"(art. 86 da Lei 14.133/2021), mas o órgão pula a própria "
                f"licitação e herda preços que não negociou — risco de sobrepreço "
                f"e vetor conhecido de direcionamento. Merece conferir se a adesão "
                f"era vantajosa frente a uma contratação própria. "
                f"Objeto: {(objeto or 'não informado')[:120]}."
            ),
            metodologia=(
                f"Identifica contratos firmados por carona via flag fruto_adesao "
                f"do PNCP ou menção a 'adesão a ata / ao registro' no objeto (o "
                f"flag costuma vir vazio; o texto complementa). Exclui prorrogação "
                f"da própria ata. Dispara acima de R$ {_VALOR_MIN:,.0f} — calibração "
                f"jul/2026: mediana das caronas R$ 98 mil (rotina); materiais são "
                f"minoria. Severidade: ≥ R$ {_LIMIAR_ALTA:,.0f} alta, "
                f"≥ R$ {_LIMIAR_MEDIA:,.0f} média."
            ),
            contratos=[pncp],
            metricas={
                "valor_global": valor,
                "deteccao_via": via,
                "categoria": categoria,
                "fornecedor": fornecedor_txt,
            },
            valor_referencia=valor,
        ))

    return resultados
