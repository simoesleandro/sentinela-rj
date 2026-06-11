"""Testes do filtro multi-município no dashboard."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes
from db.filtro_municipio import listar_municipios


@pytest.fixture
def client(tmp_path: Path):
    import web_app as wa

    wa._migracoes_aplicadas = True
    db_file = tmp_path / "municipios.db"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conn)
    conn.execute(
        "INSERT INTO orgaos (cnpj, razao_social, municipio_ibge, municipio_nome) VALUES (?, ?, ?, ?)",
        ("11111111000111", "Prefeitura A", "3304557", "Rio de Janeiro"),
    )
    conn.execute(
        "INSERT INTO orgaos (cnpj, razao_social, municipio_ibge, municipio_nome) VALUES (?, ?, ?, ?)",
        ("22222222000122", "Prefeitura B", "3303302", "Niterói"),
    )
    conn.execute(
        "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?)",
        ("99999999000199", "Fornecedor X"),
    )
    for i, orgao in enumerate(("11111111000111", "22222222000122", "11111111000111")):
        conn.execute(
            """
            INSERT INTO contratos (
                numero_controle_pncp, orgao_cnpj, fornecedor_ni,
                objeto, valor_global, data_assinatura
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"PNCP-{i}", orgao, "99999999000199", "Serviço", 100_000.0 * (i + 1), "2025-01-15"),
        )
    conn.execute(
        """
        INSERT INTO alertas (
            tipo, severidade, score, descricao, metodologia,
            valor_referencia, numero_controle_pncp
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("outlier_valor", "alta", 0.9, "Alerta RJ", "IQR", 500_000.0, "PNCP-0"),
    )
    conn.execute(
        """
        INSERT INTO alertas (
            tipo, severidade, score, descricao, metodologia,
            valor_referencia, numero_controle_pncp
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("outlier_valor", "media", 0.5, "Alerta Niteroi", "IQR", 200_000.0, "PNCP-1"),
    )
    conn.commit()
    conn.close()

    def _fake_get_db() -> sqlite3.Connection:
        c = sqlite3.connect(db_file, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    wa.get_db = _fake_get_db
    with wa.app.test_client() as test_client:
        yield test_client


def test_listar_municipios_no_banco() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conn)
    conn.execute(
        "INSERT INTO orgaos (cnpj, municipio_ibge, municipio_nome) VALUES (?, ?, ?)",
        ("1", "3304557", "Rio de Janeiro"),
    )
    conn.execute(
        """
        INSERT INTO contratos (numero_controle_pncp, orgao_cnpj, fornecedor_ni, valor_global)
        VALUES (?, ?, ?, ?)
        """,
        ("P1", "1", "F1", 10.0),
    )
    conn.commit()
    items = listar_municipios(conn)
    assert any(i["ibge"] == "3304557" for i in items)


def test_api_municipios(client) -> None:
    res = client.get("/api/municipios")
    assert res.status_code == 200
    data = res.get_json()
    assert data["coleta_ibge"] == "3304557"
    assert len(data["items"]) >= 2


def test_stats_filtra_por_municipio(client) -> None:
    res_all = client.get("/api/stats")
    res_rj = client.get("/api/stats?municipio_ibge=3304557")
    res_nit = client.get("/api/stats?municipio_ibge=3303302")
    assert res_all.status_code == res_rj.status_code == res_nit.status_code == 200
    all_data = res_all.get_json()
    rj = res_rj.get_json()
    nit = res_nit.get_json()
    assert all_data["contratos_total"] == 3
    assert rj["contratos_total"] == 2
    assert nit["contratos_total"] == 1
    assert rj["alertas_total"] == 1
    assert nit["alertas_total"] == 1
