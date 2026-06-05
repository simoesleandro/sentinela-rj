"""Entrypoint oficial do pipeline Sentinela."""
from __future__ import annotations

import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from analise.transformador import TransformadorDespesas
from automacoes.utils.notificador import NotificadorAlertas
from db.database import GerenciadorBanco
from extrator.api_client import SentinelaAPI

load_dotenv()

logger = logging.getLogger(__name__)

_TITULO_ALERTA = "Pipeline Sentinela"


def _configurar_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _require_env(nome: str) -> str:
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise ValueError(f"Variável de ambiente obrigatória não definida: {nome}")
    return valor


def _periodo_execucao() -> tuple[str, str]:
    janela = max(1, int(os.getenv("MAIN_JANELA_DIAS", "30")))
    fim = date.today()
    inicio = fim - timedelta(days=janela)
    return inicio.strftime("%Y%m%d"), fim.strftime("%Y%m%d")


def _raw_data_dir() -> Path:
    custom = os.getenv("DATA_RAW_DIR", "").strip()
    if custom:
        return Path(custom)
    return Path(__file__).resolve().parent / "data" / "raw"


def _caminho_json_bruto(orgao_id: str, data_inicio: str, data_fim: str) -> Path:
    nome = f"despesas_{orgao_id}_{data_inicio}_{data_fim}.json"
    return _raw_data_dir() / nome


def _extrair_despesas(orgao_id: str, data_inicio: str, data_fim: str) -> Path:
    api = SentinelaAPI()
    payload = api.buscar_despesas(orgao_id, data_inicio, data_fim)
    if payload is None:
        raise RuntimeError("Extração falhou: API retornou vazio.")
    caminho = _caminho_json_bruto(orgao_id, data_inicio, data_fim)
    if not caminho.is_file():
        raise FileNotFoundError(f"JSON bruto não encontrado: {caminho}")
    return caminho


def _transformar_despesas(caminho_json: Path) -> Path:
    transformador = TransformadorDespesas()
    caminho_saida = transformador.processar_dados(str(caminho_json))
    return Path(caminho_saida)


def _carregar_dataframe_processado(caminho: Path) -> pd.DataFrame:
    if caminho.suffix == ".parquet":
        return pd.read_parquet(caminho)
    return pd.read_csv(caminho)


def _persistir_despesas(df: pd.DataFrame) -> None:
    tabela = _require_env("MAIN_TABELA_DESPESAS")
    database_url = os.getenv("DATABASE_URL", "").strip() or None
    gerenciador = GerenciadorBanco(database_url=database_url)
    gerenciador.salvar_despesas(df, tabela)


def _notificar_falha(erro: Exception) -> None:
    try:
        NotificadorAlertas().enviar_alerta_discord(_TITULO_ALERTA, str(erro))
    except Exception as notify_exc:
        logger.error("Falha ao enviar alerta Discord: %s", notify_exc)


def executar() -> None:
    orgao_id = _require_env("MAIN_ORGAO_ID")
    data_inicio, data_fim = _periodo_execucao()
    logger.info("Pipeline iniciado (orgao=%s, %s–%s)", orgao_id, data_inicio, data_fim)

    caminho_json = _extrair_despesas(orgao_id, data_inicio, data_fim)
    caminho_processado = _transformar_despesas(caminho_json)
    df = _carregar_dataframe_processado(caminho_processado)
    _persistir_despesas(df)

    logger.info("Pipeline concluído com sucesso.")


if __name__ == "__main__":
    _configurar_logging()
    try:
        executar()
    except Exception as exc:
        logger.error("Falha crítica no pipeline: %s", exc)
        _notificar_falha(exc)
        sys.exit(1)
