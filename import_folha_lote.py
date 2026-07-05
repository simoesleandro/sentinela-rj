"""Orquestra import_folha.py para todos os CSVs de uma pasta.

Uso:
    python import_folha_lote.py C:\\caminho\\para\\pasta_com_csvs

Reaproveita PayrollImportService por arquivo (SRP: este script só orquestra,
nao duplica logica de parsing/insercao). Continua para o proximo arquivo se
um falhar, reportando no final quais tiveram erro.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from folha_pagamento.repository import SqliteFolhaPagamentoRepository, get_conn
from folha_pagamento.service import PayrollImportService

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if len(sys.argv) != 2:
        logger.error("Uso: python import_folha_lote.py <pasta_com_csvs>")
        return 1

    pasta = Path(sys.argv[1])
    arquivos = sorted(pasta.glob("ArquivoTC*.csv"))
    if not arquivos:
        logger.error("Nenhum ArquivoTC*.csv encontrado em %s", pasta)
        return 1

    sucesso, falha = [], []
    conn = get_conn()
    try:
        repository = SqliteFolhaPagamentoRepository(conn)
        servico = PayrollImportService(repository)
        for arquivo in arquivos:
            try:
                resultado = servico.importar(str(arquivo))
                logger.info("%s -> %s", arquivo.name, resultado)
                sucesso.append(arquivo.name)
            except Exception:
                logger.exception("Falhou: %s", arquivo.name)
                falha.append(arquivo.name)
    finally:
        conn.close()

    logger.info("Resumo: %d ok, %d falhas. Falhas: %s", len(sucesso), len(falha), falha)
    return 1 if falha else 0


if __name__ == "__main__":
    sys.exit(main())
