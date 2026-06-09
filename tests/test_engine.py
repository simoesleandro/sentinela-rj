"""Testes do motor de análise unificado."""
from __future__ import annotations

import sqlite3

import pytest

from analisador.engine import AnomaliaResult, persistir_alertas


@pytest.fixture
def conn() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    conexao.execute(
        """
        CREATE TABLE alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_controle_pncp TEXT,
            tipo TEXT,
            severidade TEXT,
            score REAL,
            descricao TEXT,
            metodologia TEXT,
            valor_referencia REAL,
            status TEXT DEFAULT 'aberto',
            narrativa_ia TEXT
        )
        """
    )
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
