"""Testes de conflito_interesse/triagem_repository.py (ConflitoTriagemRepository)."""
from __future__ import annotations

from typing import Any

import pytest

from db.triagem_core import TriagemError, TriagemRepository
from conflito_interesse.triagem_repository import (
    CandidatoConflitoNaoEncontradoError,
    ConflitoTriagemRepository,
)


class _FakeCursor:
    def __init__(self, tabela: dict[int, str]):
        self._tabela = tabela
        self._resultado: list[tuple[Any, ...]] = []
        self.queries: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.queries.append((sql, params))
        if "SELECT status FROM candidatos_conflito_interesse WHERE id" in sql:
            (id_,) = params
            status = self._tabela.get(id_)
            self._resultado = [(status,)] if status is not None else []
        elif "UPDATE candidatos_conflito_interesse" in sql:
            novo_status, id_ = params
            self._tabela[id_] = novo_status
            self._resultado = []
        elif "GROUP BY status" in sql:
            contagem: dict[str, int] = {}
            for status in self._tabela.values():
                contagem[status] = contagem.get(status, 0) + 1
            self._resultado = list(contagem.items())
        else:
            self._resultado = []

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return self._resultado


class _FakeConn:
    def __init__(self, tabela: dict[int, str] | None = None):
        self.tabela: dict[int, str] = tabela or {}
        self.commits = 0

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.tabela)

    def commit(self) -> None:
        self.commits += 1


@pytest.fixture
def conn() -> _FakeConn:
    return _FakeConn({1: "aberto"})


def test_satisfaz_protocolo_triagem_repository(conn: _FakeConn) -> None:
    repo = ConflitoTriagemRepository(conn)
    assert isinstance(repo, TriagemRepository)


def test_atualizar_status_muda_status_e_grava_revisado_em(conn: _FakeConn) -> None:
    repo = ConflitoTriagemRepository(conn)
    repo.atualizar_status(1, "investigando")

    assert conn.tabela[1] == "investigando"
    assert conn.commits == 1


def test_atualizar_status_candidato_inexistente_levanta(conn: _FakeConn) -> None:
    repo = ConflitoTriagemRepository(conn)
    with pytest.raises(CandidatoConflitoNaoEncontradoError):
        repo.atualizar_status(999, "investigando")


def test_atualizar_status_transicao_invalida_levanta(conn: _FakeConn) -> None:
    repo = ConflitoTriagemRepository(conn)
    with pytest.raises(TriagemError):
        repo.atualizar_status(1, "confirmado")


def test_atualizar_status_descarte_exige_motivo(conn: _FakeConn) -> None:
    repo = ConflitoTriagemRepository(conn)
    with pytest.raises(TriagemError):
        repo.atualizar_status(1, "descartado")


def test_atualizar_status_descarte_motivo_invalido_levanta(conn: _FakeConn) -> None:
    repo = ConflitoTriagemRepository(conn)
    with pytest.raises(TriagemError):
        repo.atualizar_status(1, "descartado", motivo_descarte="motivo qualquer")


def test_atualizar_status_descarte_motivo_valido_funciona(conn: _FakeConn) -> None:
    repo = ConflitoTriagemRepository(conn)
    repo.atualizar_status(
        1, "descartado", motivo_descarte="servidor nao esta mais ativo"
    )
    assert conn.tabela[1] == "descartado"


def test_atualizar_status_aceita_motivos_customizados_no_construtor(conn: _FakeConn) -> None:
    repo = ConflitoTriagemRepository(conn, motivos_descarte=["motivo especifico"])
    repo.atualizar_status(1, "descartado", motivo_descarte="motivo especifico")
    assert conn.tabela[1] == "descartado"


def test_registrar_historico_e_no_op(conn: _FakeConn) -> None:
    repo = ConflitoTriagemRepository(conn)
    assert repo.registrar_historico(1, "aberto", "investigando") is None
    assert conn.commits == 0


def test_resumo_status_conta_por_status() -> None:
    conn = _FakeConn({1: "aberto", 2: "aberto", 3: "investigando"})
    repo = ConflitoTriagemRepository(conn)

    resumo = repo.resumo_status()
    assert resumo["aberto"] == 2
    assert resumo["investigando"] == 1
