"""Prioridade de investigação: ordena a fila de revisão manual por relevância
real, sem inventar um novo critério de score de nome.

Não é persistida — calculada a cada listagem a partir de sinais que já
existem na linha (contrato_ativo, qtd_servidores_matched_mesmo_socio,
tem_alerta_severidade_alta, tem_sancao) e da compatibilidade de data
(calculada em [[compatibilidade]]).
"""
from __future__ import annotations


def calcular_prioridade_investigacao(
    contrato_ativo: bool | None,
    qtd_servidores_matched_mesmo_socio: int | None,
    compatibilidade_data: str | None,
    tem_alerta_severidade_alta: bool | None = False,
    tem_sancao: bool | None = False,
) -> bool:
    """True quando o candidato merece revisão prioritária.

    Nada que já indique falso positivo (idade improvável) nunca é
    prioritário, mesmo com os outros sinais batendo.

    Dentro disso, prioriza por QUALQUER UMA de duas evidências
    independentes:
    - fornecedor com contrato vigente E o MESMO sócio batendo com mais de
      um servidor (não apenas vários sócios distintos do fornecedor
      batendo cada um com o seu);
    - o fornecedor já tem alerta de contrato de severidade alta OU já foi
      sancionado — evidência de irregularidade que não depende da
      qualidade do match de nome sócio-servidor, então reforça o caso
      mesmo quando os dois primeiros sinais não batem.
    """
    if compatibilidade_data == "incompativel":
        return False

    reforco_nome = bool(contrato_ativo) and (qtd_servidores_matched_mesmo_socio or 0) >= 2
    return reforco_nome or bool(tem_alerta_severidade_alta) or bool(tem_sancao)
