"""Busca processos judiciais do fornecedor no TJRJ via Playwright (consulta pública por nome)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# URLs do TJRJ
_TJRJ_CONSULTA_URL = "https://www3.tjrj.jus.br/consultaprocessual/#/consultapornome"
_TIMEOUT_NAV = 30000   # ms — navegação
_TIMEOUT_EL = 15000   # ms — elementos
_MAX_PROCESSOS = 10

# LIMITAÇÃO CONHECIDA (jun/2026):
# A consulta por CPF/CNPJ no TJRJ exige login (Consulta Processual Privada).
# Esta implementação usa a consulta pública por nome da empresa — sem login.
# Pode retornar falsos positivos para nomes comuns.
# Issue #1 documenta a alternativa futura com credencial.


def buscar_processos_tjrj(
    cnpj: str | None = None,
    nome_empresa: str | None = None,
) -> dict:
    """Busca processos no TJRJ pela razão social do fornecedor via Playwright."""
    termo = nome_empresa
    if not termo:
        return {
            "processos": [],
            "total": 0,
            "resumo": "Nome da empresa não fornecido — busca TJRJ ignorada.",
            "limitacao": True,
        }

    termo_busca = termo.strip()[:60]

    try:
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright não instalado — TJRJ indisponível")
        return {
            "processos": [],
            "total": 0,
            "resumo": (
                "Playwright não instalado. Execute: "
                "pip install playwright && playwright install chromium"
            ),
            "limitacao": True,
        }

    processos = []
    erro = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()

            logger.info("TJRJ — abrindo consulta por nome: %s", termo_busca)
            page.goto(_TJRJ_CONSULTA_URL, timeout=_TIMEOUT_NAV)
            page.wait_for_load_state("networkidle", timeout=_TIMEOUT_NAV)

            campo_nome = page.locator(
                "input[placeholder*='nome'], input[id*='nome'], input[name*='nome']"
            ).first
            campo_nome.wait_for(timeout=_TIMEOUT_EL)
            campo_nome.fill(termo_busca)

            try:
                campo_ano_ini = page.locator(
                    "input[placeholder*='Ano Inicial'], "
                    "input[id*='anoIni'], input[name*='anoIni']"
                ).first
                campo_ano_ini.fill("2020")
            except Exception:
                pass

            page.locator(
                "button:has-text('Pesquisar'), "
                "input[type='submit'][value*='Pesquisar']"
            ).first.click()

            try:
                page.wait_for_selector(
                    "table tbody tr, .resultado-consulta, .processo-item, "
                    "[class*='processo']",
                    timeout=_TIMEOUT_EL,
                )
            except PWTimeout:
                logger.info("TJRJ — sem resultados visíveis para '%s'", termo_busca)
                browser.close()
                return {
                    "processos": [],
                    "total": 0,
                    "resumo": f"Nenhum processo encontrado no TJRJ para '{termo_busca}'.",
                }

            linhas = page.locator("table tbody tr").all()
            for linha in linhas[:_MAX_PROCESSOS]:
                cols = linha.locator("td").all_text_contents()
                if not cols or len(cols) < 2:
                    continue
                processos.append({
                    "numero": cols[0].strip() if len(cols) > 0 else "",
                    "classe": cols[1].strip() if len(cols) > 1 else "",
                    "assunto": cols[2].strip() if len(cols) > 2 else "",
                    "data": cols[3].strip() if len(cols) > 3 else "",
                    "situacao": cols[4].strip() if len(cols) > 4 else "",
                    "orgao": cols[5].strip() if len(cols) > 5 else "",
                })

            browser.close()

    except PWTimeout as exc:
        erro = f"Timeout navegando no TJRJ: {exc}"
        logger.warning("TJRJ timeout para '%s': %s", termo_busca, exc)
    except Exception as exc:
        erro = str(exc)
        logger.warning("TJRJ scraping falhou para '%s': %s", termo_busca, exc)

    total = len(processos)
    if total > 0:
        resumo = (
            f"{total} processo(s) encontrado(s) no TJRJ para '{termo_busca}'. "
            f"Nota: busca por nome — verificar se são do mesmo fornecedor."
        )
    elif erro:
        resumo = f"TJRJ indisponível: {erro}"
    else:
        resumo = f"Nenhum processo encontrado no TJRJ para '{termo_busca}'."

    return {
        "processos": processos,
        "total": total,
        "resumo": resumo,
        "erro": erro,
        "termo_buscado": termo_busca,
    }
