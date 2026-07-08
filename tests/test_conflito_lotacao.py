"""Testes para conflito_interesse/lotacao.py — cruzamento lotação × órgão contratante."""
from __future__ import annotations

import sqlite3

from conflito_interesse.enriquecimento import enriquecer_candidatos
from conflito_interesse.indice_servidores import IndiceServidoresPorToken
from conflito_interesse.lotacao import (
    lotacao_bate_orgao,
    prefixo_processo,
    prefixos_processo_fornecedor,
    raiz_sigla_ua,
)
from conflito_interesse.matcher import CandidatoConflito
from conflito_interesse.priorizacao import calcular_prioridade_investigacao


# ── raiz_sigla_ua ────────────────────────────────────────────────────────────

def test_raiz_extrai_primeiro_segmento():
    assert raiz_sigla_ua("S/SUBPAV/CAP-3.3/DVS") == "S"
    assert raiz_sigla_ua("E/CRE(05.15.017)") == "E"
    assert raiz_sigla_ua("GM/IG/DOP/SUBTRAN") == "GM"
    assert raiz_sigla_ua("COMLURB") == "COMLURB"


def test_raiz_normaliza_caixa_e_espacos():
    assert raiz_sigla_ua("  sms ") == "SMS"


def test_raiz_funprevi_e_vazio_nao_se_aplicam():
    # FUNPREVI = aposentado, sem lotação atual — o sinal não se aplica.
    assert raiz_sigla_ua("FUNPREVI (SME)") is None
    assert raiz_sigla_ua(None) is None
    assert raiz_sigla_ua("") is None


# ── prefixo_processo ─────────────────────────────────────────────────────────

def test_prefixo_processo_extrai_orgao():
    assert prefixo_processo("SMS-PRO-2024/15702") == "SMS"
    assert prefixo_processo("sme-pro-2024/73517") == "SME"
    assert prefixo_processo("GM-PRO-2024/04356") == "GM"


def test_prefixo_processo_formatos_sem_orgao():
    # Formato numérico antigo ("09/003.732/2022") não tem prefixo de órgão.
    assert prefixo_processo("09/003.732/2022") is None
    assert prefixo_processo(None) is None
    assert prefixo_processo("") is None


# ── prefixos_processo_fornecedor ─────────────────────────────────────────────

def _conn(contratos: list[tuple[str, float, str | None]]) -> sqlite3.Connection:
    """contratos: [(fornecedor_ni, valor_global, processo)]."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE contratos (numero_controle_pncp TEXT PRIMARY KEY, fornecedor_ni TEXT, "
        "data_vigencia_inicio TEXT, data_vigencia_fim TEXT, valor_global REAL, processo TEXT)"
    )
    for i, (ni, valor, processo) in enumerate(contratos):
        conn.execute(
            "INSERT INTO contratos VALUES (?, ?, '2020-01-01', '2030-01-01', ?, ?)",
            (f"pncp-{i}", ni, valor, processo),
        )
    conn.execute("CREATE TABLE alertas (numero_controle_pncp TEXT, severidade TEXT)")
    conn.execute("CREATE TABLE fornecedor_sancoes (fornecedor_ni TEXT)")
    conn.commit()
    return conn


def test_prefixos_do_fornecedor_distintos_e_sem_nulos():
    conn = _conn([
        ("111", 1000.0, "SMS-PRO-2024/1"),
        ("111", 2000.0, "SMS-PRO-2024/2"),
        ("111", 3000.0, "SME-PRO-2024/3"),
        ("111", 4000.0, "09/003.732/2022"),  # sem prefixo → ignorado
        ("111", 5000.0, None),
        ("222", 9000.0, "GM-PRO-2024/9"),    # outro fornecedor
    ])
    assert prefixos_processo_fornecedor(conn, "111") == frozenset({"SMS", "SME"})


def test_prefixos_ignora_contratos_sem_valor():
    conn = _conn([("111", 0.0, "SMS-PRO-2024/1")])
    assert prefixos_processo_fornecedor(conn, "111") == frozenset()


# ── lotacao_bate_orgao ───────────────────────────────────────────────────────

def test_bate_saude_educacao_e_riosaude():
    assert lotacao_bate_orgao("S/SUBPAV/CAP-3.3", frozenset({"SMS"})) is True
    assert lotacao_bate_orgao("E/CRE(05.15.017)", frozenset({"SME"})) is True
    assert lotacao_bate_orgao("RS/PRE/NG-HMRG", frozenset({"RSU"})) is True
    assert lotacao_bate_orgao("RS/PRE/NG-HMRG", frozenset({"SMS"})) is True


def test_nao_bate_orgao_diferente_ou_fora_do_mapa():
    assert lotacao_bate_orgao("E/CRE(05.15.017)", frozenset({"SMS"})) is False
    # COMLURB: sem contratos no recorte PNCP municipal — fora do mapa de propósito.
    assert lotacao_bate_orgao("COMLURB", frozenset({"SMS", "SME"})) is False
    assert lotacao_bate_orgao("FUNPREVI (SME)", frozenset({"SME"})) is False
    assert lotacao_bate_orgao(None, frozenset({"SMS"})) is False
    assert lotacao_bate_orgao("S/SUBPAV", frozenset()) is False


# ── integração com o enriquecimento ──────────────────────────────────────────

def _indice() -> IndiceServidoresPorToken:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE servidores (matricula TEXT PRIMARY KEY, nome_atual TEXT NOT NULL)")
    conn.execute("CREATE TABLE folha_mensal (matricula TEXT, sigla_ua TEXT, competencia TEXT)")
    conn.commit()
    return IndiceServidoresPorToken(conn)


def test_enriquecimento_preenche_lotacao_orgao_contratante():
    conn = _conn([("111", 1000.0, "SME-PRO-2024/1")])
    candidatos = [
        CandidatoConflito(
            fornecedor_ni="111", nome_socio="MARIA SILVA", qualificacao_socio=None,
            matricula_servidor="M1", nome_servidor="MARIA SILVA",
            sigla_ua="E/CRE(05.15.017)", score_similaridade=100.0,
        ),
        CandidatoConflito(
            fornecedor_ni="111", nome_socio="JOAO SOUZA", qualificacao_socio=None,
            matricula_servidor="M2", nome_servidor="JOAO SOUZA",
            sigla_ua="GM/IG/DOP", score_similaridade=100.0,
        ),
    ]
    enriquecidos = enriquecer_candidatos(candidatos, conn, _indice())
    por_matricula = {c.matricula_servidor: c for c in enriquecidos}
    assert por_matricula["M1"].lotacao_orgao_contratante is True   # E × SME
    assert por_matricula["M2"].lotacao_orgao_contratante is False  # GM × SME


# ── priorização ──────────────────────────────────────────────────────────────

def test_lotacao_sozinha_torna_prioritario():
    assert calcular_prioridade_investigacao(
        contrato_ativo=False,
        qtd_servidores_matched_mesmo_socio=1,
        compatibilidade_data="compativel",
        lotacao_orgao_contratante=True,
    ) is True


def test_idade_incompativel_veta_mesmo_com_lotacao():
    assert calcular_prioridade_investigacao(
        contrato_ativo=True,
        qtd_servidores_matched_mesmo_socio=5,
        compatibilidade_data="incompativel",
        lotacao_orgao_contratante=True,
    ) is False
