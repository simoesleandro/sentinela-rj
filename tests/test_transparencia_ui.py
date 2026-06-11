"""Testes da API — empenhos Transparência RJ no detalhe do alerta."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes
from extrator.transparencia_rj import cruzar_contratos, ingestir_empenhos


def _bootstrap_db(db_file: Path) -> None:
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conn)
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
    conn.execute(
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
    csv_text = (
        "cnpj;valor;data;historico;orgao;documento\n"
        "98765432000111;1000000;2025-01-15;Empenho consultoria;SMF;EMP-2025-01\n"
    )
    ingestir_empenhos(conn, csv_text)
    cruzar_contratos(conn, tolerancia=0.01)
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path: Path):
    import web_app as wa

    wa._migracoes_aplicadas = True
    db_file = tmp_path / "transp_ui.db"
    _bootstrap_db(db_file)

    def _fake_get_db() -> sqlite3.Connection:
        conexao = sqlite3.connect(db_file, check_same_thread=False)
        conexao.row_factory = sqlite3.Row
        return conexao

    wa.get_db = _fake_get_db
    with wa.app.test_client() as test_client:
        yield test_client


def test_alerta_detail_inclui_transparencia_rj(client) -> None:
    res = client.get("/api/alertas/1")
    assert res.status_code == 200
    payload = res.get_json()
    assert "transparencia_rj" in payload
    assert len(payload["transparencia_rj"]) == 1
    empenho = payload["transparencia_rj"][0]
    assert empenho["valor"] == 1_000_000.0
    assert empenho["documento"] == "EMP-2025-01"
    assert empenho["score"] >= 0.99


def test_alerta_sem_cruzamento_retorna_lista_vazia(client) -> None:
    import web_app as wa

    conn = wa.get_db()
    conn.execute(
        """
        INSERT INTO contratos (
            numero_controle_pncp, orgao_cnpj, fornecedor_ni,
            objeto, valor_global, data_assinatura
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "PNCP-002",
            "12345678000199",
            "98765432000111",
            "Outro serviço",
            50_000.0,
            "2025-02-01",
        ),
    )
    conn.execute(
        """
        INSERT INTO alertas (
            numero_controle_pncp, tipo, severidade, score,
            descricao, metodologia, valor_referencia, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PNCP-002",
            "outlier_valor",
            "baixa",
            0.5,
            "Sem match TRJ",
            "IQR",
            50_000.0,
            "aberto",
        ),
    )
    conn.commit()
    conn.close()

    res = client.get("/api/alertas/2")
    assert res.status_code == 200
    assert res.get_json()["transparencia_rj"] == []
