"""Testes para conflito_interesse/repository.py (CandidatoConflitoRepository).

Mesma abordagem usada para SupabaseFolhaPagamentoRepository: como
psycopg2.extras.execute_values depende de cur.mogrify (só existe em cursores
psycopg2 reais), usamos uma FakeCursor/FakeConn que mimetiza o suficiente da
API do psycopg2 para exercitar a SQL real gerada por execute_values.
"""
from __future__ import annotations

from typing import Any

import pytest

from conflito_interesse.matcher import CandidatoConflito
from conflito_interesse.repository import CandidatoConflitoRepository


class _FakeCursor:
    """Simula a tabela candidatos_conflito_interesse com UNIQUE (fornecedor_ni, matricula_servidor)."""

    def __init__(self, tabela: dict[tuple[str, str], int]):
        self._tabela = tabela
        self._proximo_id = max(tabela.values(), default=0) + 1
        self.queries: list[str] = []
        self._resultado: list[tuple[int]] = []
        self.connection = type("_FakeRawConn", (), {"encoding": "UTF8"})()

    def execute(self, sql: str | bytes) -> None:
        if isinstance(sql, bytes):
            sql = sql.decode("utf-8")
        self.queries.append(sql)
        self._resultado = []
        if "INSERT INTO candidatos_conflito_interesse" not in sql:
            return
        import re

        tuplas = re.findall(r"\(([^()]+)\)", sql.split("VALUES")[1].split("ON CONFLICT")[0])
        for t in tuplas:
            valores = [v.strip().strip("'") for v in t.split(",")]
            fornecedor_ni, matricula_servidor = valores[0], valores[3]
            chave = (fornecedor_ni, matricula_servidor)
            if chave in self._tabela:
                continue
            self._tabela[chave] = self._proximo_id
            self._resultado.append((self._proximo_id,))
            self._proximo_id += 1

    def fetchall(self) -> list[tuple[int]]:
        return self._resultado

    def mogrify(self, template: str, args: Any) -> bytes:
        valores = ", ".join("NULL" if v is None else f"'{v}'" for v in args)
        return f"({valores})".encode()


class _FakeConn:
    def __init__(self):
        self.tabela: dict[tuple[str, str], int] = {}
        self.commits = 0
        self.last_cursor: _FakeCursor | None = None

    def cursor(self) -> _FakeCursor:
        self.last_cursor = _FakeCursor(self.tabela)
        return self.last_cursor

    def commit(self) -> None:
        self.commits += 1


def _candidato(
    fornecedor_ni: str = "12345678000199",
    matricula_servidor: str = "0001",
    score: float = 92.5,
) -> CandidatoConflito:
    return CandidatoConflito(
        fornecedor_ni=fornecedor_ni,
        nome_socio="MARIA DA SILVA SANTOS",
        qualificacao_socio="Presidente",
        matricula_servidor=matricula_servidor,
        nome_servidor="MARIA SILVA SANTOS",
        sigla_ua=None,
        score_similaridade=score,
    )


@pytest.fixture
def conn():
    return _FakeConn()


def test_salvar_candidatos_insere_novos(conn):
    repo = CandidatoConflitoRepository(conn)
    inseridos = repo.salvar_candidatos([_candidato()])

    assert inseridos == 1
    assert len(conn.tabela) == 1
    assert conn.commits == 1


def test_salvar_candidatos_idempotente_nao_duplica(conn):
    repo = CandidatoConflitoRepository(conn)
    registros = [_candidato()]

    primeira = repo.salvar_candidatos(registros)
    segunda = repo.salvar_candidatos(registros)

    assert primeira == 1
    assert segunda == 0
    assert len(conn.tabela) == 1


def test_salvar_candidatos_matriculas_diferentes_mesmo_fornecedor(conn):
    repo = CandidatoConflitoRepository(conn)
    registros = [
        _candidato(matricula_servidor="0001"),
        _candidato(matricula_servidor="0002"),
    ]

    inseridos = repo.salvar_candidatos(registros)

    assert inseridos == 2
    assert len(conn.tabela) == 2


def test_salvar_candidatos_lista_vazia_nao_chama_execute_values(conn):
    repo = CandidatoConflitoRepository(conn)
    inseridos = repo.salvar_candidatos([])

    assert inseridos == 0
    assert conn.commits == 0
    assert conn.last_cursor is None


def test_salvar_candidatos_usa_sql_correta(conn):
    repo = CandidatoConflitoRepository(conn)
    repo.salvar_candidatos([_candidato()])

    sql = conn.last_cursor.queries[0]
    assert "INSERT INTO candidatos_conflito_interesse" in sql
    assert "ON CONFLICT (fornecedor_ni, matricula_servidor) DO NOTHING" in sql
    assert "RETURNING id" in sql
