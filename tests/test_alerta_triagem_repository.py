"""Caracterização: AlertaTriagemRepository deve se comportar exatamente como
as funções livres de db/triagem.py que ele encapsula — prova de que a
extração de db/triagem_core.py não mudou o comportamento de alertas.
"""
from __future__ import annotations

import sqlite3

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes
from db.triagem import AlertaTriagemRepository, TriagemError
from db.triagem_core import TriagemRepository


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


def test_satisfaz_protocolo_triagem_repository(conn: sqlite3.Connection) -> None:
    repo = AlertaTriagemRepository(conn)
    assert isinstance(repo, TriagemRepository)


def test_atualizar_status_muda_status_e_grava_historico(conn: sqlite3.Connection) -> None:
    repo = AlertaTriagemRepository(conn)
    repo.atualizar_status(1, "investigando", nota="Iniciada análise manual.")

    row = conn.execute("SELECT status FROM alertas WHERE id = 1").fetchone()
    assert row["status"] == "investigando"

    historico = conn.execute(
        "SELECT status_novo, nota FROM alertas_historico WHERE alerta_id = 1"
    ).fetchall()
    assert len(historico) == 1
    assert historico[0]["status_novo"] == "investigando"
    assert historico[0]["nota"] == "Iniciada análise manual."


def test_atualizar_status_transicao_invalida_levanta(conn: sqlite3.Connection) -> None:
    repo = AlertaTriagemRepository(conn)
    with pytest.raises(TriagemError):
        repo.atualizar_status(1, "confirmado")


def test_atualizar_status_descarte_exige_motivo(conn: sqlite3.Connection) -> None:
    repo = AlertaTriagemRepository(conn)
    with pytest.raises(TriagemError):
        repo.atualizar_status(1, "descartado")


def test_resumo_status_conta_fila(conn: sqlite3.Connection) -> None:
    repo = AlertaTriagemRepository(conn)
    repo.atualizar_status(1, "investigando", nota="ok")

    resumo = repo.resumo_status()
    assert resumo["investigando"] == 1
    assert resumo["fila"] == 1


def test_registrar_historico_insere_linha_avulsa(conn: sqlite3.Connection) -> None:
    repo = AlertaTriagemRepository(conn)
    repo.registrar_historico(1, "aberto", "investigando", nota="Anotação manual")

    historico = conn.execute(
        "SELECT status_anterior, status_novo, nota FROM alertas_historico WHERE alerta_id = 1"
    ).fetchall()
    assert len(historico) == 1
    assert historico[0]["status_anterior"] == "aberto"
    assert historico[0]["nota"] == "Anotação manual"
