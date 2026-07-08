"""Match entre sócios de fornecedores e servidores públicos ativos.

Não existe CPF utilizável dos dois lados (fornecedor_cadastro tem CPF mascarado,
folha de pagamento não tem CPF algum) — o match é 100% por nome, com normalização
+ fuzzy matching, restrito pelo primeiro token para não comparar cada sócio contra
os 286k servidores.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from rapidfuzz import fuzz

from .indice_servidores import IndiceServidoresPorToken
from .normalizador import normalizar_nome


@dataclass
class CandidatoConflito:
    fornecedor_ni: str
    nome_socio: str
    qualificacao_socio: str | None
    matricula_servidor: str
    nome_servidor: str
    sigla_ua: str | None
    score_similaridade: float
    data_entrada_sociedade: str | None = None
    faixa_etaria_socio: str | None = None
    primeira_competencia_servidor: str | None = None
    contrato_ativo: bool = False
    valor_total_contratos: float | None = None
    qtd_servidores_matched_mesmo_socio: int = 1
    tem_alerta_severidade_alta: bool = False
    tem_sancao: bool = False
    qtd_servidores_mesmo_nome: int = 1
    lotacao_orgao_contratante: bool = False


class ConflictMatcherService:
    """Para cada sócio de cada fornecedor, busca servidores candidatos pelo primeiro
    token do nome normalizado e pontua com rapidfuzz.token_sort_ratio.
    """

    SCORE_MINIMO = 80.0

    def __init__(self, conn_fornecedores: sqlite3.Connection, indice: IndiceServidoresPorToken):
        self._conn = conn_fornecedores
        self._indice = indice

    def buscar_candidatos(self) -> list[CandidatoConflito]:
        candidatos: list[CandidatoConflito] = []
        cursor = self._conn.execute(
            "SELECT fornecedor_ni, socios FROM fornecedor_cadastro "
            "WHERE socios IS NOT NULL AND socios != ''"
        )
        for fornecedor_ni, socios_json in cursor:
            try:
                socios = json.loads(socios_json)
            except (TypeError, ValueError):
                continue
            for socio in socios:
                candidatos.extend(self._match_socio(fornecedor_ni, socio))
        return candidatos

    def _match_socio(self, fornecedor_ni: str, socio: dict) -> list[CandidatoConflito]:
        nome_socio = socio.get("nome_socio") or ""
        nome_normalizado = normalizar_nome(nome_socio)
        if not nome_normalizado:
            return []
        primeiro_token = nome_normalizado.split(" ", 1)[0]

        resultado: list[CandidatoConflito] = []
        for matricula, nome_servidor in self._indice.candidatos(primeiro_token):
            score = fuzz.token_sort_ratio(nome_normalizado, nome_servidor)
            if score >= self.SCORE_MINIMO:
                resultado.append(
                    CandidatoConflito(
                        fornecedor_ni=fornecedor_ni,
                        nome_socio=nome_socio,
                        qualificacao_socio=socio.get("qualificacao_socio"),
                        matricula_servidor=matricula,
                        nome_servidor=nome_servidor,
                        sigla_ua=self._indice.sigla_ua_mais_recente(matricula),
                        score_similaridade=float(score),
                        data_entrada_sociedade=socio.get("data_entrada_sociedade"),
                        faixa_etaria_socio=socio.get("faixa_etaria"),
                        primeira_competencia_servidor=self._indice.primeira_competencia(matricula),
                    )
                )
        return resultado
