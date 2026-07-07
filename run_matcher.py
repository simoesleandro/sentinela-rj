"""Gera candidatos a conflito de interesse: sócio de empresa contratada que
também é servidor público ativo.

Uso:
    python run_matcher.py

Fontes: fornecedor_cadastro (data/sentinela_rj.db) e servidores
(data/folha_pagamento.db). Destino: candidatos_conflito_interesse no Supabase
(CONFLITO_INTERESSE_DATABASE_URL). Não escreve em 'casos'/'alertas' — a
promoção desses candidatos é decidida depois, no fluxo de triagem (triagem.py).

Também chamado por automacoes/pipeline.py (job semanal agendado via
CONFLITO_INTERESSE_CRON) — ver executar_matching().
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

from conflito_interesse.enriquecimento import enriquecer_candidatos
from conflito_interesse.indice_servidores import IndiceServidoresPorToken
from conflito_interesse.matcher import ConflictMatcherService
from conflito_interesse.repository import CandidatoConflitoRepository

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
SENTINELA_DB = ROOT / "data" / "sentinela_rj.db"
FOLHA_DB = ROOT / "data" / "folha_pagamento.db"


def executar_matching() -> dict[str, int]:
    """Roda o matcher + enriquecimento + upsert no Supabase uma vez.

    Levanta RuntimeError se CONFLITO_INTERESSE_DATABASE_URL não estiver
    configurada — quem chama decide como tratar (CLI aqui embaixo devolve
    exit code 1, o pipeline agendado captura e loga como falha da etapa).
    """
    dsn = os.environ.get("CONFLITO_INTERESSE_DATABASE_URL")
    if not dsn:
        raise RuntimeError("CONFLITO_INTERESSE_DATABASE_URL não configurada.")

    import psycopg2

    conn_folha = sqlite3.connect(FOLHA_DB)
    conn_sentinela = sqlite3.connect(SENTINELA_DB)
    conn_supabase = psycopg2.connect(dsn)
    try:
        indice = IndiceServidoresPorToken(conn_folha)
        candidatos = ConflictMatcherService(conn_sentinela, indice).buscar_candidatos()
        candidatos = enriquecer_candidatos(candidatos, conn_sentinela, indice)

        fornecedores_processados = conn_sentinela.execute(
            "SELECT COUNT(*) FROM fornecedor_cadastro WHERE socios IS NOT NULL AND socios != ''"
        ).fetchone()[0]
        alta_confianca = sum(1 for c in candidatos if c.score_similaridade >= 90)
        media_confianca = sum(1 for c in candidatos if 80 <= c.score_similaridade < 90)

        afetados = CandidatoConflitoRepository(conn_supabase).salvar_candidatos(candidatos)

        return {
            "fornecedores_processados": fornecedores_processados,
            "candidatos_gerados": len(candidatos),
            "alta_confianca": alta_confianca,
            "media_confianca": media_confianca,
            "afetados": afetados,
        }
    finally:
        conn_folha.close()
        conn_sentinela.close()
        conn_supabase.close()


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        metricas = executar_matching()
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1

    logger.info("Fornecedores processados: %d", metricas["fornecedores_processados"])
    logger.info(
        "Candidatos gerados: %d (score>=90: %d, score 80-89: %d)",
        metricas["candidatos_gerados"], metricas["alta_confianca"], metricas["media_confianca"],
    )
    logger.info(
        "Candidatos inseridos ou atualizados (upsert, status preservado): %d", metricas["afetados"]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
