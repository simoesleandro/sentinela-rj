"""Busca processos judiciais do fornecedor via DataJud CNJ."""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

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
            "nested": {
                "path": "partes",
                "query": {
                    "match": {
                        "partes.documento": cnpj_limpo,
                    }
                },
            }
        },
        "sort": [{"dataAjuizamento": {"order": "desc"}}],
        "_source": [
            "numeroProcesso",
            "dataAjuizamento",
            "classeProcessual",
            "assuntos",
            "orgaoJulgador",
            "situacao",
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
        assuntos = [a.get("nome", "") for a in src.get("assuntos", [])]
        processos.append({
            "numero": src.get("numeroProcesso"),
            "data_ajuizamento": src.get("dataAjuizamento"),
            "classe": src.get("classeProcessual", {}).get("nome"),
            "assuntos": assuntos,
            "orgao": src.get("orgaoJulgador", {}).get("nome"),
            "situacao": src.get("situacao", {}).get("nome"),
        })

    resumo = (
        f"{total} processo(s) encontrado(s) no TJRJ. "
        f"Mostrando {len(processos)}."
    ) if processos else "Nenhum processo encontrado no TJRJ."

    return {
        "processos": processos,
        "total": total,
        "resumo": resumo,
    }
