"""Parecer de IA sobre um candidato a conflito de interesse.

Reusa a cascata de provedores do motor central (analise.motor_ia.gerar_texto:
Gemma4 local → Gemini → Groq). A IA NÃO confirma identidade — ela sintetiza
os sinais já calculados num parecer legível, avalia a plausibilidade de os
dois nomes serem a mesma pessoa (variação cartorial vs. nomes distintos) e
recomenda os passos de verificação documental. Mesmo enquadramento da
narrativa de alertas: linguagem de auditor, não de acusação.
"""
from __future__ import annotations

from typing import Any


def _sim_nao(valor: Any) -> str:
    return "sim" if valor else "não"


def montar_prompt_candidato(item: dict[str, Any]) -> str:
    """Prompt com os sinais estruturados do candidato. `item` é o dict já
    serializado (mesmo formato da API /api/conflitos-interesse)."""
    qualificacao = item.get("qualificacao_socio") or "não informada"
    classe = item.get("qualificacao_classe")
    nota_qualificacao = {
        "gestao": (
            "qualificação indica PODER DE GESTÃO — para servidor público, "
            "administrar empresa é vedado pelo estatuto; ser cotista, em regra, não"
        ),
        "cotista": "participação societária simples (cotista) — em regra permitida a servidor",
    }.get(classe, "sem classificação")

    valor = item.get("valor_total_contratos")
    valor_txt = f"R$ {valor:,.2f}" if valor else "não informado"

    return f"""Você é um auditor de integridade analisando um CANDIDATO a conflito de interesse
entre um sócio de empresa contratada pela Prefeitura do Rio e um servidor público
municipal. O match foi feito POR NOME (não há CPF em nenhuma das fontes), portanto
HOMÔNIMOS SÃO ESPERADOS e nada aqui prova identidade.

DADOS DO CANDIDATO:
- Nome do sócio (QSA/Receita): {item.get("nome_socio")}
- Nome do servidor (folha PCRJ): {item.get("nome_servidor")}
- Score de similaridade dos nomes (0-100): {item.get("score_similaridade")}
- Homônimos exatos do servidor na base de 286 mil servidores: {item.get("qtd_servidores_mesmo_nome", 1)}
- Qualificação do sócio: {qualificacao} ({nota_qualificacao})
- Faixa etária do sócio: {item.get("faixa_etaria_socio") or "não informada"}
- Primeira competência como servidor: {item.get("primeira_competencia_servidor") or "não informada"}
- Compatibilidade etária calculada: {item.get("compatibilidade_data") or "não calculada"}
- Entrada na sociedade: {item.get("data_entrada_sociedade") or "não informada"}
- Lotação do servidor (sigla): {item.get("sigla_ua") or "não informada"}
- Servidor lotado no MESMO órgão de origem dos contratos do fornecedor: {_sim_nao(item.get("lotacao_orgao_contratante"))}
- Fornecedor tem contrato vigente: {_sim_nao(item.get("contrato_ativo"))}
- Valor total contratado pelo fornecedor: {valor_txt}
- Fornecedor já tem alerta de severidade alta: {_sim_nao(item.get("tem_alerta_severidade_alta"))}
- Fornecedor tem registro de sanção: {_sim_nao(item.get("tem_sancao"))}

TAREFA — responda em português, máximo 12 linhas, neste formato:

PLAUSIBILIDADE: [mesma pessoa provável | homônimo provável | inconclusivo]
CONFIANÇA: [alta | média | baixa]
ANÁLISE: 3-6 frases. Compare os dois nomes (a diferença é compatível com variação
cartorial — abreviação, nome de casada, inversão de sobrenomes — ou são pessoas
claramente distintas?). Considere a raridade do nome no Brasil, a compatibilidade
etária e o cruzamento de lotação. Se a qualificação indica gestão, diga o que isso
significa juridicamente SE a identidade se confirmar (Lei 14.133/2021, art. 14 e
vedação estatutária), sem afirmar que há infração.
VERIFICAR: os 2-3 passos documentais mais eficientes (ex.: certidão JUCERJA do
contrato social; busca da matrícula no Diário Oficial do Município; conferência
da qualificação no QSA).

Regras: linguagem de auditor, não de acusação; nunca afirme que É a mesma pessoa
nem que houve irregularidade; não invente dados além dos fornecidos."""


def analisar_candidato(item: dict[str, Any]) -> tuple[str, str]:
    """Gera o parecer. Retorna (texto, provedor_usado).

    Lança ValueError quando nenhum provedor de IA está disponível — o
    endpoint converte em 503, mesmo contrato de /investigar.
    """
    from analise.motor_ia import gerar_texto

    return gerar_texto(montar_prompt_candidato(item))
