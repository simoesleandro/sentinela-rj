"""Testes para conflito_interesse/indice_servidores.py."""
from __future__ import annotations

import sqlite3

from conflito_interesse.indice_servidores import IndiceServidoresPorToken


def _conn_servidores(
    pares: list[tuple[str, str]],
    folha_mensal: list[tuple[str, str, str]] | None = None,
) -> sqlite3.Connection:
    """Cria um sqlite :memory: com servidores + folha_mensal (mesmo db em produção)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE servidores (matricula TEXT PRIMARY KEY, nome_atual TEXT NOT NULL)")
    conn.executemany("INSERT INTO servidores VALUES (?, ?)", pares)
    conn.execute(
        "CREATE TABLE folha_mensal (matricula TEXT, sigla_ua TEXT, competencia TEXT)"
    )
    if folha_mensal:
        conn.executemany("INSERT INTO folha_mensal VALUES (?, ?, ?)", folha_mensal)
    conn.commit()
    return conn


def test_indexa_por_ultimo_token_sobrenome():
    conn = _conn_servidores([("1", "MARIA DA SILVA"), ("2", "JOAO SOUZA")])
    indice = IndiceServidoresPorToken(conn)

    assert indice.candidatos("SILVA") == [("1", "MARIA SILVA")]
    assert indice.candidatos("SOUZA") == [("2", "JOAO SOUZA")]
    # bloqueio agora é pelo sobrenome — o prenome não indexa nada
    assert indice.candidatos("MARIA") == []
    assert indice.candidatos("JOAO") == []


def test_colisao_de_ultimo_token_retorna_todos_os_candidatos():
    conn = _conn_servidores(
        [
            ("1", "MARIA DA SILVA"),
            ("2", "JOAO PEDRO SILVA"),
            ("3", "CARLOS ALBERTO SILVA"),
        ]
    )
    indice = IndiceServidoresPorToken(conn)

    candidatos = indice.candidatos("SILVA")

    assert len(candidatos) == 3
    assert ("1", "MARIA SILVA") in candidatos
    assert ("2", "JOAO PEDRO SILVA") in candidatos
    assert ("3", "CARLOS ALBERTO SILVA") in candidatos


def test_token_sem_correspondencia_retorna_lista_vazia():
    conn = _conn_servidores([("1", "MARIA DA SILVA")])
    indice = IndiceServidoresPorToken(conn)

    assert indice.candidatos("PEREIRA") == []


def test_nome_vazio_apos_normalizacao_e_ignorado():
    conn = _conn_servidores([("1", "   ")])
    indice = IndiceServidoresPorToken(conn)

    assert indice.candidatos("") == []


def test_sigla_ua_mais_recente_retorna_competencia_maxima():
    conn = _conn_servidores(
        [("1", "MARIA DA SILVA")],
        folha_mensal=[
            ("1", "SMS", "2021-06-01"),
            ("1", "SME", "2023-01-01"),
            ("1", "COMLURB", "2022-03-01"),
        ],
    )
    indice = IndiceServidoresPorToken(conn)

    assert indice.sigla_ua_mais_recente("1") == "SME"


def test_sigla_ua_mais_recente_sem_registros_retorna_none():
    conn = _conn_servidores([("1", "MARIA DA SILVA")])
    indice = IndiceServidoresPorToken(conn)

    assert indice.sigla_ua_mais_recente("1") is None
