"""Testes do motor de análise unificado."""
from __future__ import annotations

import sqlite3

import pytest

from analisador.engine import AnomaliaResult, persistir_alertas
from db.conexao import SCHEMA_PATH, aplicar_migracoes


@pytest.fixture
def conn() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    conexao.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conexao)
    return conexao


def test_persistir_alertas_grava_score(conn: sqlite3.Connection) -> None:
    anomalias = [
        AnomaliaResult(
            tipo="outlier_valor",
            severidade="alta",
            score=0.891,
            titulo="Valor atipico",
            descricao="Z-score elevado",
            metodologia="IQR + Z-score",
            contratos=["PNCP-001"],
            valor_referencia=1_000_000.0,
        )
    ]
    n = persistir_alertas(conn, anomalias)
    row = conn.execute("SELECT score, tipo FROM alertas").fetchone()
    assert n == 1
    assert row[0] == pytest.approx(0.891)
    assert row[1] == "outlier_valor"


def test_reanalise_preserva_status_e_narrativa(conn: sqlite3.Connection) -> None:
    anomalias = [
        AnomaliaResult(
            tipo="outlier_valor",
            severidade="alta",
            score=0.5,
            titulo="Valor atipico",
            descricao="v1",
            metodologia="IQR",
            contratos=["PNCP-001"],
            valor_referencia=1_000_000.0,
        )
    ]
    persistir_alertas(conn, anomalias)
    conn.execute(
        """
        UPDATE alertas
        SET status = 'investigando', narrativa_ia = 'Laudo preservado'
        WHERE numero_controle_pncp = ? AND tipo = ?
        """,
        ("PNCP-001", "outlier_valor"),
    )
    conn.commit()

    anomalias[0].score = 0.95
    anomalias[0].descricao = "v2"
    persistir_alertas(conn, anomalias)

    row = conn.execute(
        "SELECT status, narrativa_ia, score, descricao FROM alertas"
    ).fetchone()
    assert row["status"] == "investigando"
    assert row["narrativa_ia"] == "Laudo preservado"
    assert row["score"] == pytest.approx(0.95)
    assert row["descricao"] == "v2"
