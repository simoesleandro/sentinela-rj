"""Transformação de despesas brutas (JSON) em contratos padronizados."""
from __future__ import annotations

import csv
import json
import logging
import os
import re
import statistics
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_CHAVES_REGISTROS = ("data", "despesas", "items", "results", "registros")
_CHAVES_VALOR = ("valor_global", "valor", "valor_total", "valor_despesa")
_LIMIAR_Z_SCORE = 3.0


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _processed_data_dir() -> Path:
    custom = os.getenv("DATA_PROCESSED_DIR")
    if custom and custom.strip():
        return Path(custom.strip())
    return _project_root() / "data" / "processed"


def _formato_saida() -> str:
    formato = os.getenv("DATA_PROCESSED_FORMAT", "json").strip().lower()
    if formato not in {"csv", "json"}:
        raise ValueError(
            f"DATA_PROCESSED_FORMAT inválido: {formato!r}. Use 'csv' ou 'json'."
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


def _limpar_valor(valor: Any) -> Any:
    if isinstance(valor, str):
        texto = valor.strip()
        return None if texto == "" else texto
    return valor


def _normalizar_registro(registro: dict[str, Any]) -> dict[str, Any]:
    return {
        _para_snake_case(chave): _limpar_valor(valor)
        for chave, valor in registro.items()
    }


def _registro_vazio(registro: dict[str, Any]) -> bool:
    return all(valor is None for valor in registro.values())


def _chave_unica(registro: dict[str, Any]) -> str:
    return json.dumps(registro, sort_keys=True, default=str)


def _normalizar_registros(registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_normalizar_registro(registro) for registro in registros]


def _remover_inconsistentes(registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vistos: set[str] = set()
    limpos: list[dict[str, Any]] = []
    for registro in registros:
        if _registro_vazio(registro):
            continue
        chave = _chave_unica(registro)
        if chave in vistos:
            continue
        vistos.add(chave)
        limpos.append(registro)
    return limpos


def _extrair_valor_contrato(registro: dict[str, Any]) -> float | None:
    for chave in _CHAVES_VALOR:
        bruto = registro.get(chave)
        if bruto is None:
            continue
        try:
            valor = float(bruto)
        except (TypeError, ValueError):
            continue
        if valor > 0:
            return valor
    return None


def _coletar_valores(registros: list[dict[str, Any]]) -> list[float]:
    valores: list[float] = []
    for registro in registros:
        valor = _extrair_valor_contrato(registro)
        if valor is not None:
            valores.append(valor)
    return valores


def _calcular_limites_iqr(valores: list[float]) -> tuple[float, float]:
    quartis = statistics.quantiles(valores, n=4)
    q1, q3 = quartis[0], quartis[2]
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def _calcular_z_score(valor: float, media: float, desvio: float) -> float:
    if desvio == 0:
        return 0.0
    return (valor - media) / desvio


def _anomalia_iqr(valor: float, limite_inf: float, limite_sup: float) -> bool:
    return valor < limite_inf or valor > limite_sup


def _anomalia_z_score(z_score: float) -> bool:
    return abs(z_score) > _LIMIAR_Z_SCORE


def _anotar_registro(
    registro: dict[str, Any],
    *,
    limite_inf: float | None,
    limite_sup: float | None,
    media: float | None,
    desvio: float | None,
) -> dict[str, Any]:
    anotado = dict(registro)
    valor = _extrair_valor_contrato(registro)
    anotado["anomalia_iqr"] = False
    anotado["anomalia_z_score"] = False
    anotado["z_score"] = None
    if valor is None:
        return anotado
    if limite_inf is not None and limite_sup is not None:
        anotado["anomalia_iqr"] = _anomalia_iqr(valor, limite_inf, limite_sup)
    if media is not None and desvio is not None:
        z_score = _calcular_z_score(valor, media, desvio)
        anotado["z_score"] = round(z_score, 4)
        anotado["anomalia_z_score"] = _anomalia_z_score(z_score)
    return anotado


def _marcar_anomalias(registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valores = _coletar_valores(registros)
    if len(valores) < 2:
        return [dict(registro) for registro in registros]
    limite_inf, limite_sup = _calcular_limites_iqr(valores)
    media = statistics.mean(valores)
    desvio = statistics.stdev(valores)
    return [
        _anotar_registro(
            registro,
            limite_inf=limite_inf,
            limite_sup=limite_sup,
            media=media,
            desvio=desvio,
        )
        for registro in registros
    ]


def _coletar_colunas(registros: list[dict[str, Any]]) -> list[str]:
    colunas: list[str] = []
    vistas: set[str] = set()
    for registro in registros:
        for chave in registro:
            if chave not in vistas:
                vistas.add(chave)
                colunas.append(chave)
    return colunas


def _salvar_json(registros: list[dict[str, Any]], destino: Path) -> Path:
    with destino.open("w", encoding="utf-8") as handle:
        json.dump(registros, handle, ensure_ascii=False, indent=2)
    return destino


def _salvar_csv(registros: list[dict[str, Any]], destino: Path) -> Path:
    colunas = _coletar_colunas(registros)
    with destino.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=colunas)
        writer.writeheader()
        writer.writerows(registros)
    return destino


def _salvar_registros(
    registros: list[dict[str, Any]],
    caminho_base: Path,
    formato: str,
) -> Path:
    if formato == "csv":
        return _salvar_csv(registros, caminho_base.with_suffix(".csv"))
    return _salvar_json(registros, caminho_base.with_suffix(".json"))


class TransformadorDespesas:
    """Converte JSON de despesas em contratos padronizados com detecção de anomalias."""

    def _validar_registros(self, registros: list[dict[str, Any]]) -> None:
        if not registros:
            raise ValueError("Lista de contratos vazia: nada a processar.")

    def processar_registros(self, registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalizados = _normalizar_registros(registros)
        limpos = _remover_inconsistentes(normalizados)
        self._validar_registros(limpos)
        anotados = _marcar_anomalias(limpos)
        self._validar_registros(anotados)
        return anotados

    def processar_dados(self, filepath_entrada: str) -> str:
        logger.info("Início do processamento")
        caminho_entrada = _validar_arquivo_entrada(filepath_entrada)

        try:
            payload = _carregar_json(caminho_entrada)
            registros = _extrair_registros(payload)
            processados = self.processar_registros(registros)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error(
                "Falha na leitura ou conversão de %s: %s",
                caminho_entrada,
                exc,
            )
            raise

        diretorio_saida = _processed_data_dir()
        diretorio_saida.mkdir(parents=True, exist_ok=True)
        caminho_saida = _salvar_registros(
            processados,
            diretorio_saida / caminho_entrada.stem,
            _formato_saida(),
        )
        logger.info("Processamento concluído")
        return str(caminho_saida.resolve())
