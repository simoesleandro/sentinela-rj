"""Orquestração da importação de folha de pagamento (Facade)."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

from .parser import PayrollCSVParser, RegistroFolha
from .repository import AgregadoFolhaMensal, FolhaPagamentoRepository

logger = logging.getLogger(__name__)


def _agregar_por_matricula_competencia(
    registros: list[RegistroFolha],
) -> list[AgregadoFolhaMensal]:
    """Agrupa as linhas cruas do CSV (uma por tipo_folha) em uma linha por mês/matrícula.

    remuneracao_bruta_total é a soma de todas as linhas do grupo; excedeu_teto é
    True se qualquer linha do grupo tinha desconto_excedente_teto > 0 no CSV original.
    """
    grupos: dict[tuple[str, date], list[RegistroFolha]] = {}
    for r in registros:
        grupos.setdefault((r.matricula, r.competencia), []).append(r)

    agregados: list[AgregadoFolhaMensal] = []
    for (matricula, competencia), linhas in grupos.items():
        agregados.append(
            AgregadoFolhaMensal(
                matricula=matricula,
                sigla_ua=linhas[0].sigla_ua,
                competencia=competencia,
                remuneracao_bruta_total=sum(
                    linha.remuneracao_bruta or 0 for linha in linhas
                ),
                excedeu_teto=any(
                    (linha.desconto_excedente_teto or 0) > 0 for linha in linhas
                ),
            )
        )
    return agregados


class PayrollImportService:
    """Orquestra parsing do CSV, agregação por matrícula/mês e persistência."""

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

        agregados = _agregar_por_matricula_competencia(registros)
        inseridos = self._repository.insert_folha_mensal(agregados)
        resultado = {
            "lidos": len(registros),
            "inseridos": inseridos,
            "ignorados": len(agregados) - inseridos,
        }
        logger.info("[folha_pagamento] importação concluída: %s", resultado)
        return resultado
