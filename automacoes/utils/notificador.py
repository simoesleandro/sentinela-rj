"""Notificações de alertas críticos via Discord."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_STATUS_CRITICO = "[🔴 CRITICAL]"
_EMBED_COR_CRITICO = 0xED4245
_REQUEST_TIMEOUT_S = 10


def _webhook_url() -> str:
    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        raise ValueError("DISCORD_WEBHOOK_URL não definida.")
    return url


def _timestamp_ocorrencia() -> datetime:
    return datetime.now(timezone.utc)


def _montar_embed(titulo: str, mensagem_erro: str) -> dict[str, Any]:
    ocorrido_em = _timestamp_ocorrencia()
    iso = ocorrido_em.isoformat()
    return {
        "title": f"{_STATUS_CRITICO} {titulo}",
        "description": mensagem_erro,
        "color": _EMBED_COR_CRITICO,
        "footer": {"text": f"Timestamp: {iso}"},
        "timestamp": iso,
    }


def _montar_payload(embed: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {"embeds": [embed]}


def _enviar_webhook(url: str, payload: dict[str, Any]) -> None:
    try:
        response = requests.post(url, json=payload, timeout=_REQUEST_TIMEOUT_S)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Falha ao enviar alerta Discord: %s", exc)
        raise


class NotificadorAlertas:
    """Envia alertas estruturados para canais Discord via webhook."""

    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook_url: str = webhook_url or _webhook_url()

    def enviar_alerta_discord(self, titulo: str, mensagem_erro: str) -> None:
        embed = _montar_embed(titulo.strip(), mensagem_erro.strip())
        payload = _montar_payload(embed)
        _enviar_webhook(self._webhook_url, payload)
        logger.info("Alerta Discord enviado: %s", titulo)
