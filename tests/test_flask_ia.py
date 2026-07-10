"""Testes da API Flask — investigação IA on-demand e export dossiê."""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes


@pytest.fixture
def client(tmp_path):
    import web_app as wa

    wa._migracoes_aplicadas = True
    db_file = tmp_path / "flask_ia.db"
    conexao = sqlite3.connect(db_file)
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
    conexao.close()

    def _fake_get_db() -> sqlite3.Connection:
        c = sqlite3.connect(db_file, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    wa.get_db = _fake_get_db
    with wa.app.test_client() as test_client:
        yield test_client


def test_investigar_endpoint_retorna_parecer(client) -> None:
    parecer_fake = {
        "plausibilidade": "provavel_explicavel",
        "analise": "O valor alto é rotineiro para energia; sem sinal de risco.",
        "status_sugerido": "descartado",
        "motivo_sugerido": "valor_rotineiro",
        "provedor": "gemini",
    }
    with patch("analise.motor_ia.InvestigadorIA") as mock_cls, patch(
        "web_app.checar_cota_ia", return_value=({"id": 1, "is_admin": True}, None)
    ), patch("web_app.registrar_consumo_ia"):
        inst = MagicMock()
        inst.emitir_parecer.return_value = parecer_fake
        mock_cls.return_value = inst

        with patch("db.database.GerenciadorBanco") as mock_db:
            mock_db.return_value.atualizar_narrativa_anomalia = MagicMock()
            res = client.post("/api/alertas/1/investigar")

    assert res.status_code == 200
    payload = res.get_json()
    assert payload["parecer"]["status_sugerido"] == "descartado"
    assert payload["parecer"]["motivo_sugerido"] == "valor_rotineiro"
    assert payload["narrativa_ia"] == parecer_fake["analise"]


def test_dossie_md_retorna_attachment(client) -> None:
    res = client.get("/api/dossie/1?formato=md")
    assert res.status_code == 200
    assert "text/markdown" in res.content_type
    assert "attachment" in res.headers.get("Content-Disposition", "")
    assert b"# " in res.data or b"## " in res.data


def test_dossie_pdf_retorna_attachment(client) -> None:
    res = client.get("/api/dossie/1?formato=pdf")
    assert res.status_code == 200
    assert "application/pdf" in res.content_type
    assert "attachment" in res.headers.get("Content-Disposition", "")
    assert res.data[:4] == b"%PDF"


def test_parse_parecer_descartado_com_motivo() -> None:
    from analise.motor_ia import _parse_parecer

    texto = (
        "**[Parecer]**\n"
        "Plausibilidade: Provavelmente explicável\n"
        "Análise: Energia por concessionária tem valor naturalmente alto.\n"
        "Status sugerido: Descartado\n"
        "Motivo do descarte: Valor rotineiro para a categoria"
    )
    p = _parse_parecer(texto)
    assert p["plausibilidade"] == "provavel_explicavel"
    assert p["status_sugerido"] == "descartado"
    assert p["motivo_sugerido"] == "valor_rotineiro"


def test_parse_parecer_investigar_sem_motivo() -> None:
    from analise.motor_ia import _parse_parecer

    texto = (
        "**[Parecer]**\n"
        "Plausibilidade: Provável problema\n"
        "Análise: Construtora com contrato muito acima do padrão; merece checagem.\n"
        "Status sugerido: Investigando\n"
        "Motivo do descarte: —"
    )
    p = _parse_parecer(texto)
    assert p["plausibilidade"] == "provavel_problema"
    assert p["status_sugerido"] == "investigando"
    assert p["motivo_sugerido"] is None
