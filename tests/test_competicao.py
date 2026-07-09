"""Testes do detector de competição fraca (analisador/competicao.py)."""
from __future__ import annotations

import sqlite3

from analisador.competicao import detectar
from analisador.engine import _carregar_detectores


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE licitacoes (
            numero_controle_pncp TEXT PRIMARY KEY, orgao_cnpj TEXT,
            ano_compra INTEGER, sequencial_compra INTEGER,
            modalidade_id INTEGER, modalidade_nome TEXT, situacao_nome TEXT,
            objeto TEXT, valor_estimado REAL, valor_homologado REAL,
            srp INTEGER DEFAULT 0, data_publicacao TEXT,
            data_encerramento_proposta TEXT, municipio_ibge TEXT,
            itens_coletados_em TEXT, coletado_em TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE licitacao_itens (
            numero_controle_pncp TEXT, numero_item INTEGER, descricao TEXT,
            situacao_nome TEXT, quantidade REAL, tem_resultado INTEGER,
            PRIMARY KEY (numero_controle_pncp, numero_item)
        )"""
    )
    return conn


def _licitacao(conn, pncp, est, hom, modalidade="Pregão - Eletrônico"):
    conn.execute(
        "INSERT INTO licitacoes (numero_controle_pncp, orgao_cnpj, ano_compra, "
        "sequencial_compra, modalidade_nome, objeto, valor_estimado, valor_homologado) "
        "VALUES (?, '42498733000148', 2026, 1, ?, 'Aquisição de pneus', ?, ?)",
        (pncp, modalidade, est, hom),
    )


def _itens(conn, pncp, situacoes):
    for i, s in enumerate(situacoes, start=1):
        conn.execute(
            "INSERT INTO licitacao_itens (numero_controle_pncp, numero_item, situacao_nome) "
            "VALUES (?, ?, ?)",
            (pncp, i, s),
        )


# ── desconto_zero_licitacao ──────────────────────────────────────────────────

def test_desconto_zero_alta_severidade_em_valor_alto():
    conn = _conn()
    _licitacao(conn, "c1", est=9_263_108.0, hom=9_263_108.0)  # caso real: pneus
    alertas = detectar(conn)
    assert len(alertas) == 1
    a = alertas[0]
    assert a.tipo == "desconto_zero_licitacao"
    assert a.severidade == "alta"
    assert a.metricas["desconto_pct"] == 0.0
    assert "22,6%" in a.metodologia or "22.6" in a.metodologia  # calibração citada


def test_desconto_pequeno_mas_dentro_do_limiar_dispara_media():
    conn = _conn()
    _licitacao(conn, "c1", est=2_000_000.0, hom=1_992_000.0)  # 0,4%
    alertas = detectar(conn)
    assert len(alertas) == 1
    assert alertas[0].severidade == "media"


def test_desconto_saudavel_nao_dispara():
    conn = _conn()
    _licitacao(conn, "c1", est=2_000_000.0, hom=1_500_000.0)  # 25% — mediana real
    assert detectar(conn) == []


def test_valor_pequeno_nao_dispara():
    conn = _conn()
    _licitacao(conn, "c1", est=100_000.0, hom=100_000.0)  # < R$ 500k
    assert detectar(conn) == []


def test_homologado_muito_acima_do_estimado_ignorado():
    conn = _conn()
    _licitacao(conn, "c1", est=1_000_000.0, hom=3_000_000.0)  # inconsistência de dado
    assert detectar(conn) == []


def test_sem_homologacao_nao_dispara():
    conn = _conn()
    _licitacao(conn, "c1", est=1_000_000.0, hom=None)
    assert detectar(conn) == []


# ── licitacao_itens_desertos ─────────────────────────────────────────────────

def test_maioria_de_itens_fracassados_dispara():
    conn = _conn()
    _licitacao(conn, "c1", est=2_000_000.0, hom=None)
    _itens(conn, "c1", ["Fracassado", "Fracassado", "Deserto", "Homologado", "Fracassado"])
    alertas = detectar(conn)
    assert len(alertas) == 1
    a = alertas[0]
    assert a.tipo == "licitacao_itens_desertos"
    assert a.metricas["n_desertos_fracassados"] == 4
    assert a.metricas["proporcao"] == 0.8


def test_minoria_de_itens_fracassados_nao_dispara():
    # ter ALGUM item fracassado é comum (35% das compras) — minoria não dispara
    conn = _conn()
    _licitacao(conn, "c1", est=2_000_000.0, hom=None)
    _itens(conn, "c1", ["Fracassado", "Homologado", "Homologado", "Homologado", "Homologado"])
    assert detectar(conn) == []


def test_poucos_itens_nao_dispara():
    conn = _conn()
    _licitacao(conn, "c1", est=2_000_000.0, hom=None)
    _itens(conn, "c1", ["Fracassado", "Deserto"])  # < 4 itens
    assert detectar(conn) == []


def test_proporcao_alta_e_valor_alto_sobe_para_alta():
    conn = _conn()
    _licitacao(conn, "c1", est=6_000_000.0, hom=None)
    _itens(conn, "c1", ["Fracassado"] * 5 + ["Homologado"])
    alertas = detectar(conn)
    assert len(alertas) == 1
    assert alertas[0].severidade == "alta"


# ── registro no engine ───────────────────────────────────────────────────────

def test_detector_registrado_no_engine():
    nomes = [nome for nome, _ in _carregar_detectores()]
    assert "competicao" in nomes
