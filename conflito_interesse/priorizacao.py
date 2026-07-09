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
    lotacao_orgao_contratante: bool | None = False,
) -> bool:
    """True quando o candidato merece revisão prioritária.

    Nada que já indique falso positivo (idade improvável) nunca é
    prioritário, mesmo com os outros sinais batendo.

    Dentro disso, prioriza por QUALQUER UMA de três evidências
    independentes:
    - o servidor é lotado no MESMO órgão de origem dos contratos do
      fornecedor (lotação × prefixo de processo) — o sinal mais forte do
      domínio: a Lei 14.133/2021 (art. 14) impede de licitar quem mantém
      vínculo com o órgão contratante;
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
    return (
        bool(lotacao_orgao_contratante)
        or reforco_nome
        or bool(tem_alerta_severidade_alta)
        or bool(tem_sancao)
    )


def chave_ordenacao_fila(item: dict) -> tuple:
    """Chave de ordenação da fila de revisão (menor = mais acima).

    Três níveis: prioritários primeiro; dentro deles, lotação × órgão
    contratante acima de tudo (é o sinal juridicamente mais forte — um nome
    90% igual lotado no órgão que assinou o contrato importa mais que um
    homônimo exato sem vínculo nenhum); o score de nome só desempata.
    """
    return (
        0 if item.get("prioridade_investigacao") else 1,
        0 if item.get("lotacao_orgao_contratante") else 1,
        -(item.get("score_similaridade") or 0),
    )
