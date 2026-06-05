"""Testes unitários do gerenciador de banco de dados."""
from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from db.database import GerenciadorBanco


@pytest.fixture
def engine_memoria() -> Engine:
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture
def gerenciador(engine_memoria: Engine) -> GerenciadorBanco:
    return GerenciadorBanco(engine=engine_memoria)


def test_salvar_despesas_sucesso(
    gerenciador: GerenciadorBanco,
    engine_memoria: Engine,
) -> None:
    df = pd.DataFrame([{"orgao_id": "org-1", "valor": 100.0}])
    gerenciador.salvar_despesas(df, "despesas")

    salvo = pd.read_sql("SELECT * FROM despesas", engine_memoria)
    assert len(salvo) == 1
    assert salvo.iloc[0]["orgao_id"] == "org-1"
    assert float(salvo.iloc[0]["valor"]) == 100.0


def test_salvar_despesas_df_vazio(gerenciador: GerenciadorBanco) -> None:
    df = pd.DataFrame()

    with pytest.raises(ValueError, match="DataFrame vazio"):
        gerenciador.salvar_despesas(df, "despesas")
