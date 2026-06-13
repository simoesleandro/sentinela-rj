"""Busca decisões do TCM-RJ sobre o órgão/fornecedor via Playwright."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_TCM_URL = "https://etcm.tcmrio.tc.br/Processo/Home"
_TIMEOUT = 30000  # ms


def buscar_decisoes_tcm(
    orgao_nome: str | None = None,
    fornecedor_nome: str | None = None,
) -> dict:
    """Busca processos/decisões no TCM-RJ via Playwright."""
    termo = fornecedor_nome or orgao_nome
    if not termo:
        return {"decisoes": [], "total": 0, "erro": "Nome vazio"}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright não instalado — TCM-RJ indisponível")
        return {
            "decisoes": [],
            "total": 0,
            "erro": (
                "Playwright não instalado. Instale com: "
                "pip install playwright && playwright install chromium"
            ),
        }

    decisoes = []
    erro = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(_TCM_URL, timeout=_TIMEOUT)

            page.wait_for_selector(
                "input[placeholder*='interessado'], "
                "input[name*='interessado'], input[id*='interessado']",
                timeout=10000,
            )

            campo = page.locator(
                "input[placeholder*='interessado'], "
                "input[name*='interessado'], input[id*='interessado']"
            ).first
            campo.fill(termo[:50])

            page.locator(
                "button[type='submit'], button:has-text('Pesquisar'), "
                "input[type='submit']"
            ).first.click()

            page.wait_for_load_state("networkidle", timeout=15000)

            linhas = page.locator("table tbody tr").all()
            for linha in linhas[:10]:
                colunas = linha.locator("td").all_text_contents()
                if colunas:
                    decisoes.append({
                        "numero": colunas[0].strip() if len(colunas) > 0 else "",
                        "assunto": colunas[1].strip() if len(colunas) > 1 else "",
                        "interessado": colunas[2].strip() if len(colunas) > 2 else "",
                        "situacao": colunas[3].strip() if len(colunas) > 3 else "",
                        "data": colunas[4].strip() if len(colunas) > 4 else "",
                    })

            browser.close()

    except Exception as exc:
        logger.warning("TCM-RJ scraping falhou para '%s': %s", termo, exc)
        erro = str(exc)

    resumo = (
        f"{len(decisoes)} processo(s) encontrado(s) no TCM-RJ para '{termo}'."
        if decisoes
        else f"Nenhum processo encontrado no TCM-RJ para '{termo}'."
    )

    return {
        "decisoes": decisoes,
        "total": len(decisoes),
        "resumo": resumo,
        "erro": erro,
    }
