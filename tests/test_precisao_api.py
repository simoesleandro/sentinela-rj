"""Testes da API de precisão por detector (routes/institucional.py)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes


def _bootstrap_db(db_file: Path) -> None:
    conn = sqlite3.connect(db_file)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conn)
    conn.commit()
    conn.close()


def _inserir_alertas(db_file: Path, tipo: str, confirmados: int, descartados: int, pendentes: int):
    conn = sqlite3.connect(db_file)
    n = 0
    for status, qtd in (("confirmado", confirmados), ("descartado", descartados), ("aberto", pendentes)):
        for _ in range(qtd):
            n += 1
            conn.execute(
                "INSERT INTO alertas (tipo, severidade, descricao, status) VALUES (?, 'alta', 'x', ?)",
                (tipo, status),
            )
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web_app as wa

    wa._migracoes_aplicadas = True
    db_file = tmp_path / "precisao.db"
    _bootstrap_db(db_file)
    monkeypatch.setattr(wa, "get_db", lambda: _conn(db_file))
    with wa.app.test_client() as c:
        yield c, db_file


def _conn(db_file):
    c = sqlite3.connect(db_file, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def test_precisao_medida_com_amostra_suficiente(client):
    c, db_file = client
    # 8 confirmados + 2 descartados = 10 rotulados (>= min) -> precisao 0.8
    _inserir_alertas(db_file, "outlier_valor", confirmados=8, descartados=2, pendentes=5)
    res = c.get("/api/precisao")
    assert res.status_code == 200
    item = next(i for i in res.get_json()["itens"] if i["tipo"] == "outlier_valor")
    assert item["amostra_status"] == "medida"
    assert item["precisao"] == 0.8
    assert item["confirmados"] == 8 and item["descartados"] == 2 and item["pendentes"] == 5


def test_amostra_insuficiente_nao_reporta_taxa(client):
    c, db_file = client
    # só 3 rotulados (< 10) -> insuficiente, precisao None
    _inserir_alertas(db_file, "socio_compartilhado", confirmados=2, descartados=1, pendentes=4)
    res = c.get("/api/precisao")
    item = next(i for i in res.get_json()["itens"] if i["tipo"] == "socio_compartilhado")
    assert item["amostra_status"] == "amostra_insuficiente"
    assert item["precisao"] is None
    assert item["rotulados"] == 3


def test_rotulados_total_e_base_vazia(client):
    c, db_file = client
    res = c.get("/api/precisao")
    d = res.get_json()
    assert d["rotulados_total"] == 0
    assert d["min_amostra"] == 10
    assert d["itens"] == []


def test_paginas_institucionais_renderizam(client):
    c, _ = client
    assert c.get("/dados").status_code == 200
    assert c.get("/precisao").status_code == 200
