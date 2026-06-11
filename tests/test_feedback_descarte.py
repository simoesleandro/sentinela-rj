"""Testes de feedback de falso positivo ao descartar alertas."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from analise.motivos_descarte import extrair_motivo_descarte, formatar_nota_descarte
from db.conexao import SCHEMA_PATH, aplicar_migracoes
from db.triagem import TriagemError, atualizar_status_alerta


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


def test_formatar_e_extrair_motivo() -> None:
    nota = formatar_nota_descarte("valor_rotineiro", "Compra recorrente")
    assert nota.startswith("[FP:valor_rotineiro]")
    assert extrair_motivo_descarte(nota) == "valor_rotineiro"


def test_descarte_exige_motivo(conn: sqlite3.Connection) -> None:
    with pytest.raises(TriagemError, match="motivo"):
        atualizar_status_alerta(conn, 1, status="descartado", nota="Falso alarme")


def test_descarte_com_motivo(conn: sqlite3.Connection) -> None:
    resultado = atualizar_status_alerta(
        conn,
        1,
        status="descartado",
        motivo_descarte="duplicado",
        nota="Já analisado",
    )
    assert resultado["status"] == "descartado"
    assert "[FP:duplicado]" in resultado["historico"][0]["nota"]


@pytest.fixture
def client(tmp_path: Path):
    import web_app as wa

    db_file = tmp_path / "test.db"
    wa.DB_PATH = db_file
    wa._migracoes_aplicadas = False
    conn = wa.get_db()
    conn.execute(
        """
        INSERT INTO alertas (
            tipo, severidade, score, descricao, metodologia, valor_referencia, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("outlier_valor", "alta", 0.9, "Teste", "IQR", 1000.0, "aberto"),
    )
    atualizar_status_alerta(
        conn,
        1,
        status="descartado",
        motivo_descarte="valor_rotineiro",
    )
    conn.close()

    with wa.app.test_client() as test_client:
        yield test_client


def test_api_feedback_descartes(client) -> None:
    res = client.get("/api/alertas/feedback/descartes")
    assert res.status_code == 200
    data = res.get_json()
    assert data["total_descartes"] == 1
    assert data["por_motivo"].get("valor_rotineiro") == 1
    assert data["por_tipo"].get("outlier_valor") == 1
