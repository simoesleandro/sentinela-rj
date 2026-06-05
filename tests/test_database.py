"""Testes unitários do gerenciador de banco de dados."""
from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from db.database import GerenciadorBanco

_TABELA = "despesas"


@pytest.fixture
def gerenciador() -> GerenciadorBanco:
    return GerenciadorBanco(":memory:")


@pytest.fixture
def contratos_mock() -> list[dict[str, Any]]:
    return [
        {
            "numero_controle_pncp": "PNCP-2026-0001",
            "orgao_cnpj": "12345678000199",
            "fornecedor_ni": "98765432000111",
            "valor_global": 150000.0,
            "objeto": "Aquisição de equipamentos de TI",
            "data_assinatura": "2026-01-15",
        },
    ]


def _consultar_registros(
    gerenciador: GerenciadorBanco,
    tabela: str,
) -> list[dict[str, Any]]:
    conn = gerenciador._obter_conexao()
    conn.row_factory = sqlite3.Row
    linhas = conn.execute(f'SELECT * FROM "{tabela}"').fetchall()
    return [dict(linha) for linha in linhas]


def test_salvar_despesas_sucesso(
    gerenciador: GerenciadorBanco,
    contratos_mock: list[dict[str, Any]],
) -> None:
    gerenciador.salvar_despesas(contratos_mock, _TABELA)

    salvo = _consultar_registros(gerenciador, _TABELA)
    assert len(salvo) == 1
    assert salvo[0]["numero_controle_pncp"] == "PNCP-2026-0001"
    assert salvo[0]["orgao_cnpj"] == "12345678000199"
    assert float(salvo[0]["valor_global"]) == 150000.0


def test_salvar_despesas_lista_vazia(gerenciador: GerenciadorBanco) -> None:
    with pytest.raises(ValueError, match="Lista vazia"):
        gerenciador.salvar_despesas([], _TABELA)
