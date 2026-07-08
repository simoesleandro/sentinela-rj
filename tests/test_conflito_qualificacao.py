"""Testes para conflito_interesse/qualificacao.py."""
from __future__ import annotations

from conflito_interesse.qualificacao import classificar_qualificacao


def test_qualificacoes_de_gestao():
    assert classificar_qualificacao("Sócio-Administrador") == "gestao"
    assert classificar_qualificacao("Administrador") == "gestao"
    assert classificar_qualificacao("Diretor") == "gestao"
    assert classificar_qualificacao("Presidente") == "gestao"
    assert classificar_qualificacao("Conselheiro de Administração") == "gestao"
    assert classificar_qualificacao("SÓCIO-GERENTE") == "gestao"


def test_cotista_simples():
    assert classificar_qualificacao("Sócio") == "cotista"
    assert classificar_qualificacao("Sócio Capitalista") == "cotista"


def test_sem_dado():
    assert classificar_qualificacao(None) is None
    assert classificar_qualificacao("") is None
    assert classificar_qualificacao("   ") is None
