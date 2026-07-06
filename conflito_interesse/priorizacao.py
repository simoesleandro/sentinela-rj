"""Prioridade de investigação: ordena a fila de revisão manual por relevância
real, sem inventar um novo critério de score de nome.

Não é persistida — calculada a cada listagem a partir de sinais que já
existem na linha (contrato_ativo, qtd_servidores_matched_mesmo_socio) e da
compatibilidade de data (calculada em [[compatibilidade]]).
"""
from __future__ import annotations


def calcular_prioridade_investigacao(
    contrato_ativo: bool | None,
    qtd_servidores_matched_mesmo_socio: int | None,
    compatibilidade_data: str | None,
) -> bool:
    """True quando o candidato merece revisão prioritária: fornecedor com
    contrato vigente, o MESMO sócio batendo com mais de um servidor
    (não apenas vários sócios distintos do fornecedor batendo cada um com
    o seu), e nada que já indique falso positivo (idade improvável)."""
    if not contrato_ativo:
        return False
    if (qtd_servidores_matched_mesmo_socio or 0) < 2:
        return False
    if compatibilidade_data == "incompativel":
        return False
    return True
