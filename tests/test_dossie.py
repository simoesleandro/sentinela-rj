"""Testes do dossiê investigativo exportável."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from db.conexao import SCHEMA_PATH
from relatorios.dossie import (
    DossieNaoEncontradoError,
    carregar_dossie,
    exportar_dossie,
    renderizar_markdown,
    renderizar_pdf,
)


def _criar_banco(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    for stmt in (
        "ALTER TABLE fornecedores ADD COLUMN tem_sancao INTEGER DEFAULT 0",
        "ALTER TABLE alertas ADD COLUMN score REAL",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.execute(
        "INSERT INTO orgaos (cnpj, razao_social, municipio_nome) VALUES (?, ?, ?)",
        ("12345678000199", "Prefeitura Teste", "Rio de Janeiro"),
    )
    conn.execute(
        "INSERT INTO fornecedores (ni, tipo_pessoa, razao_social, tem_sancao) VALUES (?, ?, ?, ?)",
        ("98765432000111", "PJ", "Fornecedor Alfa LTDA", 0),
    )
    conn.execute(
        """
        INSERT INTO contratos (
            numero_controle_pncp, orgao_cnpj, fornecedor_ni, objeto,
            valor_global, valor_inicial, data_assinatura,
            data_vigencia_inicio, data_vigencia_fim,
            categoria_processo_nome, numero_contrato_empenho
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PNCP-TEST-001",
            "12345678000199",
            "98765432000111",
            "Serviços de consultoria",
            1_500_000.0,
            1_500_000.0,
            "2025-01-15",
            "2025-01-15",
            "2026-01-15",
            "Serviços",
            "EMP-001",
        ),
    )
    conn.execute(
        """
        INSERT INTO alertas (
            numero_controle_pncp, tipo, severidade, score,
            descricao, metodologia, valor_referencia, narrativa_ia
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PNCP-TEST-001",
            "outlier_valor",
            "alta",
            0.891,
            "Valor acima do padrão estatístico.",
            "IQR + Z-score por categoria.",
            1_500_000.0,
            "Laudo IA de teste para o dossiê.",
        ),
    )
    conn.commit()


@pytest.fixture
def conn() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    _criar_banco(conexao)
    return conexao


def test_carregar_dossie_monta_contrato(conn: sqlite3.Connection) -> None:
    dados = carregar_dossie(conn, 1)
    assert dados["alerta"]["id"] == 1
    assert dados["contrato"]["numero_controle_pncp"] == "PNCP-TEST-001"
    assert dados["fornecedor"]["razao_social"] == "Fornecedor Alfa LTDA"


def test_renderizar_markdown_contem_secoes(conn: sqlite3.Connection) -> None:
    dados = carregar_dossie(conn, 1)
    texto = renderizar_markdown(dados)
    assert "# DOSSIÊ INVESTIGATIVO" in texto
    assert "## Veredito IA" in texto
    assert "Laudo IA de teste" in texto


def test_exportar_dossie_markdown(tmp_path: Path, conn: sqlite3.Connection) -> None:
    caminho = exportar_dossie(conn, 1, tmp_path, gerar_ia=False, formato="md")
    assert caminho.is_file()
    conteudo = caminho.read_text(encoding="utf-8")
    assert "Hipótese Estatística" in conteudo


def test_alerta_inexistente(conn: sqlite3.Connection) -> None:
    with pytest.raises(DossieNaoEncontradoError):
        carregar_dossie(conn, 999)


def test_renderizar_pdf_bytes(conn: sqlite3.Connection) -> None:
    dados = carregar_dossie(conn, 1)
    pdf = renderizar_pdf(dados)
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"


def test_exportar_dossie_pdf(tmp_path: Path, conn: sqlite3.Connection) -> None:
    caminho = exportar_dossie(conn, 1, tmp_path, gerar_ia=False, formato="pdf")
    assert caminho.suffix == ".pdf"
    assert caminho.read_bytes()[:4] == b"%PDF"
