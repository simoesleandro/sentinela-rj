"""Testes do detector de outliers com fixture determinística."""
from __future__ import annotations

import sqlite3

import pytest

from analisador.outliers import detectar
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
        "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?), (?, ?)",
        ("11111111000111", "Fornecedor Normal", "22222222000122", "Fornecedor Outlier"),
    )
    valores_normais = [
        100_000.0, 102_000.0, 104_000.0, 106_000.0,
        108_000.0, 110_000.0, 112_000.0, 114_000.0,
    ]
    for i, valor in enumerate(valores_normais, start=1):
        conexao.execute(
            """
            INSERT INTO contratos (
                numero_controle_pncp, orgao_cnpj, fornecedor_ni,
                objeto, valor_global, data_assinatura, categoria_processo_nome
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"PNCP-NORM-{i:02d}",
                "12345678000199",
                "11111111000111",
                "Serviços gerais",
                valor,
                f"2025-{i:02d}-01",
                "Serviços",
            ),
        )
    conexao.execute(
        """
        INSERT INTO contratos (
            numero_controle_pncp, orgao_cnpj, fornecedor_ni,
            objeto, valor_global, data_assinatura, categoria_processo_nome
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PNCP-OUTLIER-01",
            "12345678000199",
            "22222222000122",
            "Contrato atípico",
            50_000_000.0,
            "2025-06-01",
            "Serviços",
        ),
    )
    conexao.commit()
    return conexao


def test_outlier_detectado_na_categoria(conn: sqlite3.Connection) -> None:
    resultados = detectar(conn)
    assert len(resultados) == 1
    outlier = resultados[0]
    assert outlier.contratos == ["PNCP-OUTLIER-01"]
    assert outlier.tipo == "outlier_valor"
    assert outlier.severidade in ("alta", "media", "baixa")
    assert outlier.score > 0


def test_contratos_normais_nao_flagrados(conn: sqlite3.Connection) -> None:
    resultados = detectar(conn)
    pncps = {p for r in resultados for p in r.contratos}
    assert "PNCP-NORM-01" not in pncps
    assert "PNCP-NORM-04" not in pncps
