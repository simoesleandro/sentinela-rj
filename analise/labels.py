"""Labels compartilhadas para tipos e severidades de alertas."""
from __future__ import annotations

LABEL_TIPO: dict[str, str] = {
    "outlier_valor": "Valor Muito Acima do Padrão",
    "concentracao_fornecedor": "Monopólio de Fornecedor",
    "sem_licitacao_inexigibilidade": "Dispensa por Inexigibilidade",
    "sem_licitacao_emergencia": "Contratação de Emergência",
    "sem_licitacao_dispensa": "Dispensa de Licitação",
    "fracionamento_ap": "Fracionamento de Despesa",
    "empresa_inativa": "Empresa Inativa",
    "capital_social_baixo": "Capital Social Baixo",
    "empresa_jovem_contrato_grande": "Empresa Jovem — Contrato Grande",
    "socio_compartilhado": "Sócio Compartilhado entre Fornecedores",
    "watchlist_match": "Match em Watchlist",
    "evolucao_temporal_fornecedor": "Aceleração Contratual",
}

LABEL_SEVERIDADE: dict[str, str] = {
    "alta": "Crítico",
    "media": "Elevado",
    "baixa": "Moderado",
}

ICON_SEVERIDADE: dict[str, str] = {
    "alta": "🔴",
    "media": "🟡",
    "baixa": "🟢",
}


def label_tipo(tipo: str) -> str:
    return LABEL_TIPO.get(tipo, tipo.replace("_", " ").title())


def label_severidade(severidade: str) -> str:
    return LABEL_SEVERIDADE.get(severidade, severidade.title())


def icon_severidade(severidade: str) -> str:
    return ICON_SEVERIDADE.get(severidade, "⚪")


LABEL_STATUS: dict[str, str] = {
    "aberto": "Aberto",
    "investigando": "Investigando",
    "confirmado": "Confirmado",
    "descartado": "Descartado",
}


def label_status(status: str) -> str:
    return LABEL_STATUS.get(status, status.replace("_", " ").title())
