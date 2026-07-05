"""Testes para folha_pagamento/repository.py::SqliteFolhaPagamentoRepository.

Implementação de produção para o dado bruto/histórico de folha (SQLite local,
data/folha_pagamento.db) — por isso os testes usam sqlite3 real (":memory:"),
sem fakes/mocks, ao contrário de SupabaseFolhaPagamentoRepository (psycopg2),
que ainda depende de FakeCursor/FakeConn em test_folha_repository.py.
"""
from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from folha_pagamento.repository import AgregadoFolhaMensal, SqliteFolhaPagamentoRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def repo(conn):
    return SqliteFolhaPagamentoRepository(conn)


def _agregado(
    matricula: str = "12345",
    competencia: date = date(2021, 6, 1),
    remuneracao_bruta_total: float = 3518.31,
    excedeu_teto: bool = False,
) -> AgregadoFolhaMensal:
    return AgregadoFolhaMensal(
        matricula=matricula,
        sigla_ua="SMS",
        competencia=competencia,
        remuneracao_bruta_total=remuneracao_bruta_total,
        excedeu_teto=excedeu_teto,
    )


def test_init_cria_schema_idempotente(conn):
    SqliteFolhaPagamentoRepository(conn)
    SqliteFolhaPagamentoRepository(conn)  # não deve levantar erro ao rodar de novo
    tabelas = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"servidores", "orgaos", "folha_mensal"} <= tabelas


def test_upsert_servidores_em_lote_insere(repo, conn):
    repo.upsert_servidores_em_lote([("12345", "MARIA DA SILVA"), ("54321", "JOÃO SOUZA")])

    rows = conn.execute("SELECT matricula, nome_atual FROM servidores ORDER BY matricula").fetchall()
    assert rows == [("12345", "MARIA DA SILVA"), ("54321", "JOÃO SOUZA")]


def test_upsert_servidores_em_lote_atualiza_nome_em_conflito(repo, conn):
    repo.upsert_servidores_em_lote([("12345", "MARIA DA SILVA")])
    repo.upsert_servidores_em_lote([("12345", "MARIA DA SILVA SANTOS")])

    nome = conn.execute(
        "SELECT nome_atual FROM servidores WHERE matricula='12345'"
    ).fetchone()[0]
    assert nome == "MARIA DA SILVA SANTOS"


def test_upsert_orgaos_em_lote_insere(repo, conn):
    repo.upsert_orgaos_em_lote([("SMS", None), ("SME", "Secretaria de Educação")])

    rows = conn.execute("SELECT sigla_ua, nome FROM orgaos ORDER BY sigla_ua").fetchall()
    assert rows == [("SME", "Secretaria de Educação"), ("SMS", None)]


def test_insert_folha_mensal_insere_novos_registros(repo, conn):
    repo.upsert_servidores_em_lote([("12345", "MARIA DA SILVA")])
    repo.upsert_orgaos_em_lote([("SMS", None)])

    inseridos = repo.insert_folha_mensal([_agregado()])

    assert inseridos == 1
    total = conn.execute("SELECT COUNT(*) FROM folha_mensal").fetchone()[0]
    assert total == 1


def test_insert_folha_mensal_persiste_colunas_agregadas(repo, conn):
    repo.upsert_servidores_em_lote([("12345", "MARIA DA SILVA")])
    repo.upsert_orgaos_em_lote([("SMS", None)])

    repo.insert_folha_mensal([_agregado(remuneracao_bruta_total=4518.81, excedeu_teto=True)])

    row = conn.execute(
        "SELECT matricula, sigla_ua, competencia, remuneracao_bruta_total, excedeu_teto "
        "FROM folha_mensal"
    ).fetchone()
    assert row[0] == "12345"
    assert row[1] == "SMS"
    assert row[3] == 4518.81
    assert row[4] == 1


def test_insert_folha_mensal_idempotente_reimportar_mesmo_arquivo(repo, conn):
    """Importar o mesmo mês duas vezes não duplica linhas em folha_mensal."""
    repo.upsert_servidores_em_lote([("12345", "MARIA DA SILVA")])
    repo.upsert_orgaos_em_lote([("SMS", None)])
    registros = [_agregado()]

    primeira = repo.insert_folha_mensal(registros)
    segunda = repo.insert_folha_mensal(registros)

    assert primeira == 1
    assert segunda == 0
    total = conn.execute("SELECT COUNT(*) FROM folha_mensal").fetchone()[0]
    assert total == 1


def test_insert_folha_mensal_matriculas_diferentes_geram_linhas_distintas(repo, conn):
    repo.upsert_servidores_em_lote([("12345", "A"), ("54321", "B"), ("99999", "C")])
    repo.upsert_orgaos_em_lote([("SMS", None)])
    registros = [
        _agregado(matricula="12345"),
        _agregado(matricula="54321"),
        _agregado(matricula="99999"),
    ]

    inseridos = repo.insert_folha_mensal(registros)

    assert inseridos == 3
    total = conn.execute("SELECT COUNT(*) FROM folha_mensal").fetchone()[0]
    assert total == 3


def test_insert_folha_mensal_conta_corretamente_em_lote_unico(repo, conn):
    """executemany soma as modificações de todas as linhas do lote em rowcount."""
    repo.upsert_servidores_em_lote([(f"MAT_{i}", "X") for i in range(5)])
    repo.upsert_orgaos_em_lote([("SMS", None)])
    registros = [_agregado(matricula=f"MAT_{i}") for i in range(5)]

    inseridos = repo.insert_folha_mensal(registros)

    assert inseridos == 5
