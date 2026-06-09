"""Testes de fumaça dos detectores de anomalias."""
from __future__ import annotations

import sqlite3

import pytest

from analisador import (
    concentracao,
    fracionamento,
    licitacao,
    outliers,
    sancoes,
    socios,
)
from analisador.engine import AnomaliaResult
from db.conexao import SCHEMA_PATH, aplicar_migracoes

_DETECTORES = (
    ("outliers", outliers.detectar),
    ("concentracao", concentracao.detectar),
    ("licitacao", licitacao.detectar),
    ("fracionamento", fracionamento.detectar),
    ("sancoes", sancoes.detectar),
    ("socios", socios.detectar),
)


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
        ("98765432000111", "Fornecedor Teste"),
    )
    conexao.execute(
        """
        INSERT INTO contratos (
            numero_controle_pncp, orgao_cnpj, fornecedor_ni,
            objeto, valor_global, data_assinatura, categoria_processo_nome
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PNCP-001",
            "12345678000199",
            "98765432000111",
            "Serviços gerais",
            500_000.0,
            "2025-06-01",
            "Serviços",
        ),
    )
    conexao.commit()
    return conexao


@pytest.mark.parametrize("nome,detectar", _DETECTORES)
def test_detector_retorna_lista(
    conn: sqlite3.Connection,
    nome: str,
    detectar,
) -> None:
    resultados = detectar(conn)
    assert isinstance(resultados, list)
    for item in resultados:
        assert isinstance(item, AnomaliaResult)
        assert item.tipo
        assert item.severidade in ("baixa", "media", "alta")
