"""Benchmark comparativo entre municípios — Sentinela RJ (roadmap 4.2).

Compara os municípios monitorados em indicadores de risco de contratação e
posiciona cada um contra a **mediana regional**. Responde a pergunta que nenhum
painel público entrega em nível municipal: "meu município contrata pior que os
vizinhos?".

Indicadores (derivados só de contratos já coletados, sem fonte nova):
- **% sem licitação** — fatia de contratos por dispensa/inexigibilidade/
  emergência (usa o mesmo classificador do detector sem_licitacao, para ser
  consistente). É o indicador clássico de transparência.
- **Concentração (top-1)** — fatia do maior fornecedor no valor total; alta
  concentração indica dependência/possível direcionamento.
- **HHI** — índice Herfindahl-Hirschman da distribuição de valor entre
  fornecedores (0 = pulverizado, 1 = monopólio).
- **Valor médio por contrato**.

Só entram municípios com amostra mínima (padrão 30 contratos) — abaixo disso o
percentual é instável.
"""
from __future__ import annotations

import sqlite3
import statistics
from typing import Any

from analisador.licitacao import _classificar

_MIN_CONTRATOS = 30


def calcular_benchmark(
    conn: sqlite3.Connection, min_contratos: int = _MIN_CONTRATOS
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT municipio_nome, valor_global, objeto,
               informacao_complementar, fornecedor_ni
        FROM contratos
        WHERE valor_global > 0 AND municipio_nome IS NOT NULL
        """
    ).fetchall()

    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        m = r["municipio_nome"]
        d = agg.setdefault(m, {"n": 0, "val": 0.0, "semlic": 0, "forn": {}})
        d["n"] += 1
        d["val"] += r["valor_global"]
        if _classificar(r["informacao_complementar"], r["objeto"]):
            d["semlic"] += 1
        ni = r["fornecedor_ni"] or "?"
        d["forn"][ni] = d["forn"].get(ni, 0.0) + r["valor_global"]

    municipios: list[dict[str, Any]] = []
    for m, d in agg.items():
        if d["n"] < min_contratos:
            continue
        val = d["val"] or 1.0
        top1 = max(d["forn"].values()) / val
        hhi = sum((v / val) ** 2 for v in d["forn"].values())
        municipios.append({
            "municipio": m,
            "n_contratos": d["n"],
            "valor_total": round(d["val"], 2),
            "valor_medio": round(d["val"] / d["n"], 2),
            "pct_sem_licitacao": round(d["semlic"] / d["n"], 4),
            "concentracao_top1": round(top1, 4),
            "hhi": round(hhi, 4),
            "n_fornecedores": len(d["forn"]),
        })

    if not municipios:
        return {"municipios": [], "medianas": {}, "n_municipios": 0,
                "min_contratos": min_contratos}

    def _med(chave: str) -> float:
        return statistics.median(x[chave] for x in municipios)

    medianas = {
        "pct_sem_licitacao": round(_med("pct_sem_licitacao"), 4),
        "concentracao_top1": round(_med("concentracao_top1"), 4),
        "valor_medio": round(_med("valor_medio"), 2),
    }

    ref = medianas["pct_sem_licitacao"] or None
    for x in municipios:
        x["sem_licitacao_vs_mediana"] = (
            round(x["pct_sem_licitacao"] / ref, 2) if ref else None
        )
        x["acima_mediana"] = bool(ref and x["pct_sem_licitacao"] > ref)

    municipios.sort(key=lambda x: -x["pct_sem_licitacao"])
    return {
        "municipios": municipios,
        "medianas": medianas,
        "n_municipios": len(municipios),
        "min_contratos": min_contratos,
    }
