"""
Detector de fracionamento por AP — Sentinela RJ.

Método: agrupa contratos por objeto normalizado e detecta serviços idênticos
divididos entre fornecedores distintos nas diferentes Áreas de Planejamento (AP1-AP5).
Indício de fracionamento para contornar limites de licitação.
"""
from __future__ import annotations

import re
import sqlite3

from analisador.engine import AnomaliaResult

_AP_RE = re.compile(
    r'\bAP\s*[1-5](?:[.,\s]+(?:e\s+)?AP\s*[1-5])*\b',
    re.IGNORECASE,
)

_STOP_WORDS = frozenset({
    'fase', 'area', 'areas', 'nas', 'dos', 'de', 'e', 'em', 'a', 'o',
})

_MIN_CONTRATOS_GRUPO = 2
_MIN_FORNECEDORES    = 2
_MIN_VALOR           = 5_000_000


def _fingerprint(objeto: str) -> str:
    texto = objeto.lower()
    texto = _AP_RE.sub('', texto)
    texto = re.sub(r'\d+', '', texto)
    palavras = [p for p in re.split(r'\W+', texto) if p and p not in _STOP_WORDS]
    return ' '.join(palavras)[:60].strip()


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    c = conn.cursor()
    c.execute("""
        SELECT numero_controle_pncp, objeto, valor_global, fornecedor_ni, data_assinatura
        FROM contratos
        WHERE valor_global > 0 AND objeto IS NOT NULL
    """)
    rows = [dict(r) for r in c.fetchall()]

    ap_rows = [r for r in rows if _AP_RE.search(r['objeto'])]

    grupos: dict[str, list[dict]] = {}
    for r in ap_rows:
        fp = _fingerprint(r['objeto'])
        if fp:
            grupos.setdefault(fp, []).append(r)

    resultados: list[AnomaliaResult] = []

    for fingerprint, contratos in grupos.items():
        if len(contratos) < _MIN_CONTRATOS_GRUPO:
            continue

        distinct_fornecedores = len({c['fornecedor_ni'] for c in contratos})
        total_valor = sum(c['valor_global'] for c in contratos)

        if distinct_fornecedores < _MIN_FORNECEDORES or total_valor < _MIN_VALOR:
            continue

        if total_valor >= 50_000_000 and distinct_fornecedores >= 3:
            severidade = 'alta'
        elif total_valor >= 10_000_000:
            severidade = 'media'
        else:
            severidade = 'baixa'

        score = round(min(1.0, total_valor / 1_000_000), 3)

        descricao = (
            f"Possível fracionamento por AP: {distinct_fornecedores} fornecedores, "
            f"valor total R$ {total_valor:,.2f}. "
            f"Objeto similar: '{fingerprint[:80]}'"
        )
        metodologia = "Agrupamento por similaridade de objeto + detecção de APs distintas"
        titulo = f"Fracionamento AP: {distinct_fornecedores} fornecedores — {fingerprint[:50]}"

        for contrato in contratos:
            resultados.append(AnomaliaResult(
                tipo='fracionamento_ap',
                severidade=severidade,
                score=score,
                titulo=titulo,
                descricao=descricao,
                metodologia=metodologia,
                contratos=[contrato['numero_controle_pncp']],
                metricas={
                    'distinct_fornecedores': distinct_fornecedores,
                    'total_valor': round(total_valor, 2),
                    'n_contratos': len(contratos),
                    'fingerprint': fingerprint,
                },
                valor_referencia=total_valor,
            ))

    return resultados
