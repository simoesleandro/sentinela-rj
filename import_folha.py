"""CLI de importação manual da folha de pagamento (PCRJ) para o Supabase.

Uso:
    python import_folha.py caminho/ArquivoTC202106.csv

Requer a variável de ambiente FOLHA_DATABASE_URL (connection string do Postgres
do Supabase dedicado a este domínio — ver .env.example).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from folha_pagamento.repository import SupabaseFolhaPagamentoRepository
from folha_pagamento.service import PayrollImportService

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Importa folha de pagamento PCRJ para o Supabase")
    parser.add_argument("caminho_csv", help="Caminho do arquivo ArquivoTC{AAAAMM}.csv")
    args = parser.parse_args()

    dsn = os.environ.get("FOLHA_DATABASE_URL")
    if not dsn:
        logger.error("FOLHA_DATABASE_URL não configurada.")
        return 1

    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        repository = SupabaseFolhaPagamentoRepository(conn)
        resultado = PayrollImportService(repository).importar(args.caminho_csv)
    finally:
        conn.close()

    logger.info("Importação concluída: %s", resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
