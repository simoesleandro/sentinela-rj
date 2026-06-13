"""Resultado da investigação profunda de um alerta."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResultadoInvestigacaoProfunda:
    alerta_id: int
    status: str = "concluida"  # pendente/rodando/concluida/erro
    evidencias: dict[str, Any] = field(default_factory=dict)
    sintese: str = ""
    conclusao: str = ""          # arquivar/escalar/confirmar/inconclusivo
    grau_confianca: str = ""     # baixo/medio/alto
    recomendacao: str = ""
    erro: str | None = None
