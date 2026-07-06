"""Testes para conflito_interesse/priorizacao.py."""
from __future__ import annotations

from conflito_interesse.priorizacao import calcular_prioridade_investigacao


def test_prioritario_quando_todas_condicoes_batem():
    assert calcular_prioridade_investigacao(True, 2, "compativel") is True


def test_prioritario_quando_compatibilidade_desconhecida():
    """Sem faixa etária/competência pra calcular compatibilidade (None) não
    deve bloquear a priorização — só 'incompativel' explícito bloqueia."""
    assert calcular_prioridade_investigacao(True, 2, None) is True


def test_nao_prioritario_sem_contrato_ativo():
    assert calcular_prioridade_investigacao(False, 2, "compativel") is False
    assert calcular_prioridade_investigacao(None, 2, "compativel") is False


def test_nao_prioritario_com_apenas_um_socio():
    assert calcular_prioridade_investigacao(True, 1, "compativel") is False
    assert calcular_prioridade_investigacao(True, None, "compativel") is False


def test_nao_prioritario_quando_incompativel():
    assert calcular_prioridade_investigacao(True, 3, "incompativel") is False
