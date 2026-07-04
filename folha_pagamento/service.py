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

        servidores_vistos: set[str] = set()
        orgaos_vistos: set[str] = set()
        for r in registros:
            if r.matricula not in servidores_vistos:
                self._repository.upsert_servidor(r.matricula, r.nome)
                servidores_vistos.add(r.matricula)
            if r.sigla_ua not in orgaos_vistos:
                self._repository.upsert_orgao(r.sigla_ua, None)
                orgaos_vistos.add(r.sigla_ua)

        inseridos = self._repository.insert_folha_mensal(registros)
        resultado = {
            "lidos": len(registros),
            "inseridos": inseridos,
            "ignorados": len(registros) - inseridos,
        }
        logger.info("[folha_pagamento] importação concluída: %s", resultado)
        return resultado
