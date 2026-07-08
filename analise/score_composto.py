"""Score composto para priorização de alertas na triagem.

Fonte única da fórmula: use :func:`calcular_score_composto` em Python e
:func:`score_composto_sql` para ordenar/agregar direto no SQL. Ambos derivam
das mesmas constantes, evitando rankings divergentes entre endpoints.
"""
from __future__ import annotations

_DET_PESO = 0.35
_VALOR_PESO = 0.25
_SEV_PESO = {"alta": 0.4, "media": 0.25, "baixa": 0.1}
_VALOR_TETO = 50_000_000.0


def calcular_score_composto(
    score: float | None,
    severidade: str | None,
    valor: float | None,
) -> float:
    """Combina score do detector, severidade e valor envolvido (0–1)."""
    sev = _SEV_PESO.get((severidade or "baixa").lower(), _SEV_PESO["baixa"])
    val = min((valor or 0) / _VALOR_TETO, 1.0) * _VALOR_PESO
    det = (score or 0) * _DET_PESO
    return round(det + sev + val, 4)


def score_composto_sql(alias: str = "a") -> str:
    """Fragmento SQL equivalente a :func:`calcular_score_composto`.

    Usado em ORDER BY e agregações. As colunas ``score``, ``severidade`` e
    ``valor_referencia`` são lidas de ``{alias}`` (padrão ``a`` = tabela alertas).
    """
    sev_when = " ".join(
        f"WHEN '{nivel}' THEN {peso}"
        for nivel, peso in _SEV_PESO.items()
        if nivel != "baixa"
    )
    return (
        "("
        f"COALESCE({alias}.score, 0) * {_DET_PESO}"
        f" + CASE COALESCE({alias}.severidade, 'baixa') {sev_when}"
        f" ELSE {_SEV_PESO['baixa']} END"
        f" + MIN(COALESCE({alias}.valor_referencia, 0) / {_VALOR_TETO}, 1.0) * {_VALOR_PESO}"
        ")"
    )
