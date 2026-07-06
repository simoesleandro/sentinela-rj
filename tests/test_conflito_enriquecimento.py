"""Testes para conflito_interesse/enriquecimento.py."""
from __future__ import annotations

import sqlite3

from conflito_interesse.enriquecimento import (
    buscar_contrato_ativo,
    contar_servidores_por_socio,
    enriquecer_candidatos,
    somar_valor_contratos,
)
from conflito_interesse.matcher import CandidatoConflito


def _conn_contratos(contratos: list[tuple[str, str, str, float]]) -> sqlite3.Connection:
    """contratos: [(fornecedor_ni, data_vigencia_inicio, data_vigencia_fim, valor_global)]."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE contratos (fornecedor_ni TEXT, data_vigencia_inicio TEXT, "
        "data_vigencia_fim TEXT, valor_global REAL)"
    )
    conn.executemany("INSERT INTO contratos VALUES (?, ?, ?, ?)", contratos)
    conn.commit()
    return conn


def _candidato(
    fornecedor_ni: str = "12345678000199",
    matricula_servidor: str = "0001",
    nome_socio: str = "MARIA DA SILVA SANTOS",
    score_similaridade: float = 100.0,
) -> CandidatoConflito:
    return CandidatoConflito(
        fornecedor_ni=fornecedor_ni,
        nome_socio=nome_socio,
        qualificacao_socio="Presidente",
        matricula_servidor=matricula_servidor,
        nome_servidor="MARIA SILVA SANTOS",
        sigla_ua=None,
        score_similaridade=score_similaridade,
    )


def test_contrato_ativo_com_vigencia_cobrindo_hoje():
    conn = _conn_contratos([("12345678000199", "2020-01-01", "2099-01-01", 1000.0)])
    assert buscar_contrato_ativo(conn, "12345678000199") is True


def test_contrato_inativo_vigencia_encerrada():
    conn = _conn_contratos([("12345678000199", "2010-01-01", "2011-01-01", 1000.0)])
    assert buscar_contrato_ativo(conn, "12345678000199") is False


def test_contrato_inativo_vigencia_futura():
    conn = _conn_contratos([("12345678000199", "2099-01-01", "2100-01-01", 1000.0)])
    assert buscar_contrato_ativo(conn, "12345678000199") is False


def test_contrato_ativo_fornecedor_sem_contratos():
    conn = _conn_contratos([])
    assert buscar_contrato_ativo(conn, "12345678000199") is False


def test_soma_valor_contratos_varios_contratos():
    conn = _conn_contratos(
        [
            ("12345678000199", "2020-01-01", "2099-01-01", 1000.0),
            ("12345678000199", "2015-01-01", "2016-01-01", 500.5),
        ]
    )
    assert somar_valor_contratos(conn, "12345678000199") == 1500.5


def test_soma_valor_contratos_ignora_valor_zero_ou_negativo():
    conn = _conn_contratos(
        [
            ("12345678000199", "2020-01-01", "2099-01-01", 1000.0),
            ("12345678000199", "2015-01-01", "2016-01-01", 0.0),
        ]
    )
    assert somar_valor_contratos(conn, "12345678000199") == 1000.0


def test_soma_valor_contratos_sem_contratos_retorna_none():
    conn = _conn_contratos([])
    assert somar_valor_contratos(conn, "12345678000199") is None


def test_contar_servidores_por_socio_conta_matriculas_distintas_do_mesmo_socio():
    """Sinal correto: o MESMO sócio (nome idêntico) batendo com 2 servidores
    diferentes — os dois matches são exatos (score 100), então contam."""
    candidatos = [
        _candidato(fornecedor_ni="A", nome_socio="MARIA SILVA", matricula_servidor="0001"),
        _candidato(fornecedor_ni="A", nome_socio="MARIA SILVA", matricula_servidor="0002"),
        _candidato(fornecedor_ni="B", nome_socio="JOAO SOUZA", matricula_servidor="0003"),
    ]
    assert contar_servidores_por_socio(candidatos) == {
        ("A", "MARIA SILVA"): 2,
        ("B", "JOAO SOUZA"): 1,
    }


def test_contar_servidores_por_socio_nao_soma_socios_distintos_da_mesma_empresa():
    """Primeira causa do bug: fornecedor com 2 sócios REAIS distintos, cada um
    batendo isoladamente com 1 servidor, não deve contar como 2 — é só uma
    empresa com vários sócios, cada match é isolado e não reforça o outro."""
    candidatos = [
        _candidato(fornecedor_ni="A", nome_socio="MARIA SILVA", matricula_servidor="0001"),
        _candidato(fornecedor_ni="A", nome_socio="JOAO SOUZA", matricula_servidor="0002"),
    ]
    assert contar_servidores_por_socio(candidatos) == {
        ("A", "MARIA SILVA"): 1,
        ("A", "JOAO SOUZA"): 1,
    }


def test_contar_servidores_por_socio_ignora_matches_fuzzy_de_sobrenome_comum():
    """Segunda causa do bug (só apareceu depois de corrigir a primeira, com
    dados reais): agrupar por (fornecedor_ni, sócio) sozinho ainda satura,
    porque um sobrenome comum (ex.: "LEANDRO SILVA") bate via fuzzy matching
    (score 80-84) com dezenas de servidores de nome só parecido (LEANDRO
    SILVA MELO, LEANDRO GOMES SILVA...) que não são a mesma pessoa. Só
    matches de nome EXATO (score 100) devem contar para este sinal."""
    candidatos = [
        _candidato(fornecedor_ni="A", nome_socio="LEANDRO SILVA", matricula_servidor="0001", score_similaridade=100.0),
        _candidato(fornecedor_ni="A", nome_socio="LEANDRO SILVA", matricula_servidor="0002", score_similaridade=83.9),
        _candidato(fornecedor_ni="A", nome_socio="LEANDRO SILVA", matricula_servidor="0003", score_similaridade=81.25),
    ]
    assert contar_servidores_por_socio(candidatos) == {("A", "LEANDRO SILVA"): 1}


def test_contar_servidores_por_socio_nao_dobra_mesma_matricula():
    """Dois sócios diferentes do mesmo fornecedor batendo com o MESMO
    servidor não deve contar como 2 para nenhum dos dois grupos."""
    candidatos = [
        _candidato(fornecedor_ni="A", nome_socio="MARIA SILVA", matricula_servidor="0001"),
        _candidato(fornecedor_ni="A", nome_socio="MARIA SILVA", matricula_servidor="0001"),
    ]
    assert contar_servidores_por_socio(candidatos) == {("A", "MARIA SILVA"): 1}


def test_contar_servidores_por_socio_normaliza_nome_do_socio():
    """Acentuação/caixa diferentes do mesmo nome de sócio não devem quebrar
    o agrupamento em dois grupos distintos."""
    candidatos = [
        _candidato(fornecedor_ni="A", nome_socio="José da Silva", matricula_servidor="0001"),
        _candidato(fornecedor_ni="A", nome_socio="JOSE DA SILVA", matricula_servidor="0002"),
    ]
    assert contar_servidores_por_socio(candidatos) == {("A", "JOSE SILVA"): 2}


def test_enriquecer_candidatos_preenche_os_tres_sinais():
    conn = _conn_contratos([("A", "2020-01-01", "2099-01-01", 1000.0)])
    candidatos = [
        _candidato(fornecedor_ni="A", nome_socio="MARIA SILVA", matricula_servidor="0001"),
        _candidato(fornecedor_ni="A", nome_socio="MARIA SILVA", matricula_servidor="0002"),
    ]

    enriquecidos = enriquecer_candidatos(candidatos, conn)

    assert len(enriquecidos) == 2
    for c in enriquecidos:
        assert c.contrato_ativo is True
        assert c.valor_total_contratos == 1000.0
        assert c.qtd_servidores_matched_mesmo_socio == 2


def test_enriquecer_candidatos_socios_distintos_nao_saturam_o_sinal():
    """Mesmo caso de teste que expôs a primeira causa do bug: empresa com 2
    sócios reais distintos, cada um batendo isoladamente, deve ficar com o
    sinal em 1 para cada linha, não 2."""
    conn = _conn_contratos([("A", "2020-01-01", "2099-01-01", 1000.0)])
    candidatos = [
        _candidato(fornecedor_ni="A", nome_socio="MARIA SILVA", matricula_servidor="0001"),
        _candidato(fornecedor_ni="A", nome_socio="JOAO SOUZA", matricula_servidor="0002"),
    ]

    enriquecidos = enriquecer_candidatos(candidatos, conn)

    assert all(c.qtd_servidores_matched_mesmo_socio == 1 for c in enriquecidos)


def test_enriquecer_candidatos_matches_fuzzy_nao_saturam_o_sinal():
    """Mesmo caso de teste que expôs a segunda causa do bug: sobrenome comum
    batendo fuzzy com vários servidores diferentes não deve inflar o sinal —
    cada candidato fuzzy isolado fica com piso 1."""
    conn = _conn_contratos([("A", "2020-01-01", "2099-01-01", 1000.0)])
    candidatos = [
        _candidato(fornecedor_ni="A", nome_socio="LEANDRO SILVA", matricula_servidor="0001", score_similaridade=83.9),
        _candidato(fornecedor_ni="A", nome_socio="LEANDRO SILVA", matricula_servidor="0002", score_similaridade=81.25),
    ]

    enriquecidos = enriquecer_candidatos(candidatos, conn)

    assert all(c.qtd_servidores_matched_mesmo_socio == 1 for c in enriquecidos)


def test_enriquecer_candidatos_fornecedor_sem_contrato_ativo():
    conn = _conn_contratos([("A", "2010-01-01", "2011-01-01", 1000.0)])
    candidatos = [_candidato(fornecedor_ni="A")]

    enriquecidos = enriquecer_candidatos(candidatos, conn)

    assert enriquecidos[0].contrato_ativo is False
    assert enriquecidos[0].qtd_servidores_matched_mesmo_socio == 1


def test_enriquecer_candidatos_consulta_uma_vez_por_fornecedor(monkeypatch):
    """Mesmo fornecedor aparecendo várias vezes no lote não deve gerar uma
    query de contratos por linha — só uma por fornecedor_ni distinto."""
    import conflito_interesse.enriquecimento as mod

    conn = _conn_contratos([("A", "2020-01-01", "2099-01-01", 1000.0)])
    candidatos = [
        _candidato(fornecedor_ni="A", matricula_servidor="0001"),
        _candidato(fornecedor_ni="A", matricula_servidor="0002"),
        _candidato(fornecedor_ni="A", matricula_servidor="0003"),
    ]

    chamadas = {"n": 0}
    original = mod.buscar_contrato_ativo

    def _contando(conn_, ni):
        chamadas["n"] += 1
        return original(conn_, ni)

    monkeypatch.setattr(mod, "buscar_contrato_ativo", _contando)
    mod.enriquecer_candidatos(candidatos, conn)

    assert chamadas["n"] == 1


def test_enriquecer_candidatos_lista_vazia():
    conn = _conn_contratos([])
    assert enriquecer_candidatos([], conn) == []
