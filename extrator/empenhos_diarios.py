"""Coleta diária de contratos/empenhos via PNCP filtrado pelo CNPJ da Prefeitura do Rio."""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Any

import requests

from db.conexao import get_conn

logger = logging.getLogger(__name__)

CNPJ_PREFEITURA_RIO = os.getenv("PNCP_CNPJ_ORGAO", "42498733000148")
_BASE = os.getenv("PNCP_BASE_URL", "https://pncp.gov.br/api/consulta/v1").strip()
_TIMEOUT = int(os.getenv("PNCP_TIMEOUT", "60"))
_TAM_PAGINA = int(os.getenv("PNCP_TAM_PAGINA_EMPENHOS", "50"))
_MAX_RETRIES = 5


def _get_pncp(params: dict[str, Any], tentativas: int = _MAX_RETRIES) -> dict[str, Any] | None:
    url = f"{_BASE}/contratos"
    ultimo: str | None = None
    for i in range(tentativas):
        try:
            r = requests.get(url, params=params, timeout=_TIMEOUT)
            if r.status_code == 200:
                r.encoding = "utf-8"
                try:
                    return r.json()
                except ValueError:
                    ultimo = "JSONDecodeError"
            elif r.status_code == 204:
                return None
            else:
                ultimo = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            ultimo = str(exc)
        time.sleep(min(2 * (i + 1), 15))
    raise RuntimeError(f"Falhou após {tentativas} tentativas: {ultimo}")


def _fornecedores_monitorados(conn: Any) -> set[str]:
    rows = conn.execute("SELECT ni FROM fornecedores").fetchall()
    return {r[0] for r in rows}


def _salvar_lancamento(conn: Any, d: dict[str, Any]) -> bool:
    o = d.get("orgaoEntidade") or {}
    try:
        conn.execute(
            """INSERT INTO transparencia_rj_lancamentos
               (fornecedor_ni, valor, data_lancamento, descricao, orgao, documento)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                d.get("niFornecedor"),
                d.get("valorGlobal"),
                d.get("dataPublicacaoPncp"),
                d.get("objetoContrato"),
                o.get("cnpj"),
                d.get("numeroControlePNCP"),
            ),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def coletar_empenhos_novos(data_ini: str, data_fim: str) -> dict[str, Any]:
    """Coleta contratos PNCP da Prefeitura do Rio e persiste lançamentos para fornecedores monitorados.

    Returns:
        dict com chaves: total_pncp, novos_monitorados, salvos
    """
    conn = get_conn()
    monitorados = _fornecedores_monitorados(conn)
    total_pncp = 0
    novos_monitorados = 0
    salvos = 0
    pagina = 1
    total_paginas: int | None = None

    try:
        while total_paginas is None or pagina <= total_paginas:
            params: dict[str, Any] = {
                "dataInicial": data_ini,
                "dataFinal": data_fim,
                "cnpjOrgao": CNPJ_PREFEITURA_RIO,
                "pagina": pagina,
                "tamanhoPagina": _TAM_PAGINA,
            }
            try:
                j = _get_pncp(params)
            except RuntimeError as exc:
                logger.warning("[empenhos] pagina %d falhou: %s", pagina, exc)
                break

            if not j or not j.get("data"):
                break
            if total_paginas is None:
                total_paginas = j.get("totalPaginas", 1)
                logger.info(
                    "[empenhos] %s registros PNCP, %s páginas",
                    j.get("totalRegistros"),
                    total_paginas,
                )

            for d in j["data"]:
                total_pncp += 1
                ni = d.get("niFornecedor")
                if ni and ni in monitorados:
                    novos_monitorados += 1
                    if _salvar_lancamento(conn, d):
                        salvos += 1
            conn.commit()
            pagina += 1
            time.sleep(0.3)
    finally:
        conn.close()

    metricas: dict[str, Any] = {
        "total_pncp": total_pncp,
        "novos_monitorados": novos_monitorados,
        "salvos": salvos,
    }
    logger.info("[empenhos] coleta concluída: %s", metricas)
    return metricas


def coletar_empenhos_retroativo(dias: int = 90) -> dict[str, Any]:
    """Coleta retroativa dividida em chunks de 7 dias para não sobrecarregar a API PNCP.

    Args:
        dias: Quantos dias para trás a partir de hoje cobrir.

    Returns:
        dict com chaves: total_pncp, novos_monitorados, salvos, chunks_processados
    """
    from datetime import date, timedelta

    hoje = date.today()
    chunk_inicio = hoje - timedelta(days=dias)

    acumulado: dict[str, Any] = {
        "total_pncp": 0,
        "novos_monitorados": 0,
        "salvos": 0,
        "chunks_processados": 0,
    }

    while chunk_inicio <= hoje:
        chunk_fim = min(chunk_inicio + timedelta(days=6), hoje)

        logger.info(
            "[empenhos_retroativo] chunk %s → %s",
            chunk_inicio,
            chunk_fim,
        )
        resultado = coletar_empenhos_novos(
            chunk_inicio.strftime("%Y%m%d"),
            chunk_fim.strftime("%Y%m%d"),
        )
        acumulado["total_pncp"] += resultado["total_pncp"]
        acumulado["novos_monitorados"] += resultado["novos_monitorados"]
        acumulado["salvos"] += resultado["salvos"]
        acumulado["chunks_processados"] += 1

        chunk_inicio = chunk_fim + timedelta(days=1)
        if chunk_inicio <= hoje:
            time.sleep(1)

    logger.info("[empenhos_retroativo] concluído: %s", acumulado)
    return acumulado


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Coleta de empenhos PNCP — Sentinela RJ")
    parser.add_argument(
        "--retroativo",
        action="store_true",
        help="Executa coleta retroativa em chunks de 7 dias.",
    )
    parser.add_argument(
        "--dias",
        type=int,
        default=90,
        help="Janela em dias para coleta retroativa (padrão: 90).",
    )
    cli_args = parser.parse_args()

    if cli_args.retroativo:
        resultado = coletar_empenhos_retroativo(dias=cli_args.dias)
        print(resultado)
    else:
        parser.print_help()
