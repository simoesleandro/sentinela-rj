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


def _conn_servidores(
    pares: list[tuple[str, str]],
    folha_mensal: list[tuple[str, str, str]] | None = None,
) -> sqlite3.Connection:
    """servidores + folha_mensal no mesmo db :memory: (mesmo arquivo em produção)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE servidores (matricula TEXT PRIMARY KEY, nome_atual TEXT NOT NULL)")
    conn.executemany("INSERT INTO servidores VALUES (?, ?)", pares)
    conn.execute("CREATE TABLE folha_mensal (matricula TEXT, sigla_ua TEXT, competencia TEXT)")
    if folha_mensal:
        conn.executemany("INSERT INTO folha_mensal VALUES (?, ?, ?)", folha_mensal)
    conn.commit()
    return conn


def _socios_json(
    nome_socio: str,
    qualificacao: str = "Sócio-Administrador",
    data_entrada_sociedade: str | None = None,
    faixa_etaria: str | None = None,
) -> str:
    socio = {"nome_socio": nome_socio, "qualificacao_socio": qualificacao}
    if data_entrada_sociedade is not None:
        socio["data_entrada_sociedade"] = data_entrada_sociedade
    if faixa_etaria is not None:
        socio["faixa_etaria"] = faixa_etaria
    return json.dumps([socio])


def test_match_positivo_nome_batendo():
    conn_forn = _conn_fornecedores(
        [(
            "12345678000199",
            _socios_json(
                "MARIA DA SILVA SANTOS",
                data_entrada_sociedade="2010-05-01",
                faixa_etaria="41 a 50 anos",
            ),
        )]
    )
    conn_serv = _conn_servidores(
        [("0001", "MARIA DA SILVA SANTOS")],
        folha_mensal=[("0001", "SMS", "2024-01-01"), ("0001", "SMS", "2015-03-01")],
    )
    indice = IndiceServidoresPorToken(conn_serv)

    candidatos = ConflictMatcherService(conn_forn, indice).buscar_candidatos()

    assert len(candidatos) == 1
    c = candidatos[0]
    assert c.fornecedor_ni == "12345678000199"
    assert c.matricula_servidor == "0001"
    assert c.nome_servidor == "MARIA SILVA SANTOS"
    assert c.qualificacao_socio == "Sócio-Administrador"
    assert c.sigla_ua == "SMS"
    assert c.score_similaridade >= 90
    assert c.data_entrada_sociedade == "2010-05-01"
    assert c.faixa_etaria_socio == "41 a 50 anos"
    assert c.primeira_competencia_servidor == "2015-03-01"


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


def test_sigla_ua_fica_none_quando_servidor_sem_folha_mensal():
    conn_forn = _conn_fornecedores([("12345678000199", _socios_json("MARIA DA SILVA SANTOS"))])
    conn_serv = _conn_servidores([("0001", "MARIA DA SILVA SANTOS")])  # sem folha_mensal
    indice = IndiceServidoresPorToken(conn_serv)

    candidatos = ConflictMatcherService(conn_forn, indice).buscar_candidatos()

    assert len(candidatos) == 1
    assert candidatos[0].sigla_ua is None
    assert candidatos[0].primeira_competencia_servidor is None


def test_campos_extras_ausentes_no_json_ficam_none():
    """Sócio sem data_entrada_sociedade/faixa_etaria no JSON (schema antigo,
    ou brasilapi não retornou o campo) não deve quebrar o matcher."""
    conn_forn = _conn_fornecedores([("12345678000199", _socios_json("MARIA DA SILVA SANTOS"))])
    conn_serv = _conn_servidores([("0001", "MARIA DA SILVA SANTOS")])
    indice = IndiceServidoresPorToken(conn_serv)

    candidatos = ConflictMatcherService(conn_forn, indice).buscar_candidatos()

    assert len(candidatos) == 1
    assert candidatos[0].data_entrada_sociedade is None
    assert candidatos[0].faixa_etaria_socio is None
