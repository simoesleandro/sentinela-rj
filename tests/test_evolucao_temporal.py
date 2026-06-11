"""Testes do detector de evolução temporal."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from analisador.evolucao_temporal import detectar
from db.conexao import SCHEMA_PATH, aplicar_migracoes


@pytest.fixture
def conn() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    conexao.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conexao)
    conexao.execute(
        "INSERT INTO orgaos (cnpj, razao_social) VALUES (?, ?)",
        ("12345678000199", "Prefeitura Teste"),
    )
    conexao.execute(
        "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?)",
        ("98765432000111", "Fornecedor Acelerado"),
    )
    ref = date(2025, 6, 1)
    for i in range(2):
        d = ref - timedelta(days=120 + i * 10)
        conexao.execute(
            """
            INSERT INTO contratos (
                numero_controle_pncp, orgao_cnpj, fornecedor_ni,
                objeto, valor_global, data_assinatura
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"PNCP-OLD-{i}", "12345678000199", "98765432000111", "Serviço", 100_000.0, d.isoformat()),
        )
    for i in range(8):
        d = ref - timedelta(days=10 + i * 5)
        conexao.execute(
            """
            INSERT INTO contratos (
                numero_controle_pncp, orgao_cnpj, fornecedor_ni,
                objeto, valor_global, data_assinatura
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"PNCP-NEW-{i}", "12345678000199", "98765432000111", "Serviço", 200_000.0, d.isoformat()),
        )
    conexao.commit()
    return conexao


def test_detecta_aceleracao_contratual(conn: sqlite3.Connection) -> None:
    resultados = detectar(conn)
    assert len(resultados) == 1
    evo = resultados[0]
    assert evo.tipo == "evolucao_temporal_fornecedor"
    assert evo.metricas["qtd_recente"] == 8
    assert evo.metricas["qtd_anterior"] == 2
    assert len(evo.contratos) == 8
