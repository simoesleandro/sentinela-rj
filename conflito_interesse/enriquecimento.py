"""Enriquece candidatos a conflito de interesse com sinais que já existem no
banco (sem fonte externa nova), para priorizar a fila de revisão manual.

Nenhum desses sinais prova identidade — são só heurísticas de relevância
(um contrato ativo e de valor alto, com vários sócios do mesmo fornecedor
batendo com servidores, é mais urgente de revisar do que um match isolado
de baixo valor). Não mexem em score_similaridade, que continua sendo o
único critério de qualidade do match por nome.
"""
from __future__ import annotations

import dataclasses
import sqlite3
from collections import defaultdict
from typing import Iterable

from .indice_servidores import IndiceServidoresPorToken
from .matcher import CandidatoConflito
from .normalizador import normalizar_nome

# ConflictMatcherService aceita score_similaridade a partir de 80 (fuzzy) —
# suficiente para achar candidatos, mas alto demais para CONTAR quantos
# servidores bateram com "o mesmo sócio": um sobrenome comum (ex.: "LEANDRO
# SILVA") bate, com score 81-84, em dezenas de servidores com nomes só
# parecidos (LEANDRO SILVA MELO, LEANDRO GOMES SILVA, LEANDRO SILVA CRUZ...),
# que não são a mesma pessoa. Só um match de nome IDÊNTICO após normalização
# (score 100) é confiável o bastante para reforçar esse sinal específico.
SCORE_MATCH_EXATO = 100.0


def contar_servidores_por_socio(candidatos: Iterable[CandidatoConflito]) -> dict[tuple[str, str], int]:
    """Quantos servidores (matrícula distinta) deram match de nome EXATO com
    o MESMO sócio (fornecedor_ni, nome_socio normalizado) — não para o
    fornecedor como um todo, e não contando matches fuzzy (score < 100)
    dentro do próprio grupo do sócio.

    Duas correções em cima da primeira versão deste sinal (que agrupava só
    por fornecedor_ni): agrupar só por fornecedor_ni satura porque uma
    empresa com N sócios reais distintos, cada um batendo isoladamente com
    um servidor diferente, reflete tamanho da empresa, não conflito
    sistêmico. Mas agrupar por (fornecedor_ni, sócio) sozinho AINDA satura
    (93.8% dos 972 candidatos reais, jul/2026) porque sobrenomes comuns
    puxam vários servidores diferentes por fuzzy matching — ver comentário
    de SCORE_MATCH_EXATO acima. Restringindo a matches exatos, a saturação
    real caiu para 13.2% (128/972).
    """
    matriculas_por_socio: dict[tuple[str, str], set[str]] = defaultdict(set)
    for c in candidatos:
        if c.score_similaridade < SCORE_MATCH_EXATO:
            continue
        chave = (c.fornecedor_ni, normalizar_nome(c.nome_socio))
        matriculas_por_socio[chave].add(c.matricula_servidor)
    return {chave: len(matriculas) for chave, matriculas in matriculas_por_socio.items()}


def buscar_contrato_ativo(conn: sqlite3.Connection, fornecedor_ni: str) -> bool:
    """Existe algum contrato do fornecedor cuja vigência cobre a data atual."""
    row = conn.execute(
        """
        SELECT 1 FROM contratos
        WHERE fornecedor_ni = ?
          AND data_vigencia_inicio <= date('now')
          AND data_vigencia_fim >= date('now')
        LIMIT 1
        """,
        (fornecedor_ni,),
    ).fetchone()
    return row is not None


def somar_valor_contratos(conn: sqlite3.Connection, fornecedor_ni: str) -> float | None:
    """Soma o valor_global de todos os contratos do fornecedor (mesma
    convenção de 'valor > 0' usada no resto do app para filtrar contratos
    sem valor financeiro real, ex.: adesões a ata sem execução)."""
    row = conn.execute(
        "SELECT SUM(valor_global) FROM contratos WHERE fornecedor_ni = ? AND valor_global > 0",
        (fornecedor_ni,),
    ).fetchone()
    valor = row[0] if row else None
    return float(valor) if valor is not None else None


