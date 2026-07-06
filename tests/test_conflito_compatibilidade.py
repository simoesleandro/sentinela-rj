"""Testes para conflito_interesse/compatibilidade.py."""
from __future__ import annotations

from datetime import date

from conflito_interesse.compatibilidade import calcular_compatibilidade


def test_caso_compativel_idade_de_ingresso_plausivel():
    # Faixa "31 a 40 anos" (meio = 35.5) em 2026 -> nascimento ~1990.5.
    # Ingressou em 2015 -> ~24.5 anos, plausível.
    assert (
        calcular_compatibilidade("31 a 40 anos", "2015-03-01", ano_referencia=2026)
        == "compativel"
    )


def test_caso_incompativel_idade_de_ingresso_improvavel():
    # Faixa "61 a 70 anos" (meio = 65.5) em 2026 -> nascimento ~1960.5.
    # Primeira competência em 1970 -> ~9.5 anos, biologicamente implausível.
    assert (
        calcular_compatibilidade("61 a 70 anos", "1970-01-01", ano_referencia=2026)
        == "incompativel"
    )


def test_faixa_etaria_ausente_nao_quebra():
    assert calcular_compatibilidade(None, "2015-03-01", ano_referencia=2026) is None
    assert calcular_compatibilidade("", "2015-03-01", ano_referencia=2026) is None


def test_primeira_competencia_ausente_nao_quebra():
    assert calcular_compatibilidade("31 a 40 anos", None, ano_referencia=2026) is None


def test_faixa_em_formato_nao_reconhecido_retorna_none():
    assert calcular_compatibilidade("idade desconhecida", "2015-03-01", ano_referencia=2026) is None


def test_faixa_maior_que_e_reconhecida():
    # "Maior que 80 anos" -> idade estimada 80, nascimento ~1946.
    # Ingresso em 1990 -> ~44 anos, plausível.
    assert (
        calcular_compatibilidade("Maior que 80 anos", "1990-01-01", ano_referencia=2026)
        == "compativel"
    )


def test_limite_proximo_a_16_anos():
    # Faixa "31 a 40 anos" (meio = 35.5) em 2026 -> nascimento 1990.5.
    # Ingresso em 2006 -> ~15.5 anos (abaixo do limite, incompatível).
    # Ingresso em 2007 -> ~16.5 anos (acima do limite, compatível).
    assert (
        calcular_compatibilidade("31 a 40 anos", "2006-01-01", ano_referencia=2026)
        == "incompativel"
    )
    assert (
        calcular_compatibilidade("31 a 40 anos", "2007-01-01", ano_referencia=2026)
        == "compativel"
    )


def test_aceita_objeto_date_alem_de_string_iso():
    assert (
        calcular_compatibilidade("31 a 40 anos", date(2015, 3, 1), ano_referencia=2026)
        == "compativel"
    )
