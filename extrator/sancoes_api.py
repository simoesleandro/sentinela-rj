"""Consulta de sanções federais por CNPJ na API do Portal da Transparência.

Complementa extrator/sancoes_ingestao.py (que carrega o CSV nacional inteiro):
aqui consultamos CEIS e CNEP por CNPJ, um fornecedor por vez, via o filtro
``codigoSancionado``. Vantagem sobre o CSV: sempre atual, sem hospedar arquivos
gigantes, e pega inidôneos/punidos de QUALQUER esfera (federal, estadual,
municipal) que contratem no nosso município.

A API cobra chave (``TRANSPARENCIA_API_KEY``, gratuita em
portaldatransparencia.gov.br/api-de-dados) e limita a ~90 req/min — por isso a
sincronização é incremental (coluna fornecedores.sancoes_verificado_em) e
resumível: cada execução processa os N fornecedores checados há mais tempo.

Formato da resposta confirmado empiricamente (jul/2026): lista de registros com
``tipoSancao.descricaoResumida``, ``orgaoSancionador.{nome,siglaUf,esfera}``,
``dataInicioSancao``/``dataFimSancao`` em DD/MM/YYYY, ``pessoa.cnpjFormatado``.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
# fonte -> path. CEPIM (empresas impedidas) fica de fora por ora; mesmo padrão.
ENDPOINTS = {"CEIS": "/ceis", "CNEP": "/cnep"}
_PAUSA_PADRAO_S = 0.75          # ~80 req/min, sob o limite diurno de ~90
_TAM_PAGINA = 15                # a API ignora tamanhoPagina; página fixa de 15


class SancoesApiError(RuntimeError):
    pass


def chave_configurada() -> str:
    return os.getenv("TRANSPARENCIA_API_KEY", "").strip()


def _normalizar_data(br: str | None) -> str | None:
    """'29/09/2025' -> '2025-09-29' (ISO, como o resto do banco)."""
    if not br:
        return None
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", br.strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _get(path: str, params: dict, chave: str, tentativas: int = 6) -> list[dict]:
    headers = {"chave-api-dados": chave, "Accept": "application/json"}
    ultimo: str | None = None
    for i in range(tentativas):
        try:
            r = requests.get(f"{BASE}{path}", params=params, headers=headers, timeout=60)
            if r.status_code == 200:
                return r.json() or []
            if r.status_code == 429:  # rate limit — espera crescente
                ultimo = "HTTP 429"
                time.sleep(min(5 * (i + 1), 30))
                continue
            if r.status_code in (401, 403):
                raise SancoesApiError(f"Chave rejeitada (HTTP {r.status_code}). Verifique TRANSPARENCIA_API_KEY.")
            ultimo = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            ultimo = str(exc)
        time.sleep(min(2 * (i + 1), 15))
    raise SancoesApiError(f"Falhou após {tentativas} tentativas: {ultimo}")


def consultar_cnpj(cnpj: str, chave: str) -> list[dict[str, Any]]:
    """Sanções (CEIS + CNEP) de um CNPJ, já normalizadas para fornecedor_sancoes."""
    resultados: list[dict[str, Any]] = []
    for fonte, path in ENDPOINTS.items():
        pagina = 1
        while True:
            registros = _get(path, {"codigoSancionado": cnpj, "pagina": pagina}, chave)
            for reg in registros:
                resultados.append(_parse_registro(reg, fonte, cnpj))
            if len(registros) < _TAM_PAGINA:
                break
            pagina += 1
    return resultados


def _parse_registro(reg: dict, fonte: str, fornecedor_ni: str) -> dict[str, Any]:
    orgao = reg.get("orgaoSancionador") or {}
    tipo = reg.get("tipoSancao") or {}
    orgao_txt = orgao.get("nome") or ""
    if orgao.get("esfera"):
        orgao_txt = f"{orgao_txt} ({orgao['esfera']})".strip()
    fundamentos = reg.get("fundamentacao") or []
    descricao = "; ".join(
        f.get("descricao", "") for f in fundamentos if f.get("descricao")
    )[:1000] or (reg.get("textoPublicacao") or None)
    return {
        "fornecedor_ni": fornecedor_ni,
        "fonte": fonte,
        "tipo_sancao": tipo.get("descricaoResumida"),
        "orgao_sancionador": orgao_txt or None,
        "data_inicio": _normalizar_data(reg.get("dataInicioSancao")),
        "data_fim": _normalizar_data(reg.get("dataFimSancao")),
        "descricao": descricao,
    }


def _upsert(conn: sqlite3.Connection, s: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO fornecedor_sancoes (
            fornecedor_ni, fonte, tipo_sancao, orgao_sancionador,
            data_inicio, data_fim, descricao
        ) VALUES (:fornecedor_ni, :fonte, :tipo_sancao, :orgao_sancionador,
                  :data_inicio, :data_fim, :descricao)
        ON CONFLICT(fornecedor_ni, fonte, data_inicio) DO UPDATE SET
            tipo_sancao = excluded.tipo_sancao,
            orgao_sancionador = excluded.orgao_sancionador,
            data_fim = excluded.data_fim,
            descricao = excluded.descricao,
            coletado_em = datetime('now')
        """,
        s,
    )


def sincronizar_sancoes_api(
    conn: sqlite3.Connection,
    *,
    limite: int = 300,
    pausa_s: float = _PAUSA_PADRAO_S,
    chave: str | None = None,
) -> dict[str, Any]:
    """Consulta os `limite` fornecedores verificados há mais tempo (ou nunca).

    Incremental e resumível: cada fornecedor recebe sancoes_verificado_em ao
    ser checado, então a próxima execução pega os próximos. Retorna resumo.
    """
    chave = chave or chave_configurada()
    if not chave:
        raise SancoesApiError(
            "TRANSPARENCIA_API_KEY não configurada. "
            "Cadastre em portaldatransparencia.gov.br/api-de-dados."
        )

    from extrator.sancoes_ingestao import sincronizar_tem_sancao

    pendentes = conn.execute(
        """
        SELECT DISTINCT f.ni
        FROM fornecedores f
        JOIN contratos c ON c.fornecedor_ni = f.ni AND c.valor_global > 0
        WHERE length(f.ni) = 14          -- só CNPJ (CPF sancionado é outra base)
        ORDER BY f.sancoes_verificado_em IS NOT NULL, f.sancoes_verificado_em
        LIMIT ?
        """,
        (limite,),
    ).fetchall()

    checados = 0
    sancoes_novas = 0
    fornecedores_sancionados = 0
    for (ni,) in pendentes:
        sancoes = consultar_cnpj(ni, chave)
        for s in sancoes:
            _upsert(conn, s)
        if sancoes:
            fornecedores_sancionados += 1
            sancoes_novas += len(sancoes)
        conn.execute(
            "UPDATE fornecedores SET sancoes_verificado_em = datetime('now') WHERE ni = ?",
            (ni,),
        )
        checados += 1
        conn.commit()
        time.sleep(pausa_s)

    sincronizar_tem_sancao(conn)

    restantes = conn.execute(
        """
        SELECT COUNT(DISTINCT f.ni)
        FROM fornecedores f
        JOIN contratos c ON c.fornecedor_ni = f.ni AND c.valor_global > 0
        WHERE length(f.ni) = 14 AND f.sancoes_verificado_em IS NULL
        """
    ).fetchone()[0]

    return {
        "checados": checados,
        "fornecedores_sancionados": fornecedores_sancionados,
        "sancoes_registradas": sancoes_novas,
        "pendentes_restantes": restantes,
    }
