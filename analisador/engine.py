"""
Sentinela RJ — Motor de análise de anomalias.

Interface pública:
    anomalias = analisar(conn)                 -> list[AnomaliaResult]
    anomalias, n, contagens = executar_e_persistir(conn)
    n = persistir_alertas(conn, anomalias)     -> int
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

Severidade = Literal["baixa", "media", "alta"]

_Detectores = list[tuple[str, Callable[[sqlite3.Connection], list["AnomaliaResult"]]]]


@dataclass
class AnomaliaResult:
    tipo: str
    severidade: Severidade
    score: float
    titulo: str
    descricao: str
    metodologia: str
    contratos: list[str] = field(default_factory=list)
    metricas: dict = field(default_factory=dict)
    valor_referencia: float | None = None


def _carregar_detectores() -> _Detectores:
    from analisador import (
        concentracao,
        fracionamento,
        licitacao,
        outliers,
        sancoes,
        socios,
    )

    return [
        ("outliers", outliers.detectar),
        ("concentracao", concentracao.detectar),
        ("licitacao", licitacao.detectar),
        ("fracionamento", fracionamento.detectar),
        ("sancoes", sancoes.detectar),
        ("socios", socios.detectar),
    ]


def _executar_detectores(
    conn: sqlite3.Connection,
) -> tuple[list[AnomaliaResult], dict[str, int]]:
    resultados: list[AnomaliaResult] = []
    contagens: dict[str, int] = {}
    for nome, detectar in _carregar_detectores():
        encontrados = detectar(conn)
        contagens[nome] = len(encontrados)
        resultados.extend(encontrados)
    resultados.sort(key=lambda a: a.score, reverse=True)
    return resultados, contagens


def analisar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    """Executa todos os detectores e devolve anomalias ordenadas por score desc."""
    resultados, _ = _executar_detectores(conn)
    return resultados


def persistir_alertas(conn: sqlite3.Connection, anomalias: list[AnomaliaResult]) -> int:
    """Grava anomalias na tabela alertas (compatível com chamadas legadas)."""
    from db.alertas_sync import sincronizar_alertas

    resumo = sincronizar_alertas(conn, anomalias)
    return resumo["inseridos"] + resumo["atualizados"]


def executar_e_persistir(
    conn: sqlite3.Connection,
) -> tuple[list[AnomaliaResult], int, dict[str, int]]:
    """Orquestração única: analisa e sincroniza alertas preservando triagem."""
    from db.alertas_sync import sincronizar_alertas

    resultados, contagens = _executar_detectores(conn)
    resumo = sincronizar_alertas(conn, resultados)
    n_sincronizados = resumo["inseridos"] + resumo["atualizados"]
    return resultados, n_sincronizados, contagens
