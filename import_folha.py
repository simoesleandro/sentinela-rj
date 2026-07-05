"""CLI de importação manual da folha de pagamento (PCRJ) para o SQLite local.

Uso:
    python import_folha.py caminho/ArquivoTC202106.csv

Persiste em data/folha_pagamento.db (mesmo padrão dos outros bancos do projeto).
"""
from __future__ import annotations

import argparse
import logging
import sys

from folha_pagamento.repository import SqliteFolhaPagamentoRepository, get_conn
from folha_pagamento.service import PayrollImportService

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Importa folha de pagamento PCRJ para o SQLite local")
    parser.add_argument("caminho_csv", help="Caminho do arquivo ArquivoTC{AAAAMM}.csv")
    args = parser.parse_args()

    conn = get_conn()
    try:
        repository = SqliteFolhaPagamentoRepository(conn)
        resultado = PayrollImportService(repository).importar(args.caminho_csv)
    finally:
        conn.close()

    logger.info("Importação concluída: %s", resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
