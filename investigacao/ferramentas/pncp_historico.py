"""Busca histórico completo de contratos do fornecedor no PNCP."""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_PNCP_BASE = "https://pncp.gov.br/api/pncp/v1"
_TIMEOUT = 15
_MAX_PAGINAS = 5
_TAMANHO_PAGINA = 20


def buscar_historico_fornecedor(
    fornecedor_ni: str,
    *,
    ano_inicio: int = 2022,
) -> dict:
    """Retorna contratos anteriores do fornecedor no PNCP."""
    if not fornecedor_ni:
        return {"contratos": [], "total": 0, "erro": "fornecedor_ni vazio"}

    contratos = []
    for pagina in range(1, _MAX_PAGINAS + 1):
        try:
            url = f"{_PNCP_BASE}/contratos/fornecedor/{fornecedor_ni}"
            params = {
                "pagina": pagina,
                "tamanhoPagina": _TAMANHO_PAGINA,
                "anoInicio": ano_inicio,
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
            logger.warning("PNCP histórico fornecedor falhou p=%d: %s", pagina, exc)
            break

    total_valor = sum(
        float(c.get("valorGlobal") or c.get("valor_global") or 0)
        for c in contratos
    )
    orgaos = list({
        (c.get("orgaoEntidade") or {}).get("razaoSocial", "")
        or c.get("orgao_nome", "")
        for c in contratos
        if (c.get("orgaoEntidade") or {}).get("razaoSocial") or c.get("orgao_nome")
    })

    return {
        "contratos": contratos,
        "total": len(contratos),
        "total_valor": total_valor,
        "orgaos_distintos": orgaos,
        "resumo": (
            f"{len(contratos)} contratos encontrados desde {ano_inicio}, "
            f"valor total R$ {total_valor:,.2f}, "
            f"{len(orgaos)} órgãos distintos."
        ),
    }
