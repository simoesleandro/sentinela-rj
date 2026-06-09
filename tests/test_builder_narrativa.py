"""Testes de preenchimento de narrativa IA no builder."""
from __future__ import annotations

import sqlite3

import pytest

from analisador.engine import AnomaliaResult
from db.conexao import SCHEMA_PATH
from relatorios.builder import (
    _bloco_narrativa,
    _buscar_narrativa,
    _carregar_narrativas,
    _secao_anomalia,
)


@pytest.fixture
def conn() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    conexao.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conexao.execute(
        """
        INSERT INTO alertas (
            numero_controle_pncp, tipo, severidade, score,
            descricao, metodologia, valor_referencia, narrativa_ia
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PNCP-001",
            "outlier_valor",
            "alta",
            0.95,
            "Valor atipico.",
            "IQR",
            1_000_000.0,
            "Fornecedor com historico atipico no PNCP.",
        ),
    )
    conexao.commit()
    return conexao


def test_carregar_narrativas_indexa_por_tipo_e_pncp(conn: sqlite3.Connection) -> None:
    indice = _carregar_narrativas(conn)
    assert indice[("outlier_valor", "PNCP-001")] == (
        "Fornecedor com historico atipico no PNCP."
    )


def test_secao_anomalia_preenche_narrativa(conn: sqlite3.Connection) -> None:
    anomalia = AnomaliaResult(
        tipo="outlier_valor",
        severidade="alta",
        score=0.95,
        titulo="Contrato atipico",
        descricao="Valor acima do limite.",
        metodologia="IQR",
        contratos=["PNCP-001"],
    )
    indice = _carregar_narrativas(conn)
    narrativa = _buscar_narrativa(anomalia, indice)
    texto = _secao_anomalia(1, anomalia, narrativa)
    assert "Análise IA" in texto
    assert "historico atipico" in texto
    assert "{NARRATIVA}" not in texto


def test_bloco_narrativa_mantem_placeholder_sem_texto() -> None:
    texto = _bloco_narrativa(None)
    assert "{NARRATIVA}" in texto
