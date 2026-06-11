"""Testes do workflow de triagem de alertas."""
from __future__ import annotations

import sqlite3

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes
from db.triagem import (
    AlertaNaoEncontradoError,
    TriagemError,
    atualizar_status_alerta,
    resumo_status,
)


@pytest.fixture
def conn() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    conexao.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conexao)
    conexao.execute(
        """
        INSERT INTO alertas (
            tipo, severidade, score, descricao, metodologia, valor_referencia, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("outlier_valor", "alta", 0.9, "Teste", "IQR", 1000.0, "aberto"),
    )
    conexao.commit()
    return conexao


def test_transicao_aberto_para_investigando(conn: sqlite3.Connection) -> None:
    resultado = atualizar_status_alerta(
        conn, 1, status="investigando", nota="Iniciada análise manual."
    )
    assert resultado["status"] == "investigando"
    assert len(resultado["historico"]) == 1
    assert resultado["historico"][0]["nota"] == "Iniciada análise manual."


def test_transicao_invalida(conn: sqlite3.Connection) -> None:
    with pytest.raises(TriagemError):
        atualizar_status_alerta(conn, 1, status="confirmado")


def test_resumo_status_conta_fila(conn: sqlite3.Connection) -> None:
    atualizar_status_alerta(conn, 1, status="investigando", nota="ok")
    resumo = resumo_status(conn)
    assert resumo["investigando"] == 1
    assert resumo["fila"] == 1


def test_alerta_inexistente(conn: sqlite3.Connection) -> None:
    with pytest.raises(AlertaNaoEncontradoError):
        atualizar_status_alerta(conn, 999, status="investigando")


def test_descarte_para_investigando(conn: sqlite3.Connection) -> None:
    atualizar_status_alerta(
        conn, 1, status="descartado", motivo_descarte="outro", nota="Sem risco",
    )
    resultado = atualizar_status_alerta(conn, 1, status="investigando", nota="Reabrir")
    assert resultado["status"] == "investigando"
