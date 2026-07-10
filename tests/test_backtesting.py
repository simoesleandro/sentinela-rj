"""Testes do backtesting contra casos conhecidos (analise/backtesting.py)."""
from __future__ import annotations

import sqlite3

import pytest

from analise.backtesting import executar_backtest
from db.conexao import SCHEMA_PATH, aplicar_migracoes


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(c)
    # limpa casos semeados pelas migrações para controlar o cenário
    c.execute("DELETE FROM casos")
    c.commit()
    yield c
    c.close()


def _caso(c, titulo, cnpj, tipo, ordem=0):
    c.execute(
        "INSERT INTO casos (titulo, fornecedor_nome, fornecedor_cnpj, tipo_anomalia, ordem) "
        "VALUES (?, ?, ?, ?, ?)",
        (titulo, titulo, cnpj, tipo, ordem),
    )


def _contrato_com_alerta(c, pncp, cnpj, valor, tipo_alerta, sev="alta"):
    c.execute("INSERT OR IGNORE INTO fornecedores (ni) VALUES (?)", (cnpj,))
    c.execute(
        "INSERT INTO contratos (numero_controle_pncp, fornecedor_ni, valor_global) VALUES (?,?,?)",
        (pncp, cnpj, valor),
    )
    c.execute(
        "INSERT INTO alertas (numero_controle_pncp, tipo, severidade, status) VALUES (?,?,?, 'aberto')",
        (pncp, tipo_alerta, sev),
    )
    c.commit()


def test_detectado_quando_detector_tematico_dispara(conn):
    _caso(conn, "Caso A", "111", "outlier_valor")
    _contrato_com_alerta(conn, "p1", "111", 10_000_000, "outlier_valor")
    _contrato_com_alerta(conn, "p2", "111", 5_000_000, "capital_social_baixo", "media")

    r = executar_backtest(conn)
    caso = r["casos"][0]
    assert caso["veredito"] == "detectado"
    assert caso["detector_tematico_disparou"] is True
    assert caso["n_detectores"] == 2
    assert caso["valor_flagrado"] == 15_000_000
    assert r["resumo"]["detectados"] == 1


def test_detectado_por_outro_sinal_sem_tematico(conn):
    # Flagrado por outro detector que não o temático: ainda é "detectado",
    # mas detector_tematico_disparou=False (reportado à parte).
    _caso(conn, "Caso B", "222", "concentracao_fornecedor")
    _contrato_com_alerta(conn, "p1", "222", 2_000_000, "outlier_valor")

    r = executar_backtest(conn)
    caso = r["casos"][0]
    assert caso["veredito"] == "detectado"
    assert caso["detector_tematico_disparou"] is False
    assert r["resumo"]["via_tematico"] == 0
    assert r["resumo"]["detectados"] == 1


def test_nao_detectado_sem_alertas(conn):
    _caso(conn, "Caso C", "333", "outlier_valor")
    conn.execute("INSERT INTO fornecedores (ni) VALUES ('333')")
    conn.commit()

    caso = executar_backtest(conn)["casos"][0]
    assert caso["veredito"] == "nao_detectado"
    assert caso["n_detectores"] == 0


def test_caso_sem_cnpj_usa_detector_global(conn):
    _caso(conn, "Padrão X", None, "asfalto_fatiado")
    # alerta de asfalto em qualquer fornecedor
    _contrato_com_alerta(conn, "p1", "999", 1_000_000, "asfalto_fatiado")

    caso = executar_backtest(conn)["casos"][0]
    assert caso["base"] == "padrao"
    assert caso["veredito"] == "detectado"
