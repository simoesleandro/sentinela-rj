"""Testes do grafo investigativo."""
from __future__ import annotations

import sqlite3

import pytest

from analise.grafo import (
    GrafoNaoEncontradoError,
    montar_grafo_alerta,
    montar_grafo_fornecedor,
)
from db.conexao import SCHEMA_PATH


def _seed(conn: sqlite3.Connection) -> int:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO orgaos (cnpj, razao_social) VALUES (?, ?)",
        ("12345678000199", "Prefeitura Teste"),
    )
    conn.execute(
        "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?)",
        ("98765432000111", "Fornecedor Alfa"),
    )
    conn.execute(
        """
        INSERT INTO contratos (
            numero_controle_pncp, orgao_cnpj, fornecedor_ni,
            objeto, valor_global
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("PNCP-001", "12345678000199", "98765432000111", "Serviços", 2_000_000.0),
    )
    conn.execute(
        """
        INSERT INTO fornecedor_cadastro (fornecedor_ni, socios)
        VALUES (?, ?)
        """,
        (
            "98765432000111",
            '[{"nome_socio": "Joao da Silva"}]',
        ),
    )
    cur = conn.execute(
        """
        INSERT INTO alertas (
            numero_controle_pncp, tipo, severidade, score,
            descricao, metodologia, valor_referencia
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("PNCP-001", "outlier_valor", "alta", 0.9, "x", "y", 2_000_000.0),
    )
    conn.commit()
    return int(cur.lastrowid)


@pytest.fixture
def conn() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    _seed(conexao)
    return conexao


def test_grafo_fornecedor_tem_quatro_tipos(conn: sqlite3.Connection) -> None:
    dados = montar_grafo_fornecedor(conn, "98765432000111")
    tipos = {n["tipo"] for n in dados["nodes"]}
    assert tipos >= {"fornecedor", "orgao", "contrato", "socio"}
    assert len(dados["edges"]) >= 3


def test_grafo_alerta_usa_fornecedor_do_contrato(conn: sqlite3.Connection) -> None:
    dados = montar_grafo_alerta(conn, 1)
    assert dados["meta"]["alerta_id"] == 1
    assert any(n["tipo"] == "fornecedor" for n in dados["nodes"])


def test_grafo_fornecedor_inexistente(conn: sqlite3.Connection) -> None:
    with pytest.raises(GrafoNaoEncontradoError):
        montar_grafo_fornecedor(conn, "00000000000000")
