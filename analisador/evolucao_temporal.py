"""
Detector de evolução temporal — Sentinela RJ.

Identifica fornecedores cuja quantidade de contratos disparou na janela
recente (90 dias) em relação ao período anterior equivalente.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from analisador.engine import AnomaliaResult

_JANELA_DIAS = 90
_MIN_RECENTE = 4
_MIN_AUMENTO = 3
_MIN_RAZAO = 2.0


def _data_ref(rows: list[dict]) -> date:
    datas = [date.fromisoformat(r["data_assinatura"]) for r in rows if r["data_assinatura"]]
    return max(datas) if datas else date.today()


def _contar_janela(contratos: list[dict], inicio: date, fim: date) -> list[dict]:
    return [
        c for c in contratos
        if inicio < date.fromisoformat(c["data_assinatura"]) <= fim
    ]


def _score_evolucao(recente: int, anterior: int) -> float:
    razao = recente / max(anterior, 1)
    aumento_norm = min((recente - anterior) / 10, 1.0)
    razao_norm = min(razao / 5, 1.0)
    return round(0.45 * aumento_norm + 0.55 * razao_norm, 3)


def _severidade(recente: int, razao: float) -> str:
    if recente >= 8 and razao >= 3:
        return "alta"
    if recente >= 6 or razao >= 2.5:
        return "media"
    return "baixa"


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    rows = conn.execute(
        """
        SELECT c.numero_controle_pncp, c.valor_global, c.data_assinatura,
               c.fornecedor_ni, f.razao_social AS fornecedor
        FROM contratos c
        LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        WHERE c.valor_global > 0 AND c.data_assinatura IS NOT NULL
        ORDER BY c.fornecedor_ni, c.data_assinatura
        """
    ).fetchall()
    por_forn: dict[str, list[dict]] = {}
    for row in rows:
        item = dict(row)
        por_forn.setdefault(item["fornecedor_ni"], []).append(item)

    ref = _data_ref([dict(r) for r in rows])
    fim_recente = ref
    ini_recente = ref - timedelta(days=_JANELA_DIAS)
    fim_anterior = ini_recente
    ini_anterior = ref - timedelta(days=_JANELA_DIAS * 2)

    resultados: list[AnomaliaResult] = []
    for ni, contratos in por_forn.items():
        recentes = _contar_janela(contratos, ini_recente, fim_recente)
        anteriores = _contar_janela(contratos, ini_anterior, fim_anterior)
        qtd_recente = len(recentes)
        qtd_anterior = len(anteriores)
        if qtd_recente < _MIN_RECENTE:
            continue
        aumento = qtd_recente - qtd_anterior
        razao = qtd_recente / max(qtd_anterior, 1)
        if aumento < _MIN_AUMENTO or razao < _MIN_RAZAO:
            continue

        nome = contratos[0].get("fornecedor") or ni
        valor_recente = sum(c["valor_global"] or 0 for c in recentes)
        sev = _severidade(qtd_recente, razao)
        resultados.append(
            AnomaliaResult(
                tipo="evolucao_temporal_fornecedor",
                severidade=sev,
                score=_score_evolucao(qtd_recente, qtd_anterior),
                titulo=f"Aceleração contratual — {nome}",
                descricao=(
                    f"Fornecedor passou de {qtd_anterior} para {qtd_recente} contratos "
                    f"nos últimos {_JANELA_DIAS} dias (×{razao:.1f})."
                ),
                metodologia=(
                    f"Comparação janelas {_JANELA_DIAS}d recente vs {_JANELA_DIAS}d anterior; "
                    f"mín. {_MIN_RECENTE} recentes, +{_MIN_AUMENTO} contratos, razão ≥{_MIN_RAZAO}."
                ),
                contratos=[c["numero_controle_pncp"] for c in recentes],
                metricas={
                    "qtd_recente": qtd_recente,
                    "qtd_anterior": qtd_anterior,
                    "razao": round(razao, 2),
                    "janela_dias": _JANELA_DIAS,
                },
                valor_referencia=valor_recente,
            )
        )
    return resultados
