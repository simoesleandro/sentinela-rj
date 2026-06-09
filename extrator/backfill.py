"""Backfill histórico PNCP — fatias mensais reutilizando extrator.pncp."""
from __future__ import annotations

from datetime import date

from extrator.config_municipio import rotulo_filtro
from extrator.pncp import _janelas_mensais, coletar


def executar_backfill(data_inicial: str, data_final: str) -> dict:
    """Coleta intervalo AAAAMMDD em janelas mensais (idempotente via INSERT OR REPLACE)."""
    di = date(int(data_inicial[:4]), int(data_inicial[4:6]), int(data_inicial[6:8]))
    df = date(int(data_final[:4]), int(data_final[4:6]), int(data_final[6:8]))
    if di > df:
        raise ValueError("data_inicial deve ser anterior ou igual a data_final.")

    janelas = _janelas_mensais(data_inicial, data_final)
    totais = {
        "data_inicial": data_inicial,
        "data_final": data_final,
        "filtro": rotulo_filtro(),
        "janelas": len(janelas),
        "brutos_varridos": 0,
        "salvos_municipio": 0,
        "paginas_falhas": [],
    }

    for idx, (ini, fim) in enumerate(janelas, start=1):
        print(f"\n[backfill] janela {idx}/{len(janelas)}: {ini} → {fim}")
        resumo = coletar(ini, fim)
        totais["brutos_varridos"] += int(resumo.get("brutos_varridos", 0))
        totais["salvos_municipio"] += int(resumo.get("salvos_rio", 0))
        totais["paginas_falhas"].extend(resumo.get("paginas_falhas") or [])

    return totais
