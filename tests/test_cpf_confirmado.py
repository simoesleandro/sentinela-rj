"""Testa a propagação do CPF de sócio confirmado (TSE) para os candidatos do
conflito de interesse. Usa sqlite como stand-in do Postgres — o módulo escolhe o
placeholder de parâmetro conforme o driver."""
from __future__ import annotations

import sqlite3

import pytest

from conflito_interesse.cpf_confirmado import atualizar_cpf_confirmado


@pytest.fixture
def core():
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE socios_cpf_confirmado ("
        "fornecedor_ni TEXT, nome_socio TEXT, cpf TEXT)"
    )
    yield c
    c.close()


@pytest.fixture
def destino():
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE candidatos_conflito_interesse ("
        "fornecedor_ni TEXT, nome_socio TEXT, cpf_socio_confirmado TEXT)"
    )
    yield c
    c.close()


def test_propaga_cpf_por_match_exato(core, destino):
    core.execute(
        "INSERT INTO socios_cpf_confirmado VALUES ('111','JOAO DA SILVA','00112345699')"
    )
    core.commit()
    destino.execute(
        "INSERT INTO candidatos_conflito_interesse (fornecedor_ni, nome_socio) "
        "VALUES ('111','JOAO DA SILVA')"
    )
    # candidato de outro sócio não deve receber CPF
    destino.execute(
        "INSERT INTO candidatos_conflito_interesse (fornecedor_ni, nome_socio) "
        "VALUES ('111','MARIA SOUZA')"
    )
    destino.commit()

    n = atualizar_cpf_confirmado(destino, core)
    assert n == 1
    rows = dict(
        destino.execute(
            "SELECT nome_socio, cpf_socio_confirmado FROM candidatos_conflito_interesse"
        ).fetchall()
    )
    assert rows["JOAO DA SILVA"] == "00112345699"
    assert rows["MARIA SOUZA"] is None


def test_sem_confirmados_retorna_zero(core, destino):
    destino.execute(
        "INSERT INTO candidatos_conflito_interesse (fornecedor_ni, nome_socio) "
        "VALUES ('111','JOAO DA SILVA')"
    )
    destino.commit()
    assert atualizar_cpf_confirmado(destino, core) == 0
