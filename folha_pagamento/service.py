"""Orquestração da importação de folha de pagamento (Facade)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .parser import PayrollCSVParser
from .repository import FolhaPagamentoRepository

logger = logging.getLogger(__name__)


class PayrollImportService:
    """Orquestra parsing do CSV e persistência via FolhaPagamentoRepository."""

    def __init__(self, repository: FolhaPagamentoRepository):
        self._repository = repository

    def importar(self, caminho_csv: str | Path) -> dict[str, Any]:
        registros = PayrollCSVParser(caminho_csv).parse()

        servidores: dict[str, str] = {}
        orgaos: dict[str, str | None] = {}
        for r in registros:
            servidores.setdefault(r.matricula, r.nome)
            orgaos.setdefault(r.sigla_ua, None)

        self._repository.upsert_servidores_em_lote(list(servidores.items()))
        self._repository.upsert_orgaos_em_lote(list(orgaos.items()))

        inseridos = self._repository.insert_folha_mensal(registros)
        resultado = {
            "lidos": len(registros),
            "inseridos": inseridos,
            "ignorados": len(registros) - inseridos,
        }
        logger.info("[folha_pagamento] importação concluída: %s", resultado)
        return resultado
