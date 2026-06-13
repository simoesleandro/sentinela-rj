"""Busca processos judiciais do fornecedor no TJRJ.

LIMITAÇÃO PERMANENTE (jun/2026):
O portal de consulta processual do TJRJ é uma SPA Angular que não renderiza
em modo headless. O endpoint legado (www4.tjrj.jus.br) foi desativado.
A busca por CNPJ requer login na Consulta Processual Privada (credencial TJRJ).

Alternativas futuras:
- Issue #2: implementar com credencial TJRJ se obtida
- Monitorar se o TJRJ disponibilizar API pública ou endpoint REST acessível
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def buscar_processos_tjrj(
    cnpj: str | None = None,
    nome_empresa: str | None = None,
) -> dict:
    """Stub — TJRJ não acessível via automação sem credencial."""
    logger.info("TJRJ: indisponível sem credencial (SPA Angular hostil a scraping)")
    return {
        "processos": [],
        "total": 0,
        "resumo": (
            "TJRJ: consulta indisponível — portal SPA Angular não renderiza "
            "em modo headless e endpoint legado foi desativado. "
            "Verificar manualmente em tjrj.jus.br/consultas/processos-jud."
        ),
        "limitacao": True,
        "url_manual": "https://www3.tjrj.jus.br/consultaprocessual/#/consultapornome",
    }
