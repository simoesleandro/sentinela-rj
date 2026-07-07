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


def test_prioritario_por_alerta_severidade_alta_mesmo_sem_reforco_de_nome():
    """Alerta de contrato de severidade alta é evidência independente — não
    precisa de contrato_ativo nem de qtd>=2 pra priorizar."""
    assert calcular_prioridade_investigacao(False, 1, "compativel", tem_alerta_severidade_alta=True) is True


def test_prioritario_por_sancao_mesmo_sem_reforco_de_nome():
    assert calcular_prioridade_investigacao(False, 1, "compativel", tem_sancao=True) is True


def test_alerta_e_sancao_nao_priorizam_se_incompativel():
    """Nenhuma evidência independente supera um sinal de falso positivo
    (idade improvável) — 'incompativel' sempre bloqueia."""
    assert (
        calcular_prioridade_investigacao(
            False, 1, "incompativel", tem_alerta_severidade_alta=True, tem_sancao=True
        )
        is False
    )


def test_sem_nenhum_sinal_nao_e_prioritario():
    assert calcular_prioridade_investigacao(False, 1, "compativel") is False
    assert calcular_prioridade_investigacao(False, 1, "compativel", False, False) is False
