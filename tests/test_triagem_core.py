"""Testes da lógica pura de transição de estado (db/triagem_core.py)."""
from __future__ import annotations

import pytest

from db.triagem_core import (
    STATUS_ABERTO,
    STATUS_CONFIRMADO,
    STATUS_DESCARTADO,
    STATUS_INVESTIGANDO,
    STATUS_VALIDOS,
    TriagemError,
    TriagemRepository,
    normalizar_status,
    status_permitidos,
    validar_transicao,
)


def test_normalizar_status_vazio_vira_aberto() -> None:
    assert normalizar_status(None) == STATUS_ABERTO
    assert normalizar_status("") == STATUS_ABERTO


def test_normalizar_status_invalido_vira_aberto() -> None:
    assert normalizar_status("inexistente") == STATUS_ABERTO


def test_normalizar_status_normaliza_case_e_espacos() -> None:
    assert normalizar_status("  CONFIRMADO  ") == STATUS_CONFIRMADO


def test_status_permitidos_a_partir_de_aberto() -> None:
    assert status_permitidos(STATUS_ABERTO) == sorted(
        [STATUS_INVESTIGANDO, STATUS_DESCARTADO]
    )


def test_validar_transicao_permitida_nao_levanta() -> None:
    validar_transicao(STATUS_ABERTO, STATUS_INVESTIGANDO)


def test_validar_transicao_nao_permitida_levanta() -> None:
    with pytest.raises(TriagemError):
        validar_transicao(STATUS_ABERTO, STATUS_CONFIRMADO)


def test_validar_transicao_status_invalido_levanta() -> None:
    with pytest.raises(TriagemError):
        validar_transicao(STATUS_ABERTO, "lixo")


def test_status_validos_contem_os_quatro_estados() -> None:
    assert STATUS_VALIDOS == {
        STATUS_ABERTO,
        STATUS_INVESTIGANDO,
        STATUS_CONFIRMADO,
        STATUS_DESCARTADO,
    }


class _RepoFake:
    def atualizar_status(self, id, novo_status, nota=None) -> None:
        ...

    def registrar_historico(self, id, status_anterior, status_novo, nota=None) -> None:
        ...

    def resumo_status(self) -> dict:
        return {}


def test_protocolo_e_runtime_checkable() -> None:
    assert isinstance(_RepoFake(), TriagemRepository)


def test_objeto_sem_metodos_nao_satisfaz_protocolo() -> None:
    assert not isinstance(object(), TriagemRepository)
