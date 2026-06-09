"""Testes de watchlists, regras de alerta e integração com o motor."""
from __future__ import annotations

import sqlite3

import pytest

from analisador.engine import executar_e_persistir
from analisador.watchlists import detectar, executar_watchlists_e_persistir
from db.conexao import SCHEMA_PATH, aplicar_migracoes
from db.regras_alerta import criar_regra, filtrar_para_notificacao
from db.watchlists import criar_watchlist, desativar_watchlist


@pytest.fixture
def conn() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    conexao.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conexao)
    conexao.execute(
        "INSERT INTO orgaos (cnpj, razao_social) VALUES (?, ?)",
        ("12345678000199", "Prefeitura Teste"),
    )
    conexao.execute(
        "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?), (?, ?)",
        ("98765432000111", "Fornecedor A", "11111111000122", "Fornecedor B"),
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
            "Licenciamento de SOFTWARE municipal",
            500_000.0,
            "2025-06-01",
        ),
    )
    conexao.execute(
        """
        INSERT INTO contratos (
            numero_controle_pncp, orgao_cnpj, fornecedor_ni,
            objeto, valor_global, data_assinatura
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "PNCP-002",
            "12345678000199",
            "11111111000122",
            "Obras de pavimentação",
            2_000_000.0,
            "2025-07-01",
        ),
    )
    conexao.commit()
    return conexao


def test_schema_watchlists_regras(conn: sqlite3.Connection) -> None:
    wl = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='watchlists'"
    ).fetchone()
    rg = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='regras_alerta'"
    ).fetchone()
    assert wl is not None
    assert rg is not None

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO watchlists (rotulo, fornecedor_ni, orgao_cnpj, palavra_chave_objeto)
            VALUES ('vazio', NULL, NULL, NULL)
            """
        )


def test_match_fornecedor(conn: sqlite3.Connection) -> None:
    criar_watchlist(
        conn,
        rotulo="Monitorar Fornecedor A",
        fornecedor_ni="98765432000111",
    )
    matches = detectar(conn)
    assert len(matches) == 1
    assert matches[0].tipo == "watchlist_match"
    assert matches[0].contratos == ["PNCP-001"]
    assert matches[0].metricas["watchlist_id"] == 1


def test_match_orgao_palavra(conn: sqlite3.Connection) -> None:
    criar_watchlist(
        conn,
        rotulo="Software no orgao",
        orgao_cnpj="12345678000199",
        palavra_chave_objeto="software",
    )
    matches = detectar(conn)
    assert len(matches) == 1
    assert matches[0].contratos == ["PNCP-001"]


def test_match_inativo_ignorado(conn: sqlite3.Connection) -> None:
    item = criar_watchlist(
        conn,
        rotulo="Inativa",
        fornecedor_ni="98765432000111",
    )
    desativar_watchlist(conn, int(item["id"]))
    assert detectar(conn) == []


def test_dedup_por_watchlist_id(conn: sqlite3.Connection) -> None:
    criar_watchlist(conn, rotulo="WL-1", fornecedor_ni="98765432000111")
    criar_watchlist(conn, rotulo="WL-2", fornecedor_ni="98765432000111")
    _, resumo = executar_watchlists_e_persistir(conn)
    assert resumo["inseridos"] == 2
    rows = conn.execute(
        "SELECT id, metodologia FROM alertas WHERE tipo = 'watchlist_match'"
    ).fetchall()
    assert len(rows) == 2
    metodologias = {r["metodologia"] for r in rows}
    assert any("watchlist_id=1" in m for m in metodologias)
    assert any("watchlist_id=2" in m for m in metodologias)


def test_regra_tipo_e_severidade(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO alertas (
            numero_controle_pncp, tipo, severidade, score,
            descricao, metodologia, valor_referencia, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'aberto')
        """,
        (
            "PNCP-001",
            "watchlist_match",
            "media",
            0.75,
            "match",
            "watchlist_id=1",
            500_000.0,
        ),
    )
    conn.execute(
        """
        INSERT INTO alertas (
            numero_controle_pncp, tipo, severidade, score,
            descricao, metodologia, valor_referencia, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'aberto')
        """,
        (
            "PNCP-002",
            "outlier_valor",
            "alta",
            0.95,
            "outlier",
            "IQR",
            2_000_000.0,
        ),
    )
    conn.commit()
    criar_regra(conn, tipo="watchlist_match", severidade_min="media", valor_min=0)
    ids = filtrar_para_notificacao(conn, [1, 2])
    assert ids == [1]


def test_regra_valor_min(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO alertas (
            numero_controle_pncp, tipo, severidade, score,
            descricao, metodologia, valor_referencia, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'aberto')
        """,
        (
            "PNCP-001",
            "watchlist_match",
            "media",
            0.75,
            "match",
            "watchlist_id=1",
            500_000.0,
        ),
    )
    conn.commit()
    criar_regra(conn, tipo=None, severidade_min="baixa", valor_min=1_000_000.0)
    assert filtrar_para_notificacao(conn, [1]) == []


def test_executar_e_persistir_integracao(conn: sqlite3.Connection) -> None:
    criar_watchlist(
        conn,
        rotulo="Integracao",
        fornecedor_ni="98765432000111",
    )
    _, n_sync, contagens, resumo = executar_e_persistir(conn)
    assert n_sync >= 1
    assert contagens.get("watchlists", 0) == 1
    assert resumo.get("watchlist", {}).get("inseridos", 0) == 1
    total_wl = conn.execute(
        "SELECT COUNT(*) FROM alertas WHERE tipo = 'watchlist_match'"
    ).fetchone()[0]
    assert total_wl == 1


def test_remocao_obsoleto_watchlist(conn: sqlite3.Connection) -> None:
    item = criar_watchlist(
        conn,
        rotulo="Temporaria",
        fornecedor_ni="98765432000111",
    )
    executar_watchlists_e_persistir(conn)
    assert conn.execute(
        "SELECT COUNT(*) FROM alertas WHERE tipo = 'watchlist_match'"
    ).fetchone()[0] == 1

    desativar_watchlist(conn, int(item["id"]))
    resumo = executar_watchlists_e_persistir(conn)[1]
    assert resumo["removidos"] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM alertas WHERE tipo = 'watchlist_match'"
    ).fetchone()[0] == 0
