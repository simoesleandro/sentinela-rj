"""Orquestrador do pipeline de extração e persistência de despesas."""
from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from db.database import GerenciadorBanco
from extrator.api_client import SentinelaAPI

load_dotenv()

logger = logging.getLogger(__name__)

_CHAVES_REGISTROS = ("data", "despesas", "items", "results", "registros")
_ALERTA_TITULO = "[🔴 CRITICAL] - Pipeline Dados Abertos"


def _require_env(nome: str) -> str:
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise ValueError(f"Variável de ambiente obrigatória não definida: {nome}")
    return valor


def _max_tentativas() -> int:
    return max(1, int(os.getenv("PIPELINE_MAX_TENTATIVAS", "3")))


def _backoff_base_s() -> float:
    return float(os.getenv("PIPELINE_BACKOFF_BASE_S", "1"))


def _calcular_espera(tentativa: int) -> float:
    atraso = _backoff_base_s() * (2**tentativa)
    jitter = random.uniform(0, atraso * 0.25)
    return atraso + jitter


def _log_erro_critico(causa: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.error(
        "%s\nCausa: %s\nTimestamp: %s",
        _ALERTA_TITULO,
        causa,
        timestamp,
    )


def _extrair_registros(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for chave in _CHAVES_REGISTROS:
            valor = payload.get(chave)
            if isinstance(valor, list):
                return [item for item in valor if isinstance(item, dict)]
        return [payload]
    return []


def _payload_para_dataframe(payload: dict[str, Any]) -> pd.DataFrame:
    registros = _extrair_registros(payload)
    if not registros:
        raise ValueError("Payload da API não contém registros válidos.")
    return pd.DataFrame(registros)


def _buscar_com_backoff(
    api: SentinelaAPI,
    orgao_id: str,
    data_inicio: str,
    data_fim: str,
) -> dict[str, Any]:
    ultima_causa = "Falha desconhecida na extração."
    for tentativa in range(_max_tentativas()):
        resultado = api.buscar_despesas(orgao_id, data_inicio, data_fim)
        if resultado is not None:
            return resultado
        ultima_causa = (
            f"API retornou vazio (tentativa {tentativa + 1}/{_max_tentativas()})."
        )
        if tentativa < _max_tentativas() - 1:
            time.sleep(_calcular_espera(tentativa))
    raise RuntimeError(ultima_causa)


def _persistir_despesas(df: pd.DataFrame, tabela: str) -> None:
    gerenciador = GerenciadorBanco()
    gerenciador.salvar_despesas(df, tabela)


def executar_pipeline() -> None:
    logger.info("Script de monitoramento iniciado")
    orgao_id = _require_env("PIPELINE_ORGAO_ID")
    data_inicio = _require_env("PIPELINE_DATA_INICIO")
    data_fim = _require_env("PIPELINE_DATA_FIM")
    tabela = _require_env("PIPELINE_TABELA_DESPESAS")

    try:
        api = SentinelaAPI()
        payload = _buscar_com_backoff(api, orgao_id, data_inicio, data_fim)
        df = _payload_para_dataframe(payload)
        _persistir_despesas(df, tabela)
        logger.info("Pipeline concluído com sucesso.")
    except Exception as exc:
        _log_erro_critico(str(exc))
        raise


if __name__ == "__main__":
    executar_pipeline()