def tem_alerta_severidade_alta(conn: sqlite3.Connection, fornecedor_ni: str) -> bool:
    """Fornecedor já tem algum alerta de severidade alta (valor atípico,
    fornecedor recorrente, adesão suspeita...) em algum contrato dele —
    evidência de irregularidade que já existia ANTES do match sócio-servidor,
    então é genuinamente independente do problema de nome comum."""
    row = conn.execute(
        """
        SELECT 1 FROM contratos c
        JOIN alertas a ON a.numero_controle_pncp = c.numero_controle_pncp
        WHERE c.fornecedor_ni = ? AND a.severidade = 'alta'
        LIMIT 1
        """,
        (fornecedor_ni,),
    ).fetchone()
    return row is not None


def tem_sancao(conn: sqlite3.Connection, fornecedor_ni: str) -> bool:
    """Fornecedor tem algum registro em fornecedor_sancoes (independente de
    a sanção estar em vigor ou não — o histórico já é relevante pra
    triagem)."""
    row = conn.execute(
        "SELECT 1 FROM fornecedor_sancoes WHERE fornecedor_ni = ? LIMIT 1",
        (fornecedor_ni,),
    ).fetchone()
    return row is not None


def enriquecer_candidatos(
    candidatos: list[CandidatoConflito],
    conn_sentinela: sqlite3.Connection,
    indice: IndiceServidoresPorToken,
) -> list[CandidatoConflito]:
    """Preenche contrato_ativo, valor_total_contratos,
    qtd_servidores_matched_mesmo_socio, tem_alerta_severidade_alta,
    tem_sancao e qtd_servidores_mesmo_nome. Consulta 'contratos'/'alertas'/
    'fornecedor_sancoes' uma vez por fornecedor_ni distinto (cache local),
    não uma vez por candidato — o mesmo fornecedor pode aparecer várias
    vezes no lote (vários sócios ou vários servidores batendo)."""
    if not candidatos:
        return []

    qtd_por_socio = contar_servidores_por_socio(candidatos)
    cache_contrato_ativo: dict[str, bool] = {}
    cache_valor_total: dict[str, float | None] = {}
    cache_alerta_alta: dict[str, bool] = {}
    cache_sancao: dict[str, bool] = {}
    cache_freq_nome: dict[str, int] = {}

    enriquecidos = []
    for c in candidatos:
        ni = c.fornecedor_ni
        if ni not in cache_contrato_ativo:
            cache_contrato_ativo[ni] = buscar_contrato_ativo(conn_sentinela, ni)
            cache_valor_total[ni] = somar_valor_contratos(conn_sentinela, ni)
            cache_alerta_alta[ni] = tem_alerta_severidade_alta(conn_sentinela, ni)
            cache_sancao[ni] = tem_sancao(conn_sentinela, ni)
        chave_socio = (ni, normalizar_nome(c.nome_socio))
        # Piso de 1: um candidato cujo próprio match é fuzzy (score < 100) não
        # entra no dict acima (não é "confiável" o bastante pra contar), mas
        # ele continua existindo — não faz sentido reportar 0 servidores.
        qtd = max(qtd_por_socio.get(chave_socio, 0), 1)

        nome_servidor_normalizado = normalizar_nome(c.nome_servidor)
        if nome_servidor_normalizado not in cache_freq_nome:
            cache_freq_nome[nome_servidor_normalizado] = indice.frequencia_nome(nome_servidor_normalizado)
        # Piso de 1: o próprio candidato sempre existe, mesmo que a busca no
        # índice (bloqueada por primeiro token) não confirme o total.
        freq_nome = max(cache_freq_nome[nome_servidor_normalizado], 1)

        enriquecidos.append(
            dataclasses.replace(
                c,
                contrato_ativo=cache_contrato_ativo[ni],
                valor_total_contratos=cache_valor_total[ni],
                qtd_servidores_matched_mesmo_socio=qtd,
                tem_alerta_severidade_alta=cache_alerta_alta[ni],
                tem_sancao=cache_sancao[ni],
                qtd_servidores_mesmo_nome=freq_nome,
            )
        )
    return enriquecidos
