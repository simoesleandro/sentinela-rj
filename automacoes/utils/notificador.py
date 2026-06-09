"""Notificações de alertas críticos via Discord."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

from analise.labels import label_tipo

load_dotenv()

logger = logging.getLogger(__name__)

_STATUS_CRITICO = "[🔴 CRITICAL]"
_EMBED_COR_ALTA = 0xED4245
_EMBED_COR_RESUMO = 0x5865F2
_REQUEST_TIMEOUT_S = 10
_PNCP_URL = "https://pncp.gov.br/app/contratos/{pncp_id}"
_MAX_DESCRICAO = 300
_MAX_NARRATIVA = 400


def _webhook_url() -> str:
    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        raise ValueError("DISCORD_WEBHOOK_URL não definida.")
    return url


def _env_float(nome: str, padrao: float) -> float:
    raw = os.getenv(nome, "").strip()
    return float(raw) if raw else padrao


def _timestamp_ocorrencia() -> datetime:
    return datetime.now(timezone.utc)


def _formatar_moeda(valor: float | None) -> str:
    if valor is None:
        return "—"
    return f"R$ {valor:,.2f}"


def _truncar(texto: str | None, limite: int) -> str:
    if not texto:
        return "—"
    texto = texto.strip()
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _montar_embed_erro(titulo: str, mensagem_erro: str) -> dict[str, Any]:
    ocorrido_em = _timestamp_ocorrencia()
    iso = ocorrido_em.isoformat()
    return {
        "title": f"{_STATUS_CRITICO} {titulo}",
        "description": mensagem_erro,
        "color": _EMBED_COR_ALTA,
        "footer": {"text": f"Timestamp: {iso}"},
        "timestamp": iso,
    }


def _montar_embed_novo_alerta(alerta: dict[str, Any]) -> dict[str, Any]:
    ocorrido_em = _timestamp_ocorrencia()
    iso = ocorrido_em.isoformat()
    tipo = str(alerta.get("tipo") or "")
    pncp_id = alerta.get("numero_controle_pncp")
    embed: dict[str, Any] = {
        "title": f"🔴 Novo alerta — {label_tipo(tipo)}",
        "description": _truncar(str(alerta.get("descricao") or ""), _MAX_DESCRICAO),
        "color": _EMBED_COR_ALTA,
        "timestamp": iso,
        "footer": {"text": f"Sentinela RJ · pipeline · {iso}"},
        "fields": [
            {
                "name": "Fornecedor",
                "value": _truncar(str(alerta.get("fornecedor") or "—"), 80),
                "inline": False,
            },
            {
                "name": "Valor",
                "value": _formatar_moeda(alerta.get("valor_referencia")),
                "inline": True,
            },
            {
                "name": "Score",
                "value": f"{float(alerta.get('score') or 0):.3f}",
                "inline": True,
            },
            {
                "name": "Status",
                "value": str(alerta.get("status") or "aberto"),
                "inline": True,
            },
        ],
    }
    if pncp_id:
        embed["url"] = _PNCP_URL.format(pncp_id=pncp_id)
    narrativa = str(alerta.get("narrativa_ia") or "").strip()
    if narrativa:
        embed["fields"].append({
            "name": "Laudo IA",
            "value": _truncar(narrativa, _MAX_NARRATIVA),
            "inline": False,
        })
    return embed


def _montar_embed_resumo(resumo: dict[str, Any]) -> dict[str, Any]:
    ocorrido_em = _timestamp_ocorrencia()
    iso = ocorrido_em.isoformat()
    linhas = [
        f"**Coleta:** {resumo.get('coletar', '—')}",
        f"**Enriquecer:** {resumo.get('enriquecer', '—')}",
        f"**Analisar:** {resumo.get('analisar', '—')}",
        f"**Investigar:** {resumo.get('investigar', '—')}",
        f"**Novos alertas alta:** {resumo.get('novos_alta', 0)}",
        f"**Duração:** {resumo.get('duracao_s', 0):.1f}s",
    ]
    erros = resumo.get("erros") or []
    if erros:
        linhas.append(f"**Avisos:** {len(erros)} etapa(s) com falha parcial")
    return {
        "title": "📊 Resumo do pipeline Sentinela RJ",
        "description": "\n".join(linhas),
        "color": _EMBED_COR_RESUMO,
        "timestamp": iso,
        "footer": {"text": f"Sentinela RJ · {iso}"},
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
        self._intervalo_s = _env_float("PIPELINE_DISCORD_INTERVALO_S", 1.0)

    def enviar_alerta_discord(self, titulo: str, mensagem_erro: str) -> None:
        embed = _montar_embed_erro(titulo.strip(), mensagem_erro.strip())
        payload = _montar_payload(embed)
        _enviar_webhook(self._webhook_url, payload)
        logger.info("Alerta Discord enviado: %s", titulo)

    def enviar_novo_alerta(self, alerta: dict[str, Any]) -> None:
        embed = _montar_embed_novo_alerta(alerta)
        _enviar_webhook(self._webhook_url, _montar_payload(embed))
        logger.info("Embed Discord enviado: alerta id=%s", alerta.get("id"))

    def enviar_novos_alertas(
        self,
        alertas: list[dict[str, Any]],
        *,
        max_embeds: int | None = None,
    ) -> int:
        limite = max_embeds or int(os.getenv("PIPELINE_DISCORD_MAX", "5"))
        enviados = 0
        for alerta in alertas[:limite]:
            self.enviar_novo_alerta(alerta)
            enviados += 1
            if enviados < min(len(alertas), limite):
                time.sleep(self._intervalo_s)
        return enviados

    def enviar_resumo_pipeline(self, resumo: dict[str, Any]) -> None:
        if os.getenv("PIPELINE_DISCORD_RESUMO", "true").strip().lower() in (
            "false",
            "0",
            "no",
        ):
            return
        embed = _montar_embed_resumo(resumo)
        _enviar_webhook(self._webhook_url, _montar_payload(embed))
        logger.info("Resumo do pipeline enviado ao Discord")
