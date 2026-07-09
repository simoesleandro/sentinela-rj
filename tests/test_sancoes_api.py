"""Testes do extrator de sanções federais via API (extrator/sancoes_api.py).

Sem rede: consultar_cnpj é monkeypatchado. O formato mockado espelha o real
capturado empiricamente (pessoa.cnpjFormatado, DD/MM/YYYY, etc.)."""
from __future__ import annotations

import sqlite3

import pytest

from extrator import sancoes_api


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE fornecedores (ni TEXT PRIMARY KEY, razao_social TEXT, "
        "tem_sancao INTEGER DEFAULT 0, sancoes_verificado_em TEXT)"
    )
    conn.execute(
        "CREATE TABLE contratos (numero_controle_pncp TEXT PRIMARY KEY, "
        "fornecedor_ni TEXT, valor_global REAL)"
    )
    conn.execute(
        "CREATE TABLE fornecedor_sancoes ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, fornecedor_ni TEXT, fonte TEXT, "
        "tipo_sancao TEXT, orgao_sancionador TEXT, data_inicio TEXT, data_fim TEXT, "
        "descricao TEXT, coletado_em TEXT DEFAULT (datetime('now')), "
        "UNIQUE(fornecedor_ni, fonte, data_inicio))"
    )
    conn.commit()
    return conn


def _fornecedor(conn, ni, com_contrato=True):
    conn.execute("INSERT INTO fornecedores (ni) VALUES (?)", (ni,))
    if com_contrato:
        conn.execute(
            "INSERT INTO contratos VALUES (?, ?, 1000000)", (f"c-{ni}", ni)
        )
    conn.commit()


_REG_CNEP = {
    "dataInicioSancao": "29/09/2025",
    "dataFimSancao": "29/09/2026",
    "tipoSancao": {"descricaoResumida": "Impedimento/proibição de contratar"},
    "orgaoSancionador": {"nome": "Prefeitura de Teixeira", "siglaUf": "PB", "esfera": "MUNICIPAL"},
    "fundamentacao": [{"descricao": "DECRETO MUNICIPAL - ART. 5"}],
    "pessoa": {"cnpjFormatado": "01.034.997/0001-63"},
}


# ── parsing / normalização ───────────────────────────────────────────────────

def test_normalizar_data_br_para_iso():
    assert sancoes_api._normalizar_data("29/09/2025") == "2025-09-29"
    assert sancoes_api._normalizar_data("") is None
    assert sancoes_api._normalizar_data(None) is None


def test_parse_registro_extrai_campos_reais():
    s = sancoes_api._parse_registro(_REG_CNEP, "CNEP", "01034997000163")
    assert s["fornecedor_ni"] == "01034997000163"
    assert s["fonte"] == "CNEP"
    assert s["tipo_sancao"] == "Impedimento/proibição de contratar"
    assert "Teixeira" in s["orgao_sancionador"]
    assert "MUNICIPAL" in s["orgao_sancionador"]
    assert s["data_inicio"] == "2025-09-29"
    assert s["data_fim"] == "2026-09-29"
    assert "DECRETO" in s["descricao"]


# ── sincronização incremental ────────────────────────────────────────────────

def test_sincroniza_marca_sancionado_e_verificado(monkeypatch):
    conn = _conn()
    _fornecedor(conn, "01034997000163")  # sancionado
    _fornecedor(conn, "05851921000181")  # limpo

    def fake_consultar(cnpj, chave):
        if cnpj == "01034997000163":
            return [sancoes_api._parse_registro(_REG_CNEP, "CNEP", cnpj)]
        return []

    monkeypatch.setattr(sancoes_api, "consultar_cnpj", fake_consultar)
    resumo = sancoes_api.sincronizar_sancoes_api(conn, limite=10, pausa_s=0, chave="x")

    assert resumo["checados"] == 2
    assert resumo["fornecedores_sancionados"] == 1
    assert resumo["sancoes_registradas"] == 1
    assert resumo["pendentes_restantes"] == 0
    # marca tem_sancao só no sancionado
    assert conn.execute("SELECT tem_sancao FROM fornecedores WHERE ni='01034997000163'").fetchone()[0] == 1
    assert conn.execute("SELECT tem_sancao FROM fornecedores WHERE ni='05851921000181'").fetchone()[0] == 0
    # ambos ficam com sancoes_verificado_em preenchido
    assert conn.execute("SELECT COUNT(*) FROM fornecedores WHERE sancoes_verificado_em IS NOT NULL").fetchone()[0] == 2


def test_resumivel_pega_nao_verificados_primeiro(monkeypatch):
    conn = _conn()
    todos = ("11111111000111", "22222222000122", "33333333000133")
    for ni in todos:
        _fornecedor(conn, ni)
    checados_por_chamada = []
    monkeypatch.setattr(
        sancoes_api, "consultar_cnpj",
        lambda cnpj, chave: checados_por_chamada.append(cnpj) or [],
    )

    # 1ª rodada com limite 2: checa 2, sobra 1 não-verificado
    r1 = sancoes_api.sincronizar_sancoes_api(conn, limite=2, pausa_s=0, chave="x")
    assert r1["checados"] == 2 and r1["pendentes_restantes"] == 1
    verificados_r1 = set(checados_por_chamada)

    # 2ª rodada com limite 1: prioriza o único não-verificado que sobrou
    checados_por_chamada.clear()
    r2 = sancoes_api.sincronizar_sancoes_api(conn, limite=1, pausa_s=0, chave="x")
    assert r2["checados"] == 1 and r2["pendentes_restantes"] == 0
    # o checado na 2ª rodada é justamente o que faltou (prioridade ao NULL)
    assert checados_por_chamada[0] not in verificados_r1


def test_ignora_cpf_so_cnpj(monkeypatch):
    conn = _conn()
    _fornecedor(conn, "12345678901")      # CPF (11 dígitos) — fora
    _fornecedor(conn, "11111111000111")   # CNPJ — dentro
    monkeypatch.setattr(sancoes_api, "consultar_cnpj", lambda cnpj, chave: [])
    resumo = sancoes_api.sincronizar_sancoes_api(conn, limite=10, pausa_s=0, chave="x")
    assert resumo["checados"] == 1


def test_sem_chave_levanta_erro(monkeypatch):
    conn = _conn()
    # sem chave passada E sem env → deve levantar (não silenciar)
    monkeypatch.setattr(sancoes_api, "chave_configurada", lambda: "")
    with pytest.raises(sancoes_api.SancoesApiError, match="TRANSPARENCIA_API_KEY"):
        sancoes_api.sincronizar_sancoes_api(conn, limite=10, pausa_s=0)


def test_upsert_idempotente(monkeypatch):
    conn = _conn()
    _fornecedor(conn, "01034997000163")
    monkeypatch.setattr(
        sancoes_api, "consultar_cnpj",
        lambda cnpj, chave: [sancoes_api._parse_registro(_REG_CNEP, "CNEP", cnpj)],
    )
    sancoes_api.sincronizar_sancoes_api(conn, limite=10, pausa_s=0, chave="x")
    sancoes_api.sincronizar_sancoes_api(conn, limite=10, pausa_s=0, chave="x")
    # a UNIQUE(fornecedor_ni, fonte, data_inicio) impede duplicata
    assert conn.execute("SELECT COUNT(*) FROM fornecedor_sancoes").fetchone()[0] == 1
