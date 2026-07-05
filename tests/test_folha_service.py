"""Testes para folha_pagamento/service.py (PayrollImportService) usando um fake repository."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

import pytest

from folha_pagamento.parser import RegistroFolha
from folha_pagamento.repository import FolhaPagamentoRepository
from folha_pagamento.service import PayrollImportService


class _FakeFolhaPagamentoRepository(FolhaPagamentoRepository):
    """Simula a persistência real: servidores/orgaos em dict, folha_mensal com chave única."""

    def __init__(self):
        self.servidores: dict[str, str] = {}
        self.orgaos: dict[str, str | None] = {}
        self._chaves_folha: set[tuple[str, str, date]] = set()
        self.folha: list[RegistroFolha] = []

    def upsert_servidores_em_lote(self, itens: Iterable[tuple[str, str]]) -> None:
        for matricula, nome in itens:
            self.servidores[matricula] = nome

    def upsert_orgaos_em_lote(self, itens: Iterable[tuple[str, str | None]]) -> None:
        for sigla_ua, nome in itens:
            self.orgaos[sigla_ua] = nome

    def insert_folha_mensal(self, registros: Iterable[RegistroFolha]) -> int:
        inseridos = 0
        for r in registros:
            chave = (r.matricula, r.tipo_folha, r.competencia)
            if chave in self._chaves_folha:
                continue
            self._chaves_folha.add(chave)
            self.folha.append(r)
            inseridos += 1
        return inseridos


_CABECALHO = (
    "NOME;MATRICULA;SIGLA_UA;TIPO_FOLHA;REMUNERAÇÃO BRUTA;DESCONTOS DE PREVIDÊNCIA;"
    "DESCONTOS DE IR;OUTROS DESCONTOS;DESCONTOS EXCEDENTE DE TETO;REMUNERAÇÃO LÍQUIDA\n"
)


def _escrever_csv(tmp_path: Path, nome_arquivo: str, linhas: list[str]) -> Path:
    caminho = tmp_path / nome_arquivo
    conteudo = _CABECALHO + "\n".join(linhas)
    caminho.write_bytes(conteudo.encode("latin-1"))
    return caminho


def test_importar_le_persiste_servidor_orgao_e_folha(tmp_path: Path):
    linhas = ["MARIA DA SILVA;12345;SMS;NORMAL;3018,31;;;;;3018,31"]
    caminho = _escrever_csv(tmp_path, "ArquivoTC202106.csv", linhas)
    repo = _FakeFolhaPagamentoRepository()

    resultado = PayrollImportService(repo).importar(caminho)

    assert resultado == {"lidos": 1, "inseridos": 1, "ignorados": 0}
    assert repo.servidores["12345"] == "MARIA DA SILVA"
    assert "SMS" in repo.orgaos
    assert len(repo.folha) == 1


def test_importar_matricula_duplicada_tipos_diferentes_gera_multiplas_linhas(tmp_path: Path):
    linhas = [
        "MARIA DA SILVA;12345;SMS;NORMAL;3018,31;;;;;3018,31",
        "MARIA DA SILVA;12345;SMS;SUPLEMENTO;500,00;;;;;500,00",
    ]
    caminho = _escrever_csv(tmp_path, "ArquivoTC202106.csv", linhas)
    repo = _FakeFolhaPagamentoRepository()

    resultado = PayrollImportService(repo).importar(caminho)

    assert resultado == {"lidos": 2, "inseridos": 2, "ignorados": 0}
    # servidores/orgaos dedupados antes do lote — uma entrada por matrícula/órgão distinto
    assert repo.servidores == {"12345": "MARIA DA SILVA"}
    assert set(repo.orgaos.keys()) == {"SMS"}


def test_importar_mesmo_arquivo_duas_vezes_e_idempotente(tmp_path: Path):
    linhas = ["MARIA DA SILVA;12345;SMS;NORMAL;3018,31;;;;;3018,31"]
    caminho = _escrever_csv(tmp_path, "ArquivoTC202106.csv", linhas)
    repo = _FakeFolhaPagamentoRepository()
    servico = PayrollImportService(repo)

    primeira = servico.importar(caminho)
    segunda = servico.importar(caminho)

    assert primeira == {"lidos": 1, "inseridos": 1, "ignorados": 0}
    assert segunda == {"lidos": 1, "inseridos": 0, "ignorados": 1}
    assert len(repo.folha) == 1
