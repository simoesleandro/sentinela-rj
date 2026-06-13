"""Busca processos judiciais do fornecedor via DataJud CNJ."""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

# LIMITAÇÃO CONHECIDA (jun/2026):
# A API pública do DataJud CNJ não expõe o campo 'partes' no índice TJRJ.
# Buscas por CNPJ/nome de parte retornam zero resultados.
# Alternativa futura: Playwright no site público do TJRJ
# (https://www3.tjrj.jus.br/consultaprocessual) — issue aberta para Fase 3.

_DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"
_TJRJ_ENDPOINT = f"{_DATAJUD_BASE}/api_publica_tjrj/_search"
_TIMEOUT = 20
_MAX_PROCESSOS = 10


def _get_api_key() -> str:
    return os.environ.get(
        "DATAJUD_API_KEY",
        "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==",
    )


def buscar_processos_tjrj(cnpj: str) -> dict:
    """Busca processos no TJRJ onde o fornecedor é parte."""
    if not cnpj:
        return {"processos": [], "total": 0, "erro": "CNPJ vazio"}

    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")

    headers = {
        "Authorization": f"APIKey {_get_api_key()}",
        "Content-Type": "application/json",
    }

    query = {
        "size": _MAX_PROCESSOS,
        "query": {
            "bool": {
                "should": [
                    {
                        "match": {
                            "partes.documento": cnpj_limpo
                        }
                    },
                    {
                        "match_phrase": {
                            "partes.nome": cnpj_limpo
                        }
                    }
                ],
                "minimum_should_match": 1
            }
        },
        "sort": [{"dataAjuizamento": {"order": "desc"}}],
        "_source": [
            "numeroProcesso",
            "dataAjuizamento",
            "classe",
            "assuntos",
            "orgaoJulgador",
            "grau",
            "partes",
        ],
    }

    try:
        resp = requests.post(
            _TJRJ_ENDPOINT,
            headers=headers,
            json=query,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        dados = resp.json()
    except requests.RequestException as exc:
        logger.warning("DataJud TJRJ falhou para CNPJ %s: %s", cnpj, exc)
        return {"processos": [], "total": 0, "erro": str(exc)}

    hits = dados.get("hits", {}).get("hits", [])
    total = dados.get("hits", {}).get("total", {}).get("value", 0)

    processos = []
    for hit in hits:
        src = hit.get("_source", {})
        assuntos = [
            a.get("nome", "")
            for a in (src.get("assuntos") or [])
        ]
        data_ajuiz = src.get("dataAjuizamento")
        processos.append({
            "numero": src.get("numeroProcesso"),
            "data_ajuizamento": data_ajuiz[:10] if data_ajuiz else "",
            "classe": (src.get("classe") or {}).get("nome"),
            "assuntos": assuntos[:3],
            "orgao": (src.get("orgaoJulgador") or {}).get("nome"),
            "grau": src.get("grau"),
        })

    if total == 0:
        return {
            "processos": [],
            "total": 0,
            "resumo": (
                "DataJud TJRJ: campo 'partes' não exposto na API pública — "
                "busca por CNPJ indisponível nesta versão. "
                "Fase 3 implementará via Playwright."
            ),
            "limitacao": True,
        }

    resumo = (
        f"{total} processo(s) encontrado(s) no TJRJ. "
        f"Mostrando {len(processos)}."
    ) if processos else "Nenhum processo encontrado no TJRJ."

    return {
        "processos": processos,
        "total": total,
        "resumo": resumo,
    }
