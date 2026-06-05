"""Cliente HTTP para consulta de despesas (API Sentinela)."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S = 10


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise ValueError(f"Variável de ambiente obrigatória não definida: {name}")
    return value.strip()


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _raw_data_dir() -> Path:
    custom = os.getenv("DATA_RAW_DIR")
    if custom and custom.strip():
        return Path(custom.strip())
    return _project_root() / "data" / "raw"


class SentinelaAPI:
    """Cliente da API de despesas com persistência do JSON bruto."""

    def __init__(self) -> None:
        self._base_url: str = _require_env("SENTINELA_API_BASE_URL").rstrip("/")
        self._despesas_path: str = _require_env("SENTINELA_API_DESPESAS_PATH")

    def buscar_despesas(
        self,
        orgao_id: str,
        data_inicio: str,
        data_fim: str,
    ) -> dict[str, Any] | None:
        raw_dir = _raw_data_dir()
        raw_dir.mkdir(parents=True, exist_ok=True)

        url = f"{self._base_url}{self._despesas_path}"
        params: dict[str, str] = {
            "orgao_id": orgao_id,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
        }

        try:
            response = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT_S)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            logger.error(
                "Falha de conexão ao buscar despesas (orgao=%s, %s–%s): %s",
                orgao_id,
                data_inicio,
                data_fim,
                exc,
            )
            return None
        except requests.RequestException as exc:
            logger.error(
                "Erro na requisição de despesas (orgao=%s, %s–%s): %s",
                orgao_id,
                data_inicio,
                data_fim,
                exc,
            )
            return None
        except ValueError as exc:
            logger.error(
                "Resposta inválida da API de despesas (orgao=%s, %s–%s): %s",
                orgao_id,
                data_inicio,
                data_fim,
                exc,
            )
            return None

        filename = f"despesas_{orgao_id}_{data_inicio}_{data_fim}.json"
        out_path = raw_dir / filename
        with out_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

        return payload
