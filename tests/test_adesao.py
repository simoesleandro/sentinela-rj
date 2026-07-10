"""Testes do detector de carona (adesão a ata) — analisador/adesao.py."""
from __future__ import annotations

import sqlite3

import pytest

from analisador import adesao
from db.conexao import SCHEMA_PATH, aplicar_migracoes


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(c)
    yield c
    c.close()


def _add(c, pncp, valor, objeto, fruto=0, fornecedor="EMPRESA X"):
    c.execute("INSERT OR IGNORE INTO fornecedores (ni, razao_social) VALUES ('1', ?)", (fornecedor,))
    c.execute(
        "INSERT INTO contratos (numero_controle_pncp, fornecedor_ni, valor_global, objeto, fruto_adesao) "
        "VALUES (?, '1', ?, ?, ?)",
        (pncp, valor, objeto, fruto),
    )
    c.commit()


# ── helpers ──────────────────────────────────────────────────────────────────

def test_normaliza_remove_acento():
    assert adesao._normalizar("Adesão à Ata") == "adesao a ata"


def test_e_carona_por_texto():
    assert adesao._e_carona("Trata-se de Adesão à Ata de Registro de Preços", 0)
    assert adesao._e_carona("Contratação por carona", 0)


def test_e_carona_por_flag():
    assert adesao._e_carona("qualquer objeto", 1)


def test_nao_e_carona_prorrogacao_propria_ata():
    # prorrogação/saldo da própria ata NÃO é carona
    assert not adesao._e_carona("Prorrogação da Ata de Registro de Preços nº 565/2024", 0)
    assert not adesao._e_carona("Saldo remanescente da Ata de Registro", 0)


# ── detector ─────────────────────────────────────────────────────────────────

def test_detecta_carona_acima_do_piso(conn):
    _add(conn, "p1", 8_000_000, "Adesão à Ata de Registro de Preços para aquisição")
    res = adesao.detectar(conn)
    assert len(res) == 1
    assert res[0].tipo == "adesao_carona"
    assert res[0].severidade == "alta"  # >= 5M
    assert res[0].metricas["deteccao_via"] == "objeto"


def test_ignora_carona_abaixo_do_piso(conn):
    _add(conn, "p1", 100_000, "Adesão à Ata de Registro de Preços")
    assert adesao.detectar(conn) == []


def test_ignora_prorrogacao_propria(conn):
    _add(conn, "p1", 40_000_000, "Prorrogação da Ata de Registro de Preços nº 565")
    assert adesao.detectar(conn) == []


def test_severidade_media_entre_1_e_5M(conn):
    _add(conn, "p1", 2_000_000, "adesão a ata de registro de preços")
    res = adesao.detectar(conn)
    assert len(res) == 1 and res[0].severidade == "media"


def test_detecta_por_flag_mesmo_sem_texto(conn):
    _add(conn, "p1", 6_000_000, "Aquisição de equipamentos", fruto=1)
    res = adesao.detectar(conn)
    assert len(res) == 1
    assert res[0].metricas["deteccao_via"] == "flag PNCP"
