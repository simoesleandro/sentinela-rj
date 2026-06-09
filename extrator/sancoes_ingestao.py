"""Ingestão CEIS/CNEP a partir de CSV (Portal da Transparência / dados.gov.br)."""
from __future__ import annotations

import csv
import io
import os
import re
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

_FONTE_CEIS = "CEIS"
_FONTE_CNEP = "CNEP"
_NI_KEYS = (
    "cnpj ou cpf do sancionado",
    "cpf cnpj do sancionado",
    "cpf_cnpj",
    "cnpj_cpf",
    "cnpj",
    "cpf_cnpj",
)


def _limpar_ni(valor: str | None) -> str | None:
    if not valor:
        return None
    digits = re.sub(r"\D", "", valor)
    return digits if len(digits) in (11, 14) else None


def _normalizar_header(nome: str) -> str:
    return re.sub(r"\s+", " ", nome.strip().lower())


def _extrair_ni(row: dict[str, str]) -> str | None:
    for chave, valor in row.items():
        if _normalizar_header(chave) in _NI_KEYS or "sancionado" in _normalizar_header(chave):
            ni = _limpar_ni(valor)
            if ni:
                return ni
    for valor in row.values():
        ni = _limpar_ni(str(valor))
        if ni and len(ni) >= 11:
            return ni
    return None


def _ler_bytes_conteudo(data: bytes) -> str:
    for enc in ("utf-8-sig", "latin-1", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _abrir_csv_texto(origem: Path | str) -> str:
    caminho = Path(origem)
    if caminho.suffix.lower() == ".zip":
        with zipfile.ZipFile(caminho) as zf:
            nome = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            return _ler_bytes_conteudo(zf.read(nome))
    return _ler_bytes_conteudo(caminho.read_bytes())


def _carregar_origem(env_nome: str, padrao_nome: str) -> str:
    url = os.getenv(env_nome, "").strip()
    if url:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        return _ler_bytes_conteudo(resp.content)
    caminho = Path(os.getenv("SANCOES_DIR", "data/raw/sancoes")) / padrao_nome
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}. Defina {env_nome} ou coloque o CSV lá."
        )
    return _abrir_csv_texto(caminho)


def _parse_csv(texto: str) -> list[dict[str, str]]:
    amostra = texto[:4096]
    delim = ";" if amostra.count(";") >= amostra.count(",") else ","
    reader = csv.DictReader(io.StringIO(texto), delimiter=delim)
    return [{_normalizar_header(k): (v or "").strip() for k, v in row.items()} for row in reader]


def _upsert_sancao(
    conn: sqlite3.Connection,
    *,
    fornecedor_ni: str,
    fonte: str,
    row: dict[str, str],
) -> None:
    conn.execute(
        """
        INSERT INTO fornecedor_sancoes (
            fornecedor_ni, fonte, tipo_sancao, orgao_sancionador,
            data_inicio, data_fim, descricao
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fornecedor_ni, fonte, data_inicio) DO UPDATE SET
            tipo_sancao = excluded.tipo_sancao,
            orgao_sancionador = excluded.orgao_sancionador,
            data_fim = excluded.data_fim,
            descricao = excluded.descricao,
            coletado_em = datetime('now')
        """,
        (
            fornecedor_ni,
            fonte,
            row.get("tipo de sancao") or row.get("tipo sancao"),
            row.get("orgao sancionador") or row.get("órgão sancionador"),
            row.get("data inicio sancao") or row.get("data início sanção") or row.get("data inicio"),
            row.get("data fim sancao") or row.get("data fim sanção") or row.get("data fim"),
            row.get("fundamentacao") or row.get("fundamentação") or row.get("descricao"),
        ),
    )


def ingestir_csv(
    conn: sqlite3.Connection,
    texto: str,
    fonte: str,
) -> dict[str, Any]:
    linhas = _parse_csv(texto)
    inseridos = ignorados = 0
    for row in linhas:
        ni = _extrair_ni(row)
        if not ni:
            ignorados += 1
            continue
        _upsert_sancao(conn, fornecedor_ni=ni, fonte=fonte, row=row)
        inseridos += 1
    conn.commit()
    sincronizar_tem_sancao(conn)
    return {"fonte": fonte, "linhas": len(linhas), "inseridos": inseridos, "ignorados": ignorados}


def sincronizar_tem_sancao(conn: sqlite3.Connection) -> int:
    """Marca fornecedores com registro ativo em fornecedor_sancoes."""
    cur = conn.execute(
        """
        UPDATE fornecedores
        SET tem_sancao = CASE
            WHEN ni IN (SELECT DISTINCT fornecedor_ni FROM fornecedor_sancoes) THEN 1
            ELSE 0
        END
        """
    )
    conn.commit()
    return int(cur.rowcount)


def ingestir_ceis_cnp(conn: sqlite3.Connection) -> dict[str, Any]:
    resumo: dict[str, Any] = {}
    for env, fonte, arquivo in (
        ("SANCOES_CEIS_URL", _FONTE_CEIS, "ceis.csv"),
        ("SANCOES_CNEP_URL", _FONTE_CNEP, "cnep.csv"),
    ):
        try:
            texto = _carregar_origem(env, arquivo)
            resumo[fonte.lower()] = ingestir_csv(conn, texto, fonte)
        except FileNotFoundError as exc:
            resumo[fonte.lower()] = {"erro": str(exc), "inseridos": 0}
    return resumo
