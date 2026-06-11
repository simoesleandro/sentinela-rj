"""Score composto para priorização de alertas na triagem."""
from __future__ import annotations

_SEV_PESO = {"alta": 0.4, "media": 0.25, "baixa": 0.1}
_VALOR_TETO = 50_000_000.0


def calcular_score_composto(
    score: float | None,
    severidade: str | None,
    valor: float | None,
) -> float:
    """Combina score do detector, severidade e valor envolvido (0–1)."""
    sev = _SEV_PESO.get((severidade or "baixa").lower(), 0.1)
    val = min((valor or 0) / _VALOR_TETO, 1.0) * 0.25
    det = (score or 0) * 0.35
    return round(det + sev + val, 4)
