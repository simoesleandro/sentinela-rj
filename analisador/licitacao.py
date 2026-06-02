"""
Detector de contratos sem licitação competitiva — Sentinela RJ.

Detecta três modalidades pelo campo informacao_complementar e objeto:
  - inexigibilidade   (art. 74, Lei 14.133/2021 — inviabilidade de competição)
  - dispensa          (art. 75 — abaixo do limite ou situação prevista em lei)
  - emergencia        (art. 75, inciso VIII — urgência/calamidade)

Severidade calibrada pelo valor:
  inexigibilidade: alta ≥ R$10M | media ≥ R$1M | baixa < R$1M
  emergencia:      alta ≥ R$5M  | media ≥ R$500K | baixa < R$500K
  dispensa:        alta ≥ R$1M  | media ≥ R$200K | baixa < R$200K
"""
from __future__ import annotations

import math
import re
import sqlite3

from analisador.engine import AnomaliaResult

# ── Padrões de detecção ────────────────────────────────────────────────────

_PAD_INEXIG = [
    r"inexigibilidade",
    r"inviabilidade\s+de\s+competi",
    r"art\.?\s*74\b",
]

_PAD_EMERG = [
    r"emerg[eê]ncia",
    r"calamidade",
    r"art\.?\s*75.*\bviii\b",           # art. 75, VIII
    r"\bviii\b.*art\.?\s*75",
]

_PAD_DISPENSA = [
    r"dispens[ao]",
    r"art\.?\s*75\b",
]

_THRESHOLDS: dict[str, tuple[float, float]] = {
    # tipo → (limiar_alta, limiar_media)
    "inexigibilidade": (10_000_000, 1_000_000),
    "emergencia":      (5_000_000,   500_000),
    "dispensa":        (1_000_000,   200_000),
}

_LABELS = {
    "inexigibilidade": "Inexigibilidade de licitação",
    "dispensa":        "Dispensa de licitação",
    "emergencia":      "Contrato emergencial",
}


def _match(text: str, patterns: list[str]) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(re.search(p, t) for p in patterns)


def _classificar(info: str, objeto: str) -> str | None:
    """Retorna o tipo de não-licitação ou None se não detectado."""
    combined = (info or "") + " " + (objeto or "")
    if _match(combined, _PAD_INEXIG):
        return "inexigibilidade"
    # emergência é subconjunto de dispensa — testa antes
    if _match(combined, _PAD_EMERG):
        return "emergencia"
    if _match(combined, _PAD_DISPENSA):
        return "dispensa"
    return None


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    c = conn.cursor()
    c.execute("""
        SELECT c.numero_controle_pncp, c.valor_global, c.objeto,
               c.informacao_complementar, c.categoria_processo_nome,
               c.data_assinatura, c.unidade_nome, c.processo,
               f.razao_social AS fornecedor
        FROM contratos c
        LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        WHERE c.valor_global > 0
    """)
    rows = [dict(r) for r in c.fetchall()]

    resultados: list[AnomaliaResult] = []

    for row in rows:
        tipo = _classificar(row["informacao_complementar"], row["objeto"])
        if tipo is None:
            continue

        v = row["valor_global"]
        lim_alta, lim_media = _thresholds_para(tipo)

        if v >= lim_alta:
            severidade, base_score = "alta", 0.70
        elif v >= lim_media:
            severidade, base_score = "media", 0.45
        else:
            severidade, base_score = "baixa", 0.20

        # Pequeno boost logarítmico pelo valor absoluto (máx +0,25)
        value_boost = min(0.25, math.log10(max(v, 1)) / 40)
        score = round(min(1.0, base_score + value_boost), 3)

        label = _LABELS[tipo]
        nome_forn = (row["fornecedor"] or "fornecedor não informado")[:50]

        resultados.append(AnomaliaResult(
            tipo=f"sem_licitacao_{tipo}",
            severidade=severidade,
            score=score,
            titulo=f"{label} — R$ {v:,.0f} — {nome_forn}",
            descricao=(
                f"Contrato de R$ {v:,.2f} firmado sem licitação competitiva "
                f"({label}). "
                f"Órgão: {row['unidade_nome'] or 'não informado'}. "
                f"Objeto: {(row['objeto'] or 'não informado')[:120]}."
            ),
            metodologia=(
                f"Detecção por regex em informacao_complementar + objeto "
                f"(padrões: {tipo}). "
                f"Severidade: alta ≥ R${lim_alta:,.0f}, "
                f"média ≥ R${lim_media:,.0f}. "
                f"Score = base + log10(valor)/40."
            ),
            contratos=[row["numero_controle_pncp"]],
            metricas={
                "tipo_contratacao": tipo,
                "valor_global": v,
                "unidade": row["unidade_nome"],
                "processo": row["processo"],
                "categoria": row["categoria_processo_nome"],
            },
            valor_referencia=v,
        ))

    return resultados


def _thresholds_para(tipo: str) -> tuple[float, float]:
    return _THRESHOLDS.get(tipo, (1_000_000, 100_000))
