"""Testes Flask — endpoint comparador."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes


@pytest.fixture
def client(tmp_path: Path):
    import web_app as wa

    wa._migracoes_aplicadas = True
    db_file = tmp_path / "comparador.db"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conn)
    conn.execute(
        "INSERT INTO orgaos (cnpj, razao_social) VALUES (?, ?)",
        ("12345678000199", "Prefeitura"),
    )
    for ni in ("11111111000111", "22222222000122"):
        conn.execute(
            "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?)",
            (ni, f"Forn {ni[-4:]}"),
        )
        conn.execute(
            """
            INSERT INTO contratos (
                numero_controle_pncp, orgao_cnpj, fornecedor_ni, valor_global
            ) VALUES (?, ?, ?, ?)
            """,
            (f"P-{ni[-4:]}", "12345678000199", ni, 100_000.0),
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


def test_api_comparar_retorna_dois_perfis(client) -> None:
    res = client.get(
        "/api/fornecedores/comparar?ni=11111111000111&ni=22222222000122"
    )
    assert res.status_code == 200
    payload = res.get_json()
    assert len(payload["fornecedores"]) == 2


def test_api_comparar_parametro_nis(client) -> None:
    res = client.get("/api/fornecedores/comparar?nis=11111111000111,22222222000122")
    assert res.status_code == 200


def test_api_investigados_lista_fornecedores_com_alertas(client) -> None:
    conn = __import__("web_app", fromlist=["get_db"]).get_db()
    conn.execute(
        """
        INSERT INTO alertas (
            numero_controle_pncp, tipo, severidade, score,
            descricao, metodologia, valor_referencia, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("P-0111", "outlier_valor", "alta", 0.9, "x", "y", 100_000.0, "aberto"),
    )
    conn.commit()
    conn.close()

    res = client.get("/api/fornecedores/investigados")
    assert res.status_code == 200
    items = res.get_json()["items"]
    assert len(items) >= 1
    assert items[0]["fornecedor_ni"] in ("11111111000111", "22222222000122")
    assert "total_alertas" in items[0]
