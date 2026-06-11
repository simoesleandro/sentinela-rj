"""Comparador multi-fornecedor — perfil lado a lado para investigação."""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from analise.grafo import _parse_socios, _slug_socio

_MIN_FORNECEDORES = 2
_MAX_FORNECEDORES = 4
_LIMITE_CONTRATOS = 8
_LIMITE_ALERTAS = 8


class ComparadorError(ValueError):
    """Erro de validação no comparador."""


def _normalizar_nis(nis: list[str]) -> list[str]:
    limpos: list[str] = []
    for ni in nis:
        digits = re.sub(r"\D", "", ni or "")
        if digits and digits not in limpos:
            limpos.append(digits)
    if len(limpos) < _MIN_FORNECEDORES:
        raise ComparadorError(
            f"Informe ao menos {_MIN_FORNECEDORES} fornecedores distintos."
        )
    if len(limpos) > _MAX_FORNECEDORES:
        raise ComparadorError(
            f"Máximo de {_MAX_FORNECEDORES} fornecedores por comparação."
        )
    return limpos


def _nomes_socios(socios_raw: str | None) -> list[str]:
    return [
        (s.get("nome_socio") or "").strip()
        for s in _parse_socios(socios_raw)
        if len((s.get("nome_socio") or "").strip()) >= 3
    ]


def _carregar_identidade(conn: sqlite3.Connection, ni: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT ni, razao_social, tipo_pessoa, tem_sancao,
               capital_social, data_inicio_atividade
        FROM fornecedores WHERE ni = ?
        """,
        (ni,),
    ).fetchone()
    if row is None:
        raise ComparadorError(f"Fornecedor não encontrado: {ni}")
    return dict(row)


def _carregar_resumo(conn: sqlite3.Connection, ni: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS total_contratos,
               COALESCE(SUM(c.valor_global), 0) AS valor_total,
               COUNT(DISTINCT a.id) AS total_alertas,
               COUNT(DISTINCT CASE WHEN a.severidade = 'alta' THEN a.id END) AS alertas_alta
        FROM contratos c
        LEFT JOIN alertas a ON a.numero_controle_pncp = c.numero_controle_pncp
        WHERE c.fornecedor_ni = ? AND c.valor_global > 0
        """,
        (ni,),
    ).fetchone()
    return dict(row) if row else {}


def _carregar_contratos(conn: sqlite3.Connection, ni: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.numero_controle_pncp, c.objeto, c.valor_global,
               c.data_assinatura, o.razao_social AS orgao
        FROM contratos c
        LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
        WHERE c.fornecedor_ni = ? AND c.valor_global > 0
        ORDER BY c.valor_global DESC
        LIMIT ?
        """,
        (ni, _LIMITE_CONTRATOS),
    ).fetchall()
    return [dict(r) for r in rows]


def _carregar_alertas(conn: sqlite3.Connection, ni: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT a.id, a.tipo, a.severidade, a.score, a.descricao,
               a.valor_referencia, a.status, c.objeto
        FROM alertas a
        JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
        WHERE c.fornecedor_ni = ?
        ORDER BY CASE a.severidade WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END,
                 a.score DESC
        LIMIT ?
        """,
        (ni, _LIMITE_ALERTAS),
    ).fetchall()
    return [dict(r) for r in rows]


def _carregar_sancoes(conn: sqlite3.Connection, ni: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT fonte, tipo_sancao, orgao_sancionador, data_inicio, data_fim, descricao
        FROM fornecedor_sancoes
        WHERE fornecedor_ni = ?
        ORDER BY data_inicio DESC
        """,
        (ni,),
    ).fetchall()
    return [dict(r) for r in rows]


def _perfil_fornecedor(conn: sqlite3.Connection, ni: str) -> dict[str, Any]:
    identidade = _carregar_identidade(conn, ni)
    cadastro = conn.execute(
        "SELECT socios, descricao_situacao, porte FROM fornecedor_cadastro WHERE fornecedor_ni = ?",
        (ni,),
    ).fetchone()
    socios = _nomes_socios(cadastro["socios"] if cadastro else None)
    return {
        "identidade": identidade,
        "cadastro": dict(cadastro) if cadastro else None,
        "resumo": _carregar_resumo(conn, ni),
        "contratos": _carregar_contratos(conn, ni),
        "alertas": _carregar_alertas(conn, ni),
        "socios": socios,
        "sancoes": _carregar_sancoes(conn, ni),
    }


def _vinculos_socios(
    perfis: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    por_nome: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    for perfil in perfis:
        ni = perfil["identidade"]["ni"]
        nome_forn = perfil["identidade"].get("razao_social") or ni
        labels[ni] = nome_forn
        for socio in perfil["socios"]:
            slug = _slug_socio(socio)
            por_nome.setdefault(slug, set()).add(ni)
            labels.setdefault(slug, socio)
    return [
        {
            "nome": labels[slug],
            "fornecedores": [
                {"ni": ni, "razao_social": labels.get(ni, ni)}
                for ni in sorted(nis)
            ],
        }
        for slug, nis in sorted(por_nome.items())
        if len(nis) >= 2
    ]


def montar_comparacao(
    conn: sqlite3.Connection,
    fornecedor_nis: list[str],
) -> dict[str, Any]:
    """Monta visão comparativa de 2–4 fornecedores."""
    nis = _normalizar_nis(fornecedor_nis)
    perfis = [_perfil_fornecedor(conn, ni) for ni in nis]
    return {
        "fornecedores": perfis,
        "vinculos": {
            "socios_compartilhados": _vinculos_socios(perfis),
        },
    }
