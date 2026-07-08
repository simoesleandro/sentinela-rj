"""Classificação da qualificação do sócio — o ponto legal decisivo do domínio.

Para servidor público, participar de sociedade como COTISTA é em regra
permitido; exercer GESTÃO (administrador, gerente, diretor, presidente) é
vedado pelo estatuto dos servidores. Um candidato cuja qualificação indica
gestão é qualitativamente mais grave *se* a identidade se confirmar.

Medido em jul/2026 sobre os 966 candidatos reais: 84,7% têm qualificação de
gestão (Sócio-Administrador 515, Diretor 155, Administrador 85, Presidente 63,
Conselheiro 46) — por isso a classificação NÃO entra na fórmula de prioridade
(saturaria a fila, como o sinal qtd_socios da primeira versão). Ela informa o
revisor (selo na UI) e o parecer de IA.
"""
from __future__ import annotations

# Termos que indicam poder de gestão na qualificação do QSA (Receita/BrasilAPI).
_TERMOS_GESTAO = (
    "administrador",
    "gerente",
    "diretor",
    "presidente",
    "conselheiro",
)


def classificar_qualificacao(qualificacao: str | None) -> str | None:
    """'gestao' quando a qualificação indica poder de administração,
    'cotista' quando é participação societária simples, None sem dado."""
    if not qualificacao or not qualificacao.strip():
        return None
    q = qualificacao.strip().lower()
    if any(termo in q for termo in _TERMOS_GESTAO):
        return "gestao"
    return "cotista"
