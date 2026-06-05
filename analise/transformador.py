"""Transformação de despesas brutas (JSON) em dataset tabular padronizado."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_CHAVES_REGISTROS = ("data", "despesas", "items", "results", "registros")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _processed_data_dir() -> Path:
    custom = os.getenv("DATA_PROCESSED_DIR")
    if custom and custom.strip():
        return Path(custom.strip())
    return _project_root() / "data" / "processed"


def _formato_saida() -> str:
    formato = os.getenv("DATA_PROCESSED_FORMAT", "csv").strip().lower()
    if formato not in {"csv", "parquet"}:
        raise ValueError(
            f"DATA_PROCESSED_FORMAT inválido: {formato!r}. Use 'csv' ou 'parquet'."
        )
    return formato


def _validar_arquivo_entrada(filepath_entrada: str) -> Path:
    caminho = Path(filepath_entrada)
    if not caminho.is_file():
        raise FileNotFoundError(f"Arquivo de entrada inexistente: {caminho}")
    if caminho.stat().st_size == 0:
        raise ValueError(f"Arquivo de entrada vazio: {caminho}")
    return caminho


def _carregar_json(caminho: Path) -> Any:
    with caminho.open(encoding="utf-8") as handle:
        return json.load(handle)


def _extrair_registros(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for chave in _CHAVES_REGISTROS:
            valor = payload.get(chave)
            if isinstance(valor, list):
                return [item for item in valor if isinstance(item, dict)]
        return [payload]

    raise TypeError(
        f"Estrutura JSON não suportada: {type(payload).__name__}"
    )


def _para_snake_case(nome: str) -> str:
    texto = str(nome).strip()
    texto = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", texto)
    texto = re.sub(r"[\s\-\.]+", "_", texto)
    texto = re.sub(r"[^\w]+", "_", texto, flags=re.UNICODE)
    texto = re.sub(r"_+", "_", texto)
    return texto.strip("_").lower()


def _normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    renomear = {_col: _para_snake_case(_col) for _col in df.columns}
    normalizado = df.rename(columns=renomear)
    normalizado.columns = pd.Index(
        [_para_snake_case(col) for col in normalizado.columns]
    )
    return normalizado


def _remover_inconsistentes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    limpo = df.copy()
    for coluna in limpo.select_dtypes(include="object").columns:
        limpo[coluna] = limpo[coluna].apply(
            lambda valor: valor.strip() if isinstance(valor, str) else valor
        )
        limpo[coluna] = limpo[coluna].replace("", pd.NA)

    limpo = limpo.dropna(how="all")
    limpo = limpo.drop_duplicates()
    return limpo.reset_index(drop=True)


def _salvar_dataframe(df: pd.DataFrame, caminho_base: Path, formato: str) -> Path:
    if formato == "parquet":
        destino = caminho_base.with_suffix(".parquet")
        df.to_parquet(destino, index=False)
        return destino

    destino = caminho_base.with_suffix(".csv")
    df.to_csv(destino, index=False, encoding="utf-8")
    return destino


class TransformadorDespesas:
    """Converte JSON de despesas em arquivo tabular padronizado."""

    def processar_dados(self, filepath_entrada: str) -> str:
        logger.info("Início do processamento")

        caminho_entrada = _validar_arquivo_entrada(filepath_entrada)

        try:
            payload = _carregar_json(caminho_entrada)
            registros = _extrair_registros(payload)
            if not registros:
                raise ValueError(
                    f"Nenhum registro válido encontrado em: {caminho_entrada}"
                )

            dataframe = pd.DataFrame(registros)
            dataframe = _normalizar_colunas(dataframe)
            dataframe = _remover_inconsistentes(dataframe)
            if dataframe.empty:
                raise ValueError(
                    f"Dataset vazio após padronização: {caminho_entrada}"
                )
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error(
                "Falha na leitura ou conversão de %s: %s",
                caminho_entrada,
                exc,
            )
            raise

        diretorio_saida = _processed_data_dir()
        diretorio_saida.mkdir(parents=True, exist_ok=True)

        caminho_saida = _salvar_dataframe(
            dataframe,
            diretorio_saida / caminho_entrada.stem,
            _formato_saida(),
        )

        logger.info("Processamento concluído")
        return str(caminho_saida.resolve())
