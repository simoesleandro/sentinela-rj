"""Testes do comparador multi-fornecedor."""
from __future__ import annotations

import sqlite3

import pytest

from analise.comparador import ComparadorError, montar_comparacao
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
    for ni, nome in (
        ("11111111000111", "Empresa A"),
        ("22222222000122", "Empresa B"),
    ):
        conexao.execute(
            "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?)",
            (ni, nome),
        )
        conexao.execute(
            """
            INSERT INTO contratos (
                numero_controle_pncp, orgao_cnpj, fornecedor_ni,
                objeto, valor_global, data_assinatura
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"PNCP-{ni[-4:]}", "12345678000199", ni, "Serviços", 500_000.0, "2025-01-01"),
        )
        conexao.execute(
            """
            INSERT INTO alertas (
                numero_controle_pncp, tipo, severidade, score,
                descricao, metodologia, valor_referencia
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"PNCP-{ni[-4:]}", "outlier_valor", "alta", 0.9, "Alerta", "IQR", 500_000.0),
        )
    conexao.execute(
        """
        INSERT INTO fornecedor_cadastro (fornecedor_ni, socios) VALUES (?, ?), (?, ?)
        """,
        (
            "11111111000111",
            '[{"nome_socio": "Joao da Silva"}]',
            "22222222000122",
            '[{"nome_socio": "Joao da Silva"}]',
        ),
    )
    conexao.commit()
    return conexao


def test_montar_comparacao_dois_fornecedores(conn: sqlite3.Connection) -> None:
    dados = montar_comparacao(conn, ["11111111000111", "22222222000122"])
    assert len(dados["fornecedores"]) == 2
    assert dados["fornecedores"][0]["resumo"]["total_contratos"] == 1
    assert len(dados["vinculos"]["socios_compartilhados"]) == 1


def test_comparador_exige_minimo(conn: sqlite3.Connection) -> None:
    with pytest.raises(ComparadorError):
        montar_comparacao(conn, ["11111111000111"])


def test_comparador_fornecedor_inexistente(conn: sqlite3.Connection) -> None:
    with pytest.raises(ComparadorError, match="não encontrado"):
        montar_comparacao(conn, ["11111111000111", "00000000000000"])
