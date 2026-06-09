"""Testes da API Flask — investigação IA on-demand e export dossiê."""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes


@pytest.fixture
def client():
    import web_app as wa

    wa._migracoes_aplicadas = True
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
        ("98765432000111", "Fornecedor Alfa"),
    )
    conexao.execute(
        """
        INSERT INTO contratos (
            numero_controle_pncp, orgao_cnpj, fornecedor_ni,
            objeto, valor_global, data_assinatura
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "PNCP-001",
            "12345678000199",
            "98765432000111",
            "Consultoria",
            1_000_000.0,
            "2025-01-01",
        ),
    )
    conexao.execute(
        """
        INSERT INTO alertas (
            numero_controle_pncp, tipo, severidade, score,
            descricao, metodologia, valor_referencia, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PNCP-001",
            "outlier_valor",
            "alta",
            0.9,
            "Valor atípico",
            "IQR",
            1_000_000.0,
            "aberto",
        ),
    )
    conexao.commit()

    def _fake_get_db() -> sqlite3.Connection:
        return conexao

    wa.get_db = _fake_get_db
    with wa.app.test_client() as test_client:
        yield test_client


def test_investigar_endpoint_salva_narrativa(client) -> None:
    with patch("analise.motor_ia.InvestigadorIA") as mock_cls:
        inst = MagicMock()
        inst.investigar_anomalia.return_value = "Laudo investigativo gerado pela IA."
        mock_cls.return_value = inst

        with patch("db.database.GerenciadorBanco") as mock_db:
            mock_db.return_value.atualizar_narrativa_anomalia = MagicMock()
            res = client.post("/api/alertas/1/investigar")

    assert res.status_code == 200
    payload = res.get_json()
    assert payload["narrativa_ia"] == "Laudo investigativo gerado pela IA."
    assert payload["chars"] == len("Laudo investigativo gerado pela IA.")


def test_dossie_md_retorna_attachment(client) -> None:
    res = client.get("/api/dossie/1?formato=md")
    assert res.status_code == 200
    assert "text/markdown" in res.content_type
    assert "attachment" in res.headers.get("Content-Disposition", "")
    assert b"# " in res.data or b"## " in res.data
