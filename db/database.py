"""Persistência de despesas via SQLAlchemy."""
from __future__ import annotations

import logging
import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

logger = logging.getLogger(__name__)


def _resolver_engine(
    database_url: str | None,
    engine: Engine | None,
) -> Engine:
    if engine is not None:
        return engine
    url = database_url or os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise ValueError("DATABASE_URL não definida e engine não fornecido.")
    return create_engine(url)


def _validar_dataframe(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError("DataFrame vazio: nada a persistir.")


def _validar_nome_tabela(nome_tabela: str) -> str:
    nome = nome_tabela.strip()
    if not nome:
        raise ValueError("nome_tabela não pode ser vazio.")
    return nome


class GerenciadorBanco:
    """Gerencia persistência tabular de despesas no banco relacional."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        engine: Engine | None = None,
    ) -> None:
        self._engine: Engine = _resolver_engine(database_url, engine)

    def salvar_despesas(self, df: pd.DataFrame, nome_tabela: str) -> None:
        tabela = _validar_nome_tabela(nome_tabela)
        logger.info("Início da persistência em '%s'", tabela)
        _validar_dataframe(df)

        try:
            df.to_sql(
                tabela,
                self._engine,
                if_exists="append",
                index=False,
                method="multi",
            )
        except SQLAlchemyError as exc:
            logger.error(
                "Falha ao persistir despesas em '%s': %s",
                tabela,
                exc,
            )
            raise

        logger.info(
            "Persistência concluída: %d registros em '%s'",
            len(df),
            tabela,
        )
