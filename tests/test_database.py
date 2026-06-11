"""Testes do gerenciador de narrativas IA."""
from __future__ import annotations

import sqlite3

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes
from db.narrativa import GerenciadorNarrativa


@pytest.fixture
def gerenciador() -> GerenciadorNarrativa:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conn)
    conn.commit()
    return GerenciadorNarrativa(connection=conn)


def _inserir_alerta(conn: sqlite3.Connection, *, narrativa: str | None = None) -> int:
    conn.execute(
        """
        INSERT INTO alertas (
            numero_controle_pncp, tipo, severidade, descricao,
            metodologia, valor_referencia, narrativa_ia
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("PNCP-1", "outlier", "alta", "Teste", "iqr", 1000.0, narrativa),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM alertas ORDER BY id DESC LIMIT 1").fetchone()
    assert row is not None
    return int(row[0])


def test_listar_sem_narrativa(gerenciador: GerenciadorNarrativa) -> None:
    gerenciador.garantir_tabela_anomalias()
    conn = gerenciador._obter_conexao()
    _inserir_alerta(conn, narrativa=None)
    _inserir_alerta(conn, narrativa="já tem texto")

    pendentes = gerenciador.listar_anomalias_sem_narrativa(limite=10)
    assert len(pendentes) == 1
    assert pendentes[0]["numero_controle_pncp"] == "PNCP-1"


def test_atualizar_narrativa(gerenciador: GerenciadorNarrativa) -> None:
    gerenciador.garantir_tabela_anomalias()
    conn = gerenciador._obter_conexao()
    alerta_id = _inserir_alerta(conn, narrativa=None)

    gerenciador.atualizar_narrativa_anomalia(alerta_id, "Narrativa gerada pela IA.")

    row = conn.execute(
        "SELECT narrativa_ia FROM alertas WHERE id = ?",
        (alerta_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == "Narrativa gerada pela IA."


def test_atualizar_narrativa_id_invalido(gerenciador: GerenciadorNarrativa) -> None:
    with pytest.raises(ValueError, match="positivo"):
        gerenciador.atualizar_narrativa_anomalia(0, "x")
