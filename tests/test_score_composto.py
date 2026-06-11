"""Testes do score composto de priorização."""
from __future__ import annotations

from analise.score_composto import calcular_score_composto


def test_score_alta_severidade_e_valor() -> None:
    score = calcular_score_composto(0.9, "alta", 25_000_000.0)
    assert score >= 0.8


def test_score_baixa_sem_valor() -> None:
    score = calcular_score_composto(0.2, "baixa", 0)
    assert 0.1 <= score <= 0.2


def test_score_valor_capado_no_teto() -> None:
    baixo = calcular_score_composto(0.5, "media", 10_000_000.0)
    alto = calcular_score_composto(0.5, "media", 100_000_000.0)
    assert alto > baixo
    assert alto - baixo < 0.26
