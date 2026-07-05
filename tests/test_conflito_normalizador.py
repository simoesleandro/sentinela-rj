"""Testes para conflito_interesse/normalizador.py."""
from __future__ import annotations

from conflito_interesse.normalizador import normalizar_nome


def test_normaliza_maiusculas_e_remove_acentos():
    assert normalizar_nome("José Antônio da Silva") == "JOSE ANTONIO SILVA"


def test_remove_preposicoes_soltas():
    assert normalizar_nome("Maria de Souza") == "MARIA SOUZA"
    assert normalizar_nome("João dos Santos") == "JOAO SANTOS"
    assert normalizar_nome("Ana Paula do Nascimento") == "ANA PAULA NASCIMENTO"


def test_colapsa_espacos_multiplos():
    assert normalizar_nome("MARIA    DA   SILVA") == "MARIA SILVA"


def test_ordem_de_nome_invertida_nao_e_reordenada():
    """O normalizador só limpa o texto — não decide se duas ordens de nome
    batem, isso é responsabilidade do fuzzy matching (token_sort_ratio) no
    ConflictMatcherService, não do normalizador.
    """
    assert normalizar_nome("SILVA SANTOS MARIA") != normalizar_nome("MARIA SILVA SANTOS")
    assert normalizar_nome("SILVA SANTOS MARIA") == "SILVA SANTOS MARIA"


def test_string_vazia_ou_none():
    assert normalizar_nome("") == ""
    assert normalizar_nome(None) == ""
