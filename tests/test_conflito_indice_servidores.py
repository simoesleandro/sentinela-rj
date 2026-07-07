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


def test_indexa_por_primeiro_token():
    conn = _conn_servidores([("1", "MARIA DA SILVA"), ("2", "JOAO SOUZA")])
    indice = IndiceServidoresPorToken(conn)

    assert indice.candidatos("MARIA") == [("1", "MARIA SILVA")]
    assert indice.candidatos("JOAO") == [("2", "JOAO SOUZA")]
    # bloqueio é pelo primeiro token — o sobrenome não indexa nada
    assert indice.candidatos("SILVA") == []
    assert indice.candidatos("SOUZA") == []


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


def test_frequencia_nome_conta_homonimos_exatos():
    conn = _conn_servidores(
        [
            ("1", "LUIZ CARLOS SILVA"),
            ("2", "LUIZ CARLOS SILVA"),
            ("3", "LUIZ CARLOS SILVA"),
            ("4", "JOAO SOUZA"),
        ]
    )
    indice = IndiceServidoresPorToken(conn)

    assert indice.frequencia_nome("LUIZ CARLOS SILVA") == 3
    assert indice.frequencia_nome("JOAO SOUZA") == 1


def test_frequencia_nome_nao_conta_nomes_so_parecidos():
    """Frequência é de nome EXATO (pós-normalização), não fuzzy — diferente
    do problema de match do matcher.py."""
    conn = _conn_servidores(
        [
            ("1", "LEANDRO SILVA"),
            ("2", "LEANDRO SILVA MELO"),
            ("3", "LEANDRO GOMES SILVA"),
        ]
    )
    indice = IndiceServidoresPorToken(conn)

    assert indice.frequencia_nome("LEANDRO SILVA") == 1


def test_frequencia_nome_inexistente_retorna_zero():
    conn = _conn_servidores([("1", "MARIA DA SILVA")])
    indice = IndiceServidoresPorToken(conn)

    assert indice.frequencia_nome("PEDRO ALVES") == 0


def test_frequencia_nome_vazio_retorna_zero():
    conn = _conn_servidores([("1", "MARIA DA SILVA")])
    indice = IndiceServidoresPorToken(conn)

    assert indice.frequencia_nome("") == 0
