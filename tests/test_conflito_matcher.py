"""Testes para conflito_interesse/matcher.py (ConflictMatcherService)."""
from __future__ import annotations

import json
import sqlite3

from conflito_interesse.indice_servidores import IndiceServidoresPorToken
from conflito_interesse.matcher import ConflictMatcherService


def _conn_fornecedores(fornecedores: list[tuple[str, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE fornecedor_cadastro (fornecedor_ni TEXT PRIMARY KEY, socios TEXT)")
    conn.executemany("INSERT INTO fornecedor_cadastro VALUES (?, ?)", fornecedores)
    conn.commit()
    return conn


def _conn_servidores(pares: list[tuple[str, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE servidores (matricula TEXT PRIMARY KEY, nome_atual TEXT NOT NULL)")
    conn.executemany("INSERT INTO servidores VALUES (?, ?)", pares)
    conn.commit()
    return conn


def _socios_json(nome_socio: str, qualificacao: str = "Sócio-Administrador") -> str:
    return json.dumps([{"nome_socio": nome_socio, "qualificacao_socio": qualificacao}])


def test_match_positivo_nome_batendo():
    conn_forn = _conn_fornecedores([("12345678000199", _socios_json("MARIA DA SILVA SANTOS"))])
    conn_serv = _conn_servidores([("0001", "MARIA DA SILVA SANTOS")])
    indice = IndiceServidoresPorToken(conn_serv)

    candidatos = ConflictMatcherService(conn_forn, indice).buscar_candidatos()

    assert len(candidatos) == 1
    c = candidatos[0]
    assert c.fornecedor_ni == "12345678000199"
    assert c.matricula_servidor == "0001"
    assert c.nome_servidor == "MARIA SILVA SANTOS"
    assert c.qualificacao_socio == "Sócio-Administrador"
    assert c.sigla_ua is None
    assert c.score_similaridade >= 90


def test_match_negativo_primeiro_token_diferente_nao_entra_no_indice():
    """Nome parecido, mas primeiro token diferente — nem chega a ser comparado
    via fuzzy matching, porque a busca no índice já não encontra candidatos.
    """
    conn_forn = _conn_fornecedores([("12345678000199", _socios_json("CARLOS ALBERTO SILVA SANTOS"))])
    conn_serv = _conn_servidores([("0001", "MARCOS ALBERTO SILVA SANTOS")])
    indice = IndiceServidoresPorToken(conn_serv)

    candidatos = ConflictMatcherService(conn_forn, indice).buscar_candidatos()

    assert candidatos == []


def test_score_abaixo_do_minimo_e_descartado():
    conn_forn = _conn_fornecedores([("12345678000199", _socios_json("MARIA SILVA"))])
    conn_serv = _conn_servidores([("0001", "MARIA OLIVEIRA COSTA PEREIRA")])
    indice = IndiceServidoresPorToken(conn_serv)

    candidatos = ConflictMatcherService(conn_forn, indice).buscar_candidatos()

    assert candidatos == []


def test_multiplos_socios_no_mesmo_fornecedor_geram_multiplos_candidatos():
    socios = json.dumps(
        [
            {"nome_socio": "MARIA DA SILVA SANTOS", "qualificacao_socio": "Presidente"},
            {"nome_socio": "JOAO DE SOUZA LIMA", "qualificacao_socio": "Sócio"},
        ]
    )
    conn_forn = _conn_fornecedores([("12345678000199", socios)])
    conn_serv = _conn_servidores(
        [("0001", "MARIA DA SILVA SANTOS"), ("0002", "JOAO DE SOUZA LIMA")]
    )
    indice = IndiceServidoresPorToken(conn_serv)

    candidatos = ConflictMatcherService(conn_forn, indice).buscar_candidatos()

    assert len(candidatos) == 2
    assert {c.matricula_servidor for c in candidatos} == {"0001", "0002"}


def test_fornecedor_sem_socios_e_ignorado():
    conn_forn = _conn_fornecedores([("12345678000199", None), ("98765432000100", "")])
    conn_serv = _conn_servidores([("0001", "MARIA DA SILVA SANTOS")])
    indice = IndiceServidoresPorToken(conn_serv)

    candidatos = ConflictMatcherService(conn_forn, indice).buscar_candidatos()

    assert candidatos == []
