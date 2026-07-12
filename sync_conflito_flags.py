"""Materializa no core (data/sentinela_rj.db) os sinais de conflito de interesse
por fornecedor, lidos do Supabase (CONFLITO_INTERESSE_DATABASE_URL).

Uso:
    python sync_conflito_flags.py

Popula a tabela `fornecedores_conflito`, consumida pela fila de alertas para o
selo "sócio-servidor" e o filtro de triagem. Em produção o mesmo trabalho é
feito pelo endpoint admin POST /api/admin/sync-conflito-flags (o Supabase é
alcançável da app, sem transfer de DB). Rode este CLI depois de run_matcher.py
quando estiver atualizando os candidatos localmente.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys

from dotenv import load_dotenv

from db.conexao import DB_PATH, aplicar_migracoes
from db.conflito_flags import sincronizar_flags

logger = logging.getLogger(__name__)

# Respeita DB_PATH (env) — em produção o core vive no volume /data, não em ./data.
SENTINELA_DB = DB_PATH


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    dsn = os.environ.get("CONFLITO_INTERESSE_DATABASE_URL")
    if not dsn:
        logger.error("CONFLITO_INTERESSE_DATABASE_URL não configurada.")
        return 1

    import psycopg2

    conn_core = sqlite3.connect(SENTINELA_DB)
    conn_conflito = psycopg2.connect(dsn)
    try:
        aplicar_migracoes(conn_core)  # garante a tabela fornecedores_conflito
        n = sincronizar_flags(conn_core, conn_conflito)
        logger.info("Fornecedores com conflito materializados: %d", n)
    finally:
        conn_core.close()
        conn_conflito.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
