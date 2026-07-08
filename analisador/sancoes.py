"""
Detector de anomalias cadastrais de fornecedores — Sentinela RJ.

Cruza fornecedor_cadastro com contratos para detectar:
  - empresa_inativa: empresa inapta/baixada com contratos ativos
  - capital_social_baixo: capital < 5% do volume contratado
  - empresa_jovem_contrato_grande: menos de 2 anos de abertura no primeiro contrato
"""
from __future__ import annotations

import sqlite3
from datetime import date

from analisador.engine import AnomaliaResult

_MIN_VALOR_EMPRESA_JOVEM = 5_000_000
_ANOS_EMPRESA_JOVEM = 2
_FATOR_CAPITAL = 0.05  # capital < 5% do total contratado


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    """Detecta anomalias cadastrais com base nos dados da BrasilAPI."""
    resultados: list[AnomaliaResult] = []
    resultados.extend(_detectar_empresa_inativa(conn))
    resultados.extend(_detectar_capital_social_baixo(conn))
    resultados.extend(_detectar_empresa_jovem(conn))
    return resultados


# ── Anomalia 1: empresa inativa ───────────────────────────────────────────────

def _detectar_empresa_inativa(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    """Fornecedor com situação cadastral diferente de ATIVA (código 2) e contratos."""
    c = conn.cursor()
    c.execute("""
        SELECT f.ni, f.razao_social,
               fc.situacao_cadastral, fc.descricao_situacao
        FROM fornecedores f
        JOIN fornecedor_cadastro fc ON fc.fornecedor_ni = f.ni
        JOIN contratos ct ON ct.fornecedor_ni = f.ni
        WHERE fc.situacao_cadastral IS NOT NULL
          AND fc.situacao_cadastral != 2
          AND ct.valor_global > 0
        GROUP BY f.ni
    """)
    rows = c.fetchall()

    resultados = []
    for r in rows:
        ni = r["ni"]
        razao = r["razao_social"] or ni
        situacao = r["descricao_situacao"] or f"código {r['situacao_cadastral']}"

        contratos = c.execute(
            "SELECT numero_controle_pncp, valor_global FROM contratos WHERE fornecedor_ni = ? AND valor_global > 0",
            (ni,),
        ).fetchall()
        pncp_ids = [ct["numero_controle_pncp"] for ct in contratos]
        valor_total = sum(ct["valor_global"] for ct in contratos)

        resultados.append(AnomaliaResult(
            tipo="empresa_inativa",
            severidade="alta",
            score=1.0,
            titulo=f"Empresa inativa/inapta contratada: {razao[:60]}",
            descricao=(
                f"{razao} possui situação cadastral '{situacao}' (não ATIVA) "
                f"e {len(contratos)} contrato(s) totalizando R$ {valor_total:,.2f}."
            ),
            metodologia=(
                "Situação cadastral consultada via BrasilAPI. "
                "Código 2 = ATIVA. Qualquer outro código gera alerta 'alta'."
            ),
            contratos=pncp_ids,
            metricas={
                "situacao_cadastral": r["situacao_cadastral"],
                "descricao_situacao": situacao,
                "total_contratos": len(contratos),
                "valor_total": round(valor_total, 2),
            },
            valor_referencia=valor_total,
        ))
    return resultados


# ── Anomalia 2: capital social baixo ─────────────────────────────────────────

def _detectar_capital_social_baixo(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    """Capital social menor que 5% do volume total contratado."""
    c = conn.cursor()
    c.execute("""
        SELECT f.ni, f.razao_social, fc.capital_social
        FROM fornecedores f
        JOIN fornecedor_cadastro fc ON fc.fornecedor_ni = f.ni
        WHERE fc.capital_social IS NOT NULL AND fc.capital_social >= 0
    """)
    rows = c.fetchall()

    resultados = []
    for r in rows:
        ni = r["ni"]
        capital = r["capital_social"]

        contratos = c.execute(
            "SELECT numero_controle_pncp, valor_global FROM contratos WHERE fornecedor_ni = ? AND valor_global > 0",
            (ni,),
        ).fetchall()
        if not contratos:
            continue

        valor_total = sum(ct["valor_global"] for ct in contratos)
        limiar = valor_total * _FATOR_CAPITAL
        if capital >= limiar:
            continue

        razao = r["razao_social"] or ni
        pncp_ids = [ct["numero_controle_pncp"] for ct in contratos]
        score = round(min(1.0, 1.0 - capital / limiar if limiar > 0 else 1.0), 3)

        resultados.append(AnomaliaResult(
            tipo="capital_social_baixo",
            severidade="media",
            score=score,
            titulo=f"Capital social baixo em relação ao volume contratado: {razao[:50]}",
            descricao=(
                f"{razao} possui capital social de R$ {capital:,.2f}, "
                f"equivalente a {capital / valor_total * 100:.1f}% do volume contratado "
                f"(R$ {valor_total:,.2f}). Limiar mínimo sugerido: R$ {limiar:,.2f} (5%)."
            ),
            metodologia=(
                f"Capital social < {_FATOR_CAPITAL*100:.0f}% do total contratado. "
                "Dados cadastrais via BrasilAPI."
            ),
            contratos=pncp_ids,
            metricas={
                "capital_social": capital,
                "valor_total_contratos": round(valor_total, 2),
                "percentual_capital": round(capital / valor_total * 100, 2) if valor_total else 0,
            },
            valor_referencia=valor_total,
        ))
    return resultados


# ── Anomalia 3: empresa jovem com contrato grande ─────────────────────────────

def _detectar_empresa_jovem(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    """Empresa com menos de 2 anos de abertura no momento do primeiro contrato e volume > R$ 5M."""
    c = conn.cursor()
    c.execute("""
        SELECT f.ni, f.razao_social, fc.data_inicio_atividade
        FROM fornecedores f
        JOIN fornecedor_cadastro fc ON fc.fornecedor_ni = f.ni
        WHERE fc.data_inicio_atividade IS NOT NULL
    """)
    rows = c.fetchall()

    resultados = []
    limite_dias = _ANOS_EMPRESA_JOVEM * 365

    for r in rows:
        ni = r["ni"]
        try:
            data_abertura = date.fromisoformat(r["data_inicio_atividade"][:10])
        except (ValueError, TypeError):
            continue

        contratos = c.execute(
            """
            SELECT numero_controle_pncp, valor_global, data_assinatura
            FROM contratos
            WHERE fornecedor_ni = ? AND valor_global > 0 AND data_assinatura IS NOT NULL
            ORDER BY data_assinatura
            """,
            (ni,),
        ).fetchall()
        if not contratos:
            continue

        valor_total = sum(ct["valor_global"] for ct in contratos)
        if valor_total < _MIN_VALOR_EMPRESA_JOVEM:
            continue

        try:
            primeiro_contrato = date.fromisoformat(contratos[0]["data_assinatura"][:10])
        except (ValueError, TypeError):
            continue

        dias_antes = (primeiro_contrato - data_abertura).days
        if dias_antes >= limite_dias:
            continue

        razao = r["razao_social"] or ni
        pncp_ids = [ct["numero_controle_pncp"] for ct in contratos]
        anos_str = f"{dias_antes / 365:.1f}"

        resultados.append(AnomaliaResult(
            tipo="empresa_jovem_contrato_grande",
            severidade="media",
            score=round(min(1.0, _MIN_VALOR_EMPRESA_JOVEM / valor_total), 3),
            titulo=f"Empresa jovem com contrato de alto valor: {razao[:55]}",
            descricao=(
                f"{razao} foi aberta em {data_abertura} e recebeu seu primeiro contrato "
                f"em {primeiro_contrato} ({anos_str} anos depois), "
                f"totalizando R$ {valor_total:,.2f} em {len(contratos)} contrato(s)."
            ),
            metodologia=(
                f"Empresa com menos de {_ANOS_EMPRESA_JOVEM} anos de abertura no primeiro contrato "
                f"e volume total > R$ {_MIN_VALOR_EMPRESA_JOVEM:,.0f}. "
                "Datas de abertura via BrasilAPI."
            ),
            contratos=pncp_ids,
            metricas={
                "data_abertura": str(data_abertura),
                "primeiro_contrato": str(primeiro_contrato),
                "dias_antes_primeiro_contrato": dias_antes,
                "valor_total": round(valor_total, 2),
                "total_contratos": len(contratos),
            },
            valor_referencia=valor_total,
        ))
    return resultados
