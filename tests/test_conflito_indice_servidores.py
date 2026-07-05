"""Testes para conflito_interesse/indice_servidores.py."""
from __future__ import annotations

import sqlite3

from conflito_interesse.indice_servidores import IndiceServidoresPorToken


def _conn_servidores(pares: list[tuple[str, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE servidores (matricula TEXT PRIMARY KEY, nome_atual TEXT NOT NULL)")
    conn.executemany("INSERT INTO servidores VALUES (?, ?)", pares)
    conn.commit()
    return conn


def test_indexa_por_primeiro_token():
    conn = _conn_servidores([("1", "MARIA DA SILVA"), ("2", "JOAO SOUZA")])
    indice = IndiceServidoresPorToken(conn)

    assert indice.candidatos("MARIA") == [("1", "MARIA SILVA")]
    assert indice.candidatos("JOAO") == [("2", "JOAO SOUZA")]


def test_colisao_de_primeiro_token_retorna_todos_os_candidatos():
    conn = _conn_servidores(
        [
            ("1", "MARIA DA SILVA"),
            ("2", "MARIA APARECIDA SOUZA"),
            ("3", "MARIA JOSE LIMA"),
        ]
    )
    indice = IndiceServidoresPorToken(conn)

    candidatos = indice.candidatos("MARIA")

    assert len(candidatos) == 3
    assert ("1", "MARIA SILVA") in candidatos
    assert ("2", "MARIA APARECIDA SOUZA") in candidatos
    assert ("3", "MARIA JOSE LIMA") in candidatos


def test_token_sem_correspondencia_retorna_lista_vazia():
    conn = _conn_servidores([("1", "MARIA DA SILVA")])
    indice = IndiceServidoresPorToken(conn)

    assert indice.candidatos("PEDRO") == []


def test_nome_vazio_apos_normalizacao_e_ignorado():
    conn = _conn_servidores([("1", "   ")])
    indice = IndiceServidoresPorToken(conn)

    assert indice.candidatos("") == []
