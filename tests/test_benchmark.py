"""Testes do benchmark municipal (analise/benchmark.py)."""
from __future__ import annotations

import sqlite3

import pytest

from analise.benchmark import calcular_benchmark
from db.conexao import SCHEMA_PATH, aplicar_migracoes


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(c)
    yield c
    c.close()


def _contrato(c, pncp, municipio, valor, fornecedor, objeto=""):
    c.execute("INSERT OR IGNORE INTO fornecedores (ni) VALUES (?)", (fornecedor,))
    c.execute(
        "INSERT INTO contratos (numero_controle_pncp, municipio_nome, valor_global, "
        "fornecedor_ni, objeto) VALUES (?,?,?,?,?)",
        (pncp, municipio, valor, fornecedor, objeto),
    )


def _povoar_municipio(c, nome, n, n_dispensa, fornecedor_unico=False):
    """n contratos; n_dispensa deles com objeto de dispensa."""
    for i in range(n):
        forn = "F1" if fornecedor_unico else f"F{i}"
        objeto = "Contratação por dispensa de licitação" if i < n_dispensa else "Aquisição regular"
        _contrato(c, f"{nome}-{i}", nome, 1_000_000, forn, objeto)
    c.commit()


def test_calcula_pct_sem_licitacao(conn):
    # Município A: 40 contratos, 20 por dispensa -> 50%
    _povoar_municipio(conn, "Alfa", 40, 20)
    # Município B: 40 contratos, 4 por dispensa -> 10%
    _povoar_municipio(conn, "Beta", 40, 4)

    r = calcular_benchmark(conn)
    assert r["n_municipios"] == 2
    alfa = next(m for m in r["municipios"] if m["municipio"] == "Alfa")
    beta = next(m for m in r["municipios"] if m["municipio"] == "Beta")
    assert alfa["pct_sem_licitacao"] == 0.5
    assert beta["pct_sem_licitacao"] == 0.1
    # ordenado por %sem-licitação desc
    assert r["municipios"][0]["municipio"] == "Alfa"


def test_ignora_municipio_abaixo_do_minimo(conn):
    _povoar_municipio(conn, "Grande", 40, 10)
    _povoar_municipio(conn, "Pequeno", 5, 3)  # < 30, fora
    r = calcular_benchmark(conn)
    nomes = {m["municipio"] for m in r["municipios"]}
    assert "Grande" in nomes and "Pequeno" not in nomes


def test_concentracao_top1_e_hhi(conn):
    # Município com fornecedor único -> concentração 100%, HHI 1
    _povoar_municipio(conn, "Mono", 40, 0, fornecedor_unico=True)
    r = calcular_benchmark(conn)
    mono = r["municipios"][0]
    assert mono["concentracao_top1"] == 1.0
    assert mono["hhi"] == 1.0
    assert mono["n_fornecedores"] == 1


def test_vs_mediana(conn):
    _povoar_municipio(conn, "Alta", 40, 32)   # 80%
    _povoar_municipio(conn, "Media", 40, 8)   # 20%
    _povoar_municipio(conn, "Baixa", 40, 4)   # 10%
    r = calcular_benchmark(conn)
    # mediana de {0.8, 0.2, 0.1} = 0.2
    assert r["medianas"]["pct_sem_licitacao"] == 0.2
    alta = next(m for m in r["municipios"] if m["municipio"] == "Alta")
    assert alta["sem_licitacao_vs_mediana"] == 4.0  # 0.8 / 0.2
    assert alta["acima_mediana"] is True
