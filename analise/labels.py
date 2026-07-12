"""Labels compartilhadas para tipos e severidades de alertas."""
from __future__ import annotations

# Fonte canônica de rótulos de tipo — sóbria e factual, espelhando o vocabulário
# do dashboard (static/app.js TIPO_LABELS). O produto afirma indícios, não
# vereditos: nada de rótulos alarmistas ("Monopólio", "Muito Acima").
LABEL_TIPO: dict[str, str] = {
    "outlier_valor": "Outlier de valor",
    "concentracao_fornecedor": "Concentração de fornecedor",
    "sem_licitacao_inexigibilidade": "Inexigibilidade",
    "sem_licitacao_emergencia": "Emergência",
    "sem_licitacao_dispensa": "Dispensa",
    "fracionamento_ap": "Fracionamento",
    "fracionamento_empenhos": "Fracionamento de empenhos",
    "asfalto_fatiado": "Asfalto fatiado",
    "contrato_sem_empenho": "Contrato sem empenho",
    "empenho_total_dia_unico": "Empenho total em dia único",
    "empenho_acima_contrato": "Empenho acima do contrato",
    "desconto_zero_licitacao": "Desconto zero em licitação",
    "licitacao_itens_desertos": "Itens desertos na licitação",
    "socio_doou_campanha": "Sócio doou à campanha",
    "socio_compartilhado": "Sócio compartilhado",
    "adesao_carona": "Adesão a ata (carona)",
    "empresa_inativa": "Empresa inativa",
    "capital_social_baixo": "Capital social baixo",
    "empresa_jovem_contrato_grande": "Empresa jovem, contrato alto",
    "watchlist_match": "Match em Watchlist",
    "evolucao_temporal_fornecedor": "Aceleração contratual",
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
