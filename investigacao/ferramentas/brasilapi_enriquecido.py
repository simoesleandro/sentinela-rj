"""Enriquecimento cadastral via BrasilAPI — além do que já existe no banco."""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_BASE = "https://brasilapi.com.br/api/cnpj/v1"
_TIMEOUT = 10


def buscar_cadastro_completo(cnpj: str) -> dict:
    """Retorna dados cadastrais completos do fornecedor."""
    if not cnpj:
        return {"erro": "CNPJ vazio"}

    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
    try:
        resp = requests.get(f"{_BASE}/{cnpj_limpo}", timeout=_TIMEOUT)
        resp.raise_for_status()
        dados = resp.json()
    except requests.RequestException as exc:
        logger.warning("BrasilAPI falhou para CNPJ %s: %s", cnpj, exc)
        return {"erro": str(exc)}

    capital = float(dados.get("capital_social") or 0)
    socios = dados.get("qsa") or []
    atividades = dados.get("cnaes_secundarios") or []

    return {
        "situacao": dados.get("descricao_situacao_cadastral"),
        "data_inicio": dados.get("data_inicio_atividade"),
        "capital_social": capital,
        "porte": dados.get("porte"),
        "natureza_juridica": dados.get("descricao_natureza_juridica"),
        "cnae_principal": dados.get("cnae_fiscal_descricao"),
        "cnaes_secundarios": [a.get("descricao") for a in atividades[:5]],
        "socios": [
            {
                "nome": s.get("nome_socio"),
                "qualificacao": s.get("qualificacao_socio"),
                "entrada": s.get("data_entrada_sociedade"),
            }
            for s in socios
        ],
        "municipio": dados.get("municipio"),
        "uf": dados.get("uf"),
        "resumo": (
            f"Capital social R$ {capital:,.2f}, "
            f"porte {dados.get('porte', '?')}, "
            f"{len(socios)} sócio(s), "
            f"ativa desde {dados.get('data_inicio_atividade', '?')}."
        ),
    }
