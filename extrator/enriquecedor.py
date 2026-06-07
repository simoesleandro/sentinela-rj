"""
Enriquecimento cadastral de fornecedores — Sentinela RJ.

Consulta BrasilAPI para cada fornecedor e persiste dados cadastrais
em fornecedor_cadastro. CEIS/CNEP foram abandonados: a chave gratuita
do Portal da Transparência não filtra por CNPJ.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time

import requests


class Enriquecedor:
    """Consulta BrasilAPI e persiste dados cadastrais de fornecedores."""

    def __init__(self) -> None:
        self.verbose = False  # ativado externamente para diagnóstico

    def consultar_cnpj_brasilapi(self, cnpj: str) -> dict | None:
        """
        Consulta dados cadastrais na BrasilAPI.

        Retorna dict com situação, CNAE, capital social, sócios etc.
        Retorna None em caso de 404 ou erro de rede.
        """
        cnpj_limpo = _limpar_cnpj(cnpj)
        try:
            resp = requests.get(
                f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}",
                timeout=15,
            )
            if self.verbose:
                preview = resp.text[:120].replace("\n", " ")
                print(f"      [BrasilAPI] HTTP {resp.status_code} — {preview}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            dados = resp.json()
            if self.verbose:
                sit = dados.get("descricao_situacao_cadastral", "?")
                print(f"      [BrasilAPI] situacao={sit}  capital={dados.get('capital_social')}")
            return dados
        except Exception as exc:
            if self.verbose:
                print(f"      [BrasilAPI] ERRO: {exc}")
            return None

    def salvar_cadastro(
        self, conn: sqlite3.Connection, fornecedor_ni: str, dados: dict
    ) -> None:
        """Salva dados cadastrais da BrasilAPI em fornecedor_cadastro via INSERT OR REPLACE."""
        conn.execute(
            """
            INSERT OR REPLACE INTO fornecedor_cadastro
                (fornecedor_ni, situacao_cadastral, descricao_situacao,
                 data_inicio_atividade, cnae_fiscal, cnae_fiscal_descricao,
                 capital_social, porte, natureza_juridica,
                 socios, cnaes_secundarios, municipio, uf, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                fornecedor_ni,
                dados.get("situacao_cadastral"),
                dados.get("descricao_situacao_cadastral"),
                dados.get("data_inicio_atividade"),
                dados.get("cnae_fiscal"),
                dados.get("cnae_fiscal_descricao"),
                dados.get("capital_social"),
                dados.get("porte"),
                _safe(dados.get("natureza_juridica")),
                _safe(dados.get("qsa")),
                _safe(dados.get("cnaes_secundarios")),
                dados.get("municipio"),
                dados.get("uf"),
            ),
        )

    def enriquecer_fornecedor(self, conn: sqlite3.Connection, fornecedor_ni: str) -> dict:
        """
        Consulta BrasilAPI para o fornecedor e persiste os dados cadastrais.

        - Se 200: salva em fornecedor_cadastro, atualiza tem_sancao (1 se inativo),
          capital_social e data_inicio_atividade em fornecedores.
        - Se 404 ou erro: marca como consultado (ultima_consulta_sancao = now)
          sem alterar tem_sancao.
        - Retorna dict com 'encontrado', 'situacao', 'ativo' e 'erro'.
        """
        dados = self.consultar_cnpj_brasilapi(fornecedor_ni)
        time.sleep(0.3)

        if dados is None:
            conn.execute(
                "UPDATE fornecedores SET ultima_consulta_sancao = datetime('now') WHERE ni = ?",
                (fornecedor_ni,),
            )
            conn.commit()
            return {"encontrado": False, "situacao": None, "ativo": None, "erro": False}

        self.salvar_cadastro(conn, fornecedor_ni, dados)

        situacao_cadastral = dados.get("situacao_cadastral")
        ativo = situacao_cadastral == 2  # 2 = ATIVA

        conn.execute(
            """
            UPDATE fornecedores
               SET tem_sancao             = ?,
                   ultima_consulta_sancao = datetime('now'),
                   capital_social         = ?,
                   data_inicio_atividade  = ?
             WHERE ni = ?
            """,
            (
                0 if ativo else 1,
                dados.get("capital_social"),
                dados.get("data_inicio_atividade"),
                fornecedor_ni,
            ),
        )
        conn.commit()

        return {
            "encontrado": True,
            "situacao": dados.get("descricao_situacao_cadastral"),
            "ativo": ativo,
            "erro": False,
        }


# ── Helpers privados ──────────────────────────────────────────────────────────

def _limpar_cnpj(cnpj: str) -> str:
    """Remove formatação do CNPJ, retornando apenas os 14 dígitos numéricos."""
    return re.sub(r"\D", "", str(cnpj))


def _safe(val) -> str | None:
    """Converte dict/list para JSON string; mantém None e escalares intactos."""
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return val
