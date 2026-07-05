"""Testes para folha_pagamento/repository.py.

SupabaseFolhaPagamentoRepository usa psycopg2.extras.execute_values, que monta a
query final com cur.mogrify/cur.execute reais — não dá para exercitar isso sem uma
conexão de verdade. Por isso estes testes usam uma FakeCursor/FakeConn mínima que
mimetiza a API do psycopg2 (cursor(), execute(), fetchall(), rowcount) e verificam:
(1) a SQL enviada tem ON CONFLICT ... DO NOTHING/DO UPDATE corretos e (2) a contagem
de inseridos é o len() dos ids retornados por RETURNING — não cur.rowcount, que só
refletiria a última página quando execute_values divide a carga em várias.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from folha_pagamento.parser import RegistroFolha
from folha_pagamento.repository import SupabaseFolhaPagamentoRepository


class _FakeCursor:
    """Simula uma tabela folha_mensal com UNIQUE (matricula, tipo_folha, competencia)."""

    def __init__(self, folha_mensal: dict[tuple[str, str, date], int]):
        self._folha_mensal = folha_mensal
        self._proximo_id = max(folha_mensal.values(), default=0) + 1
        self.queries: list[str] = []
        self.rowcount = 0
        self._resultado: list[tuple[int]] = []
        self.connection = type("_FakeRawConn", (), {"encoding": "UTF8"})()

    def execute(self, sql: str | bytes) -> None:
        if isinstance(sql, bytes):
            sql = sql.decode("utf-8")
        self.queries.append(sql)
        # simula o INSERT ... VALUES (...) ON CONFLICT DO NOTHING RETURNING id
        # a partir dos literais já mogrificados pelo execute_values na SQL final.
        self._resultado = []
        if "INSERT INTO folha_mensal" not in sql:
            self.rowcount = 1
            return
        import re

        tuplas = re.findall(r"\(([^()]+)\)", sql.split("VALUES")[1].split("ON CONFLICT")[0])
        for t in tuplas:
            valores = [v.strip().strip("'") for v in t.split(",")]
            matricula, sigla_ua, competencia, tipo_folha = valores[0], valores[1], valores[2], valores[3]
            chave = (matricula, tipo_folha, competencia)
            if chave in self._folha_mensal:
                continue
            self._folha_mensal[chave] = self._proximo_id
            self._resultado.append((self._proximo_id,))
            self._proximo_id += 1
        self.rowcount = len(self._resultado)

    def fetchall(self) -> list[tuple[int]]:
        return self._resultado

    def mogrify(self, template: str, args: Any) -> bytes:
        valores = ", ".join(
            "NULL" if v is None else f"'{v}'" for v in args
        )
        return f"({valores})".encode()


class _FakeConn:
    def __init__(self):
        self.folha_mensal: dict[tuple[str, str, date], int] = {}
        self.servidores: dict[str, str] = {}
        self.orgaos: dict[str, str | None] = {}
        self.commits = 0
        self.last_cursor: _FakeCursor | None = None

    def cursor(self) -> _FakeCursor:
        self.last_cursor = _FakeCursor(self.folha_mensal)
        return self.last_cursor

    def commit(self) -> None:
        self.commits += 1


def _registro(tipo_folha: str = "NORMAL", competencia=date(2021, 6, 1)) -> RegistroFolha:
    return RegistroFolha(
        nome="MARIA DA SILVA",
        matricula="12345",
        sigla_ua="SMS",
        tipo_folha=tipo_folha,
        competencia=competencia,
        remuneracao_bruta=3018.31,
        desconto_previdencia=301.83,
        desconto_ir=150.00,
        outros_descontos=10.50,
        desconto_excedente_teto=0.00,
        remuneracao_liquida=2555.98,
    )


@pytest.fixture
def conn():
    return _FakeConn()


def test_insert_folha_mensal_insere_novos_registros(conn):
    repo = SupabaseFolhaPagamentoRepository(conn)
    inseridos = repo.insert_folha_mensal([_registro()])
    assert inseridos == 1
    assert len(conn.folha_mensal) == 1
    assert conn.commits == 1


def test_insert_folha_mensal_idempotente_reimportar_mesmo_arquivo(conn):
    """Importar o mesmo mês duas vezes não duplica linhas em folha_mensal."""
    repo = SupabaseFolhaPagamentoRepository(conn)
    registros = [_registro()]

    primeira = repo.insert_folha_mensal(registros)
    segunda = repo.insert_folha_mensal(registros)

    assert primeira == 1
    assert segunda == 0
    assert len(conn.folha_mensal) == 1


def test_insert_folha_mensal_matricula_duplicada_tipos_diferentes(conn):
    """Mesma matrícula com TIPO_FOLHA diferente na mesma competência gera linhas distintas."""
    repo = SupabaseFolhaPagamentoRepository(conn)
    registros = [
        _registro(tipo_folha="NORMAL"),
        _registro(tipo_folha="SUPLEMENTO"),
        _registro(tipo_folha="FOLHA DE FERIAS"),
    ]

    inseridos = repo.insert_folha_mensal(registros)

    assert inseridos == 3
    assert len(conn.folha_mensal) == 3


def test_insert_folha_mensal_conta_corretamente_atraves_de_paginas(conn):
    """Contagem correta mesmo quando execute_values divide em várias páginas (page_size baixo).

    cur.rowcount refletiria só a última página — por isso insert_folha_mensal usa
    RETURNING id + fetch=True, que agrega os resultados de todas as páginas.
    """
    repo = SupabaseFolhaPagamentoRepository(conn, batch_size=1)
    registros = [_registro(tipo_folha=f"TIPO_{i}") for i in range(5)]

    inseridos = repo.insert_folha_mensal(registros)

    assert inseridos == 5
    assert len(conn.folha_mensal) == 5


def test_upsert_servidores_em_lote_usa_on_conflict_do_update(conn):
    repo = SupabaseFolhaPagamentoRepository(conn)
    repo.upsert_servidores_em_lote([("12345", "MARIA DA SILVA")])

    sql = conn.last_cursor.queries[0]
    assert "INSERT INTO servidores" in sql
    assert "'12345'" in sql and "'MARIA DA SILVA'" in sql
    assert "ON CONFLICT (matricula) DO UPDATE SET nome_atual = EXCLUDED.nome_atual" in sql
    assert conn.commits == 1


def test_upsert_orgaos_em_lote_usa_on_conflict_do_update(conn):
    repo = SupabaseFolhaPagamentoRepository(conn)
    repo.upsert_orgaos_em_lote([("SMS", None)])

    sql = conn.last_cursor.queries[0]
    assert "INSERT INTO orgaos" in sql
    assert "ON CONFLICT (sigla_ua) DO UPDATE SET nome = EXCLUDED.nome" in sql
    assert conn.commits == 1
