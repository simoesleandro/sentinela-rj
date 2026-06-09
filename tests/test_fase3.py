"""Testes Fase 3 — multi-município, CEIS/CNEP, backfill e Transparência RJ."""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes
from extrator.config_municipio import municipio_ibge
from extrator.sancoes_ingestao import ingestir_csv, sincronizar_tem_sancao
from extrator.transparencia_rj import cruzar_contratos, ingestir_empenhos


@pytest.fixture
def conn() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    conexao.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conexao)
    conexao.execute(
        "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?), (?, ?)",
        ("12345678000199", "Fornecedor Sancionado", "98765432000111", "Fornecedor OK"),
    )
    conexao.execute(
        """
        INSERT INTO contratos (
            numero_controle_pncp, fornecedor_ni, valor_global, objeto
        ) VALUES (?, ?, ?, ?)
        """,
        ("PNCP-T1", "98765432000111", 100_000.0, "Serviços"),
    )
    conexao.commit()
    return conexao


def test_municipio_ibge_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUNICIPIO_IBGE", raising=False)
    assert municipio_ibge() == "3304557"


def test_ingestao_ceis_csv(conn: sqlite3.Connection) -> None:
    csv_text = (
        "CNPJ OU CPF DO SANCIONADO;NOME DO SANCIONADO;DATA INICIO SANCAO\n"
        "12345678000199;Empresa X;2024-01-01\n"
    )
    resumo = ingestir_csv(conn, csv_text, "CEIS")
    assert resumo["inseridos"] == 1
    flag = conn.execute(
        "SELECT tem_sancao FROM fornecedores WHERE ni = ?",
        ("12345678000199",),
    ).fetchone()[0]
    assert flag == 1


def test_sincronizar_tem_sancao_desmarca_sem_registro(conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE fornecedores SET tem_sancao = 1 WHERE ni = '98765432000111'"
    )
    conn.commit()
    sincronizar_tem_sancao(conn)
    flag = conn.execute(
        "SELECT tem_sancao FROM fornecedores WHERE ni = '98765432000111'"
    ).fetchone()[0]
    assert flag == 0


def test_transparencia_cruzamento_valor(conn: sqlite3.Connection) -> None:
    csv_text = (
        "cnpj;valor;data;historico\n"
        "98765432000111;100000;2025-01-01;Empenho teste\n"
    )
    ingestir_empenhos(conn, csv_text)
    resumo = cruzar_contratos(conn, tolerancia=0.01)
    assert resumo["cruzamentos"] == 1


def test_backfill_chama_coletar_por_janela() -> None:
    from extrator.backfill import executar_backfill

    chamadas: list[tuple[str, str]] = []

    def _fake_coletar(di: str, df: str) -> dict:
        chamadas.append((di, df))
        return {"brutos_varridos": 10, "salvos_rio": 1, "paginas_falhas": []}

    with patch("extrator.backfill.coletar", side_effect=_fake_coletar):
        resumo = executar_backfill("20250101", "20250215")

    assert len(chamadas) >= 2
    assert resumo["salvos_municipio"] >= 2
