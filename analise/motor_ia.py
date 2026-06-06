"""Integração com IA para narrativas investigativas de anomalias."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import google.generativeai as genai
import groq as groq_sdk

logger = logging.getLogger(__name__)

_MODELO = "gemini-2.5-flash"
_PROMPT_AUDITOR = (
    "Atue como um auditor investigativo. Escreva 1 parágrafo curto, "
    "direto e alarmante explicando por que este contrato é suspeito "
    "do ponto de vista de auditoria."
)


def _require_api_key() -> str:
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        raise ValueError("GEMINI_API_KEY não definida.")
    return chave


def _serializar_anomalia(anomalia: dict[str, Any]) -> str:
    return json.dumps(anomalia, ensure_ascii=False, default=str)


def _montar_prompt(anomalia: dict[str, Any]) -> str:
    return f"{_PROMPT_AUDITOR}\n\nDados da anomalia:\n{_serializar_anomalia(anomalia)}"


def _call_groq(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY não definida.")
    client = groq_sdk.Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content.strip()


def _extrair_texto_resposta(resposta: genai.types.GenerateContentResponse) -> str:
    texto = (resposta.text or "").strip()
    if not texto:
        raise ValueError("Resposta da API Gemini sem conteúdo textual.")
    return texto


class InvestigadorIA:
    """Gera narrativas investigativas via API Google Gemini."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key or _require_api_key()).strip()
        genai.configure(api_key=self.api_key)
        self._model = genai.GenerativeModel(_MODELO)

    def _gerar_narrativa(self, prompt: str) -> str:
        try:
            resposta = self._model.generate_content(prompt)
            return _extrair_texto_resposta(resposta)
        except Exception as exc:
            logger.error("Falha na API Gemini: %s", exc)
            raise

    def investigar_anomalia(self, anomalia: dict[str, Any]) -> str:
        logger.info(
            "Solicitando narrativa para anomalia id=%s",
            anomalia.get("id", "?"),
        )
        prompt = _montar_prompt(anomalia)
        try:
            narrativa = self._gerar_narrativa(prompt)
        except Exception as exc:
            if "429" in str(exc):
                logger.warning("Gemini 429 — usando Groq como fallback.")
                try:
                    narrativa = _call_groq(prompt)
                except Exception:
                    raise exc
            else:
                raise
        logger.info("Narrativa gerada (%d caracteres)", len(narrativa))
        return narrativa
