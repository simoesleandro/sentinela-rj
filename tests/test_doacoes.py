"""Testes do cruzamento sócio × doação de campanha (TSE).

Cobre o extrator (parse/ingestão), a confirmação de CPF por nome + 6 dígitos e a
severidade do detector socio_doou_campanha.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from analisador.doacoes import detectar, matches_confirmados, resolver_cpf_confirmado
from db.conexao import SCHEMA_PATH, aplicar_migracoes
from extrator.tse import _data_iso, _valor_br, ingerir_receitas, normalizar_nome


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(c)
    yield c
    c.close()


def _add_fornecedor(c, ni, razao, socios):
    c.execute("INSERT INTO fornecedores (ni, razao_social) VALUES (?,?)", (ni, razao))
    c.execute(
        "INSERT INTO fornecedor_cadastro (fornecedor_ni, socios) VALUES (?,?)",
        (ni, json.dumps(socios)),
    )


def _add_contrato(c, pncp, ni, valor, municipio):
    c.execute(
        "INSERT INTO contratos (numero_controle_pncp, fornecedor_ni, valor_global, municipio_nome) "
        "VALUES (?,?,?,?)",
        (pncp, ni, valor, municipio),
    )


def _add_doacao(c, nome, cpf, municipio, cargo, candidato, valor, sq):
    c.execute(
        """INSERT INTO doacoes_campanha
           (ano_eleicao, uf, municipio_ue, cargo, candidato_nome, partido,
            doador_cpf, doador_nome, doador_nome_norm, valor, data_receita, sq_receita)
           VALUES (2024,'RJ',?,?,?,'XX',?,?,?,?, '2024-08-01', ?)""",
        (municipio, cargo, candidato, cpf, nome, normalizar_nome(nome), valor, sq),
    )


# ── helpers de parsing ───────────────────────────────────────────────────────

def test_normalizar_nome_remove_preposicoes_e_acentos():
    assert normalizar_nome("João DA Silva de Souza") == "JOAO SILVA SOUZA"
    assert normalizar_nome("MARIA DOS ANJOS") == "MARIA ANJOS"


def test_valor_br():
    assert _valor_br("1.500,00") == 1500.0
    assert _valor_br("500,00") == 500.0
    assert _valor_br("") == 0.0


def test_data_iso():
    assert _data_iso("27/08/2024") == "2024-08-27"
    assert _data_iso("") is None


# ── confirmação de CPF ───────────────────────────────────────────────────────

def test_confirma_cpf_por_nome_e_6_digitos(conn):
    # sócio com CPF mascarado ***123456**
    _add_fornecedor(conn, "111", "EMPRESA A", [
        {"nome_socio": "JOAO DA SILVA", "cnpj_cpf_do_socio": "***123456**",
         "qualificacao_socio": "Sócio-Administrador"},
    ])
    # doador de mesmo nome cujo CPF tem o meio 123456 -> confirma
    _add_doacao(conn, "JOAO DA SILVA", "00112345699", "RIO DE JANEIRO",
                "Vereador", "FULANO", 1000.0, "sq1")
    # homônimo com CPF de meio diferente -> NÃO confirma
    _add_doacao(conn, "JOAO DA SILVA", "99988877766", "RIO DE JANEIRO",
                "Vereador", "CICLANO", 500.0, "sq2")
    conn.commit()

    n = resolver_cpf_confirmado(conn)
    assert n == 1
    rows = conn.execute("SELECT cpf, nome_socio FROM socios_cpf_confirmado").fetchall()
    assert len(rows) == 1
    assert rows[0]["cpf"] == "00112345699"


def test_socio_sem_cpf_mascarado_nao_confirma(conn):
    _add_fornecedor(conn, "111", "EMPRESA A", [
        {"nome_socio": "JOAO DA SILVA", "cnpj_cpf_do_socio": None,
         "qualificacao_socio": "Sócio"},
    ])
    _add_doacao(conn, "JOAO DA SILVA", "00112345699", "RIO DE JANEIRO",
                "Vereador", "FULANO", 1000.0, "sq1")
    conn.commit()
    assert matches_confirmados(conn) == []


# ── ingestão ────────────────────────────────────────────────────────────────

def test_ingerir_ignora_pj(conn, tmp_path):
    csv = tmp_path / "receitas.csv"
    linhas = [
        "NR_CPF_CNPJ_DOADOR;NM_DOADOR;NM_UE;DS_CARGO;NM_CANDIDATO;SQ_CANDIDATO;SG_PARTIDO;VR_RECEITA;DT_RECEITA;SQ_RECEITA",
        "00112345699;JOAO DA SILVA;RIO DE JANEIRO;Vereador;FULANO;9;XX;1.000,00;01/08/2024;sq1",
        "12345678000190;EMPRESA X LTDA;RIO DE JANEIRO;Vereador;FULANO;9;XX;5.000,00;01/08/2024;sq2",
    ]
    csv.write_text("\n".join(linhas), encoding="latin-1")

    resumo = ingerir_receitas(conn, Path(csv), 2024, "RJ")
    assert resumo["doacoes_pf_inseridas"] == 1
    assert resumo["pj_ignoradas"] == 1
    total = conn.execute("SELECT COUNT(*) FROM doacoes_campanha").fetchone()[0]
    assert total == 1


# ── detector: severidade ─────────────────────────────────────────────────────

def test_detector_alta_alinhado_e_grande(conn):
    _add_fornecedor(conn, "111", "CONSTRUTORA GRANDE", [
        {"nome_socio": "JOAO DA SILVA", "cnpj_cpf_do_socio": "***123456**",
         "qualificacao_socio": "Sócio-Administrador"},
    ])
    _add_contrato(conn, "pncp1", "111", 50_000_000, "Rio de Janeiro")
    _add_doacao(conn, "JOAO DA SILVA", "00112345699", "RIO DE JANEIRO",
                "Vereador", "FULANO", 5000.0, "sq1")
    conn.commit()

    res = detectar(conn)
    assert len(res) == 1
    a = res[0]
    assert a.tipo == "socio_doou_campanha"
    assert a.severidade == "alta"  # alinhado + contrato >= 10M
    assert a.metricas["alinhado_municipio"] is True
    assert "pncp1" in a.contratos


def test_detector_baixa_nao_alinhado_e_pequeno(conn):
    _add_fornecedor(conn, "222", "EMPRESA PEQUENA", [
        {"nome_socio": "MARIA SOUZA", "cnpj_cpf_do_socio": "***654321**",
         "qualificacao_socio": "Sócio"},
    ])
    _add_contrato(conn, "pncp2", "222", 500_000, "Rio de Janeiro")
    # doação em OUTRO município (Niterói) -> não alinhado
    _add_doacao(conn, "MARIA SOUZA", "00165432199", "NITEROI",
                "Vereador", "BELTRANO", 1000.0, "sq3")
    conn.commit()

    res = detectar(conn)
    assert len(res) == 1
    assert res[0].severidade == "baixa"
    assert res[0].metricas["alinhado_municipio"] is False


def test_detector_sem_contrato_nao_gera_alerta(conn):
    _add_fornecedor(conn, "333", "SEM CONTRATO", [
        {"nome_socio": "JOAO DA SILVA", "cnpj_cpf_do_socio": "***123456**"},
    ])
    _add_doacao(conn, "JOAO DA SILVA", "00112345699", "RIO DE JANEIRO",
                "Vereador", "FULANO", 5000.0, "sq1")
    conn.commit()
    assert detectar(conn) == []
