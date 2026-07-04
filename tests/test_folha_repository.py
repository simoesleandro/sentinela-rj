"""Testes para folha_pagamento/repository.py.

Usa sqlite3 (paramstyle '?') como substituto do Postgres/Supabase para exercitar
a mesma sintaxe SQL (INSERT ... ON CONFLICT ... DO NOTHING) sem depender de uma
instância real do Supabase. SupabaseFolhaPagamentoRepository só assume uma conexão
DBAPI com .cursor()/.commit() — o paramstyle é o único ponto de variação.
"""
from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from folha_pagamento.parser import RegistroFolha
from folha_pagamento.repository import SupabaseFolhaPagamentoRepository

sqlite3.register_adapter(date, lambda d: d.isoformat())


class _SQLiteFolhaPagamentoRepository(SupabaseFolhaPagamentoRepository):
    PLACEHOLDER = "?"


_SCHEMA = """
CREATE TABLE servidores (
    matricula       TEXT PRIMARY KEY,
    nome_atual      TEXT NOT NULL
);
CREATE TABLE orgaos (
    sigla_ua        TEXT PRIMARY KEY,
    nome            TEXT
);
CREATE TABLE folha_mensal (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula                   TEXT NOT NULL REFERENCES servidores(matricula),
    sigla_ua                    TEXT NOT NULL REFERENCES orgaos(sigla_ua),
    competencia                 TEXT NOT NULL,
    tipo_folha                  TEXT NOT NULL,
    remuneracao_bruta           NUMERIC,
    desconto_previdencia        NUMERIC,
    desconto_ir                 NUMERIC,
    outros_descontos            NUMERIC,
    desconto_excedente_teto     NUMERIC,
    remuneracao_liquida         NUMERIC,
    UNIQUE (matricula, tipo_folha, competencia)
);
"""


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    r = _SQLiteFolhaPagamentoRepository(conn)
    r.upsert_servidor("12345", "MARIA DA SILVA")
    r.upsert_orgao("SMS", None)
    yield r
    conn.close()


def _registro(tipo_folha: str = "NORMAL", competencia: date = date(2021, 6, 1)) -> RegistroFolha:
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


def test_upsert_servidor_e_orgao_persistem(repo):
    cur = repo._conn.cursor()
    assert cur.execute("SELECT nome_atual FROM servidores WHERE matricula='12345'").fetchone()[0] == (
        "MARIA DA SILVA"
    )
    assert cur.execute("SELECT sigla_ua FROM orgaos WHERE sigla_ua='SMS'").fetchone()[0] == "SMS"


def test_upsert_servidor_atualiza_nome_em_conflito(repo):
    repo.upsert_servidor("12345", "MARIA DA SILVA SANTOS")
    cur = repo._conn.cursor()
    nome = cur.execute("SELECT nome_atual FROM servidores WHERE matricula='12345'").fetchone()[0]
    assert nome == "MARIA DA SILVA SANTOS"


def test_insert_folha_mensal_insere_novos_registros(repo):
    inseridos = repo.insert_folha_mensal([_registro()])
    assert inseridos == 1
    total = repo._conn.cursor().execute("SELECT COUNT(*) FROM folha_mensal").fetchone()[0]
    assert total == 1


def test_insert_folha_mensal_idempotente_reimportar_mesmo_arquivo(repo):
    """Importar o mesmo mês duas vezes não duplica linhas em folha_mensal."""
    registros = [_registro()]

    primeira = repo.insert_folha_mensal(registros)
    segunda = repo.insert_folha_mensal(registros)

    assert primeira == 1
    assert segunda == 0
    total = repo._conn.cursor().execute("SELECT COUNT(*) FROM folha_mensal").fetchone()[0]
    assert total == 1


def test_insert_folha_mensal_matricula_duplicada_tipos_diferentes(repo):
    """Mesma matrícula com TIPO_FOLHA diferente na mesma competência gera linhas distintas."""
    registros = [
        _registro(tipo_folha="NORMAL"),
        _registro(tipo_folha="SUPLEMENTO"),
        _registro(tipo_folha="FOLHA DE FERIAS"),
    ]

    inseridos = repo.insert_folha_mensal(registros)

    assert inseridos == 3
    total = repo._conn.cursor().execute("SELECT COUNT(*) FROM folha_mensal").fetchone()[0]
    assert total == 3
