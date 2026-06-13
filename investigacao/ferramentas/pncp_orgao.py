"""Busca histórico de contratos do órgão contratante no PNCP."""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_PNCP_BASE = "https://pncp.gov.br/api/pncp/v1"
_TIMEOUT = 15
_MAX_PAGINAS = 3
_TAMANHO_PAGINA = 20


def buscar_historico_orgao(
    orgao_cnpj: str,
    *,
    ano: int = 2024,
) -> dict:
    """Retorna contratos recentes do órgão para contexto."""
    if not orgao_cnpj:
        return {"contratos": [], "total": 0, "erro": "orgao_cnpj vazio"}

    cnpj_limpo = orgao_cnpj.replace(".", "").replace("/", "").replace("-", "")
    contratos = []

    for pagina in range(1, _MAX_PAGINAS + 1):
        try:
            url = f"{_PNCP_BASE}/orgaos/{cnpj_limpo}/contratos"
            params = {
                "pagina": pagina,
                "tamanhoPagina": _TAMANHO_PAGINA,
                "ano": ano,
            }
            resp = requests.get(url, params=params, timeout=_TIMEOUT)
            if resp.status_code == 404:
                break
            resp.raise_for_status()
            dados = resp.json()
            itens = dados.get("data", []) or dados.get("contratos", []) or []
            if not itens:
                break
            contratos.extend(itens)
            if len(itens) < _TAMANHO_PAGINA:
                break
        except requests.RequestException as exc:
            logger.warning("PNCP histórico órgão falhou p=%d: %s", pagina, exc)
            break

    total_valor = sum(
        float(c.get("valorGlobal") or c.get("valor_global") or 0)
        for c in contratos
    )

    return {
        "contratos": contratos,
        "total": len(contratos),
        "total_valor": total_valor,
        "resumo": (
            f"Órgão possui {len(contratos)} contratos em {ano}, "
            f"valor total R$ {total_valor:,.2f}."
        ),
    }
