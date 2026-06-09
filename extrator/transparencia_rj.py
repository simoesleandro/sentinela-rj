"""Cross-reference contratos PNCP × empenhos Transparência RJ (CSV configurável)."""
from __future__ import annotations

import csv
import io
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

_NI_KEYS = ("cnpj", "cpf_cnpj", "credor", "fornecedor", "cnpj cpf")
_VALOR_KEYS = ("valor", "valor empenhado", "valor pago", "valor liquidado")
_DATA_KEYS = ("data", "data empenho", "data pagamento", "data_lancamento")
_DESC_KEYS = ("historico", "histórico", "descricao", "descrição", "natureza")


def _norm(chave: str) -> str:
    return re.sub(r"\s+", " ", chave.strip().lower())


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str:
    for chave, valor in row.items():
        if _norm(chave) in keys:
            return (valor or "").strip()
    return ""


def _limpar_ni(valor: str) -> str | None:
    digits = re.sub(r"\D", "", valor or "")
    return digits if len(digits) in (11, 14) else None


def _parse_valor(texto: str) -> float | None:
    if not texto:
        return None
    limpo = texto.replace(".", "").replace(",", ".")
    limpo = re.sub(r"[^\d.]", "", limpo)
    try:
        return float(limpo)
    except ValueError:
        return None


def _carregar_csv() -> str:
    url = os.getenv("TRANSPARENCIA_RJ_EMPENHOS_URL", "").strip()
    if url:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        return resp.content.decode("utf-8-sig", errors="replace")
    caminho = Path(
        os.getenv(
            "TRANSPARENCIA_RJ_EMPENHOS_PATH",
            "data/raw/transparencia_rj/empenhos.csv",
        )
    )
    if not caminho.exists():
        raise FileNotFoundError(
            f"CSV não encontrado: {caminho}. Defina TRANSPARENCIA_RJ_EMPENHOS_URL ou PATH."
        )
    return caminho.read_text(encoding="utf-8-sig", errors="replace")


def _parse_linhas(texto: str) -> list[dict[str, str]]:
    amostra = texto[:4096]
    delim = ";" if amostra.count(";") >= amostra.count(",") else ","
    reader = csv.DictReader(io.StringIO(texto), delimiter=delim)
    return [{_norm(k): (v or "").strip() for k, v in row.items()} for row in reader]


def ingestir_empenhos(conn: sqlite3.Connection, texto: str) -> dict[str, Any]:
    linhas = _parse_linhas(texto)
    inseridos = ignorados = 0
    for row in linhas:
        ni = _limpar_ni(_pick(row, _NI_KEYS))
        valor = _parse_valor(_pick(row, _VALOR_KEYS))
        if not ni or valor is None:
            ignorados += 1
            continue
        conn.execute(
            """
            INSERT INTO transparencia_rj_lancamentos (
                fornecedor_ni, valor, data_lancamento, descricao, orgao, documento
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(fornecedor_ni, data_lancamento, valor, documento) DO UPDATE SET
                descricao = excluded.descricao,
                orgao = excluded.orgao,
                coletado_em = datetime('now')
            """,
            (
                ni,
                valor,
                _pick(row, _DATA_KEYS) or None,
                _pick(row, _DESC_KEYS) or None,
                row.get("orgao") or row.get("órgão") or None,
                row.get("documento") or row.get("empenho") or None,
            ),
        )
        inseridos += 1
    conn.commit()
    return {"linhas": len(linhas), "inseridos": inseridos, "ignorados": ignorados}


def cruzar_contratos(conn: sqlite3.Connection, tolerancia: float = 0.05) -> dict[str, Any]:
    """Cruza contratos com empenhos por fornecedor + valor aproximado."""
    rows = conn.execute(
        """
        SELECT c.numero_controle_pncp, c.fornecedor_ni, c.valor_global
        FROM contratos c
        WHERE c.fornecedor_ni IS NOT NULL AND c.valor_global > 0
        """
    ).fetchall()
    matches = 0
    for pncp, ni, valor in rows:
        candidatos = conn.execute(
            """
            SELECT id, valor FROM transparencia_rj_lancamentos
            WHERE fornecedor_ni = ?
            """,
            (ni,),
        ).fetchall()
        for lid, lval in candidatos:
            if not lval or not valor:
                continue
            diff = abs(float(lval) - float(valor)) / float(valor)
            if diff > tolerancia:
                continue
            score = max(0.0, 1.0 - diff)
            conn.execute(
                """
                INSERT INTO transparencia_rj_cruzamentos (
                    numero_controle_pncp, lancamento_id, score
                ) VALUES (?, ?, ?)
                ON CONFLICT(numero_controle_pncp, lancamento_id) DO UPDATE SET
                    score = excluded.score,
                    detectado_em = datetime('now')
                """,
                (pncp, lid, score),
            )
            matches += 1
    conn.commit()
    return {"contratos_analisados": len(rows), "cruzamentos": matches}


def executar_transparencia_rj(conn: sqlite3.Connection) -> dict[str, Any]:
    texto = _carregar_csv()
    ingestao = ingestir_empenhos(conn, texto)
    cruzamento = cruzar_contratos(conn)
    return {"ingestao": ingestao, "cruzamento": cruzamento}
