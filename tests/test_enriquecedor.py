"""Testes do enriquecedor cadastral (BrasilAPI mockada)."""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes
from extrator.enriquecedor import Enriquecedor


@pytest.fixture
def conn() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    conexao.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conexao)
    conexao.execute(
        "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?)",
        ("98765432000111", "Fornecedor Teste LTDA"),
    )
    conexao.commit()
    return conexao


def test_enriquecer_fornecedor_ativo_salva_cadastro(conn: sqlite3.Connection) -> None:
    dados_api = {
        "situacao_cadastral": 2,
        "descricao_situacao_cadastral": "ATIVA",
        "data_inicio_atividade": "2010-01-01",
        "cnae_fiscal": 6201501,
        "cnae_fiscal_descricao": "Desenvolvimento de programas",
        "capital_social": 100000.0,
        "porte": "DEMAIS",
        "natureza_juridica": "2062",
        "municipio": "Rio de Janeiro",
        "uf": "RJ",
        "qsa": [{"nome": "Socio A"}],
        "cnaes_secundarios": [],
    }
    enriquecedor = Enriquecedor()

    with patch.object(enriquecedor, "consultar_cnpj_brasilapi", return_value=dados_api):
        with patch("extrator.enriquecedor.time.sleep"):
            with patch("extrator.sancoes_ingestao.sincronizar_tem_sancao"):
                resumo = enriquecedor.enriquecer_fornecedor(conn, "98765432000111")

    assert resumo["encontrado"] is True
    assert resumo["ativo"] is True
    row = conn.execute(
        "SELECT situacao_cadastral, municipio FROM fornecedor_cadastro WHERE fornecedor_ni = ?",
        ("98765432000111",),
    ).fetchone()
    assert row is not None
    assert row["municipio"] == "Rio de Janeiro"


def test_enriquecer_fornecedor_nao_encontrado(conn: sqlite3.Connection) -> None:
    enriquecedor = Enriquecedor()

    with patch.object(enriquecedor, "consultar_cnpj_brasilapi", return_value=None):
        with patch("extrator.enriquecedor.time.sleep"):
            resumo = enriquecedor.enriquecer_fornecedor(conn, "98765432000111")

    assert resumo["encontrado"] is False
    cadastro = conn.execute(
        "SELECT COUNT(*) FROM fornecedor_cadastro WHERE fornecedor_ni = ?",
        ("98765432000111",),
    ).fetchone()[0]
    assert cadastro == 0
