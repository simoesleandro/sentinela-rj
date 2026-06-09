"""Integração com IA para narrativas investigativas de anomalias."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

_PROMPT_AUDITOR = (
    "Atue como um auditor investigativo. Escreva 1 parágrafo curto, "
    "direto e alarmante explicando por que este contrato é suspeito "
    "do ponto de vista de auditoria."
)
_OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
_OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))


def _serializar_anomalia(anomalia: dict[str, Any]) -> str:
    return json.dumps(anomalia, ensure_ascii=False, default=str)


def _montar_prompt(anomalia: dict[str, Any]) -> str:
    return f"{_PROMPT_AUDITOR}\n\nDados da anomalia:\n{_serializar_anomalia(anomalia)}"


def _call_ollama(prompt: str) -> str:
    url = f"{_OLLAMA_BASE}/api/chat"
    payload = {
        "model": _OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    try:
        resposta = requests.post(url, json=payload, timeout=_OLLAMA_TIMEOUT)
        resposta.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(
            f"Ollama indisponível em {_OLLAMA_BASE} (modelo {_OLLAMA_MODEL}): {exc}"
        ) from exc
    dados = resposta.json()
    texto = (dados.get("message") or {}).get("content", "").strip()
    if not texto:
        raise ValueError("Resposta do Ollama sem conteúdo textual.")
    return texto


def _call_gemini(prompt: str) -> str:
    import google.generativeai as genai

    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        raise ValueError("GEMINI_API_KEY não definida.")
    genai.configure(api_key=chave)
    modelo = genai.GenerativeModel("gemini-2.5-flash")
    resposta = modelo.generate_content(prompt)
    texto = (resposta.text or "").strip()
    if not texto:
        raise ValueError("Resposta da API Gemini sem conteúdo textual.")
    return texto


def _call_groq(prompt: str) -> str:
    import groq as groq_sdk

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY não definida.")
    client = groq_sdk.Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content.strip()


def _gerar_narrativa(prompt: str) -> str:
    provedor = os.environ.get("SENTINELA_IA_PROVIDER", "ollama").strip().lower()
    if provedor == "gemini":
        return _call_gemini(prompt)
    if provedor == "groq":
        return _call_groq(prompt)
    try:
        return _call_ollama(prompt)
    except ValueError as exc:
        if os.environ.get("GEMINI_API_KEY", "").strip():
            logger.warning("Ollama falhou — fallback Gemini: %s", exc)
            return _call_gemini(prompt)
        if os.environ.get("GROQ_API_KEY", "").strip():
            logger.warning("Ollama falhou — fallback Groq: %s", exc)
            return _call_groq(prompt)
        raise


class InvestigadorIA:
    """Gera narrativas investigativas (padrão: Ollama llama3.1 local)."""

    def __init__(self) -> None:
        pass

    def investigar_anomalia(self, anomalia: dict[str, Any]) -> str:
        logger.info(
            "Solicitando narrativa para anomalia id=%s (provider=%s)",
            anomalia.get("id", "?"),
            os.environ.get("SENTINELA_IA_PROVIDER", "ollama"),
        )
        prompt = _montar_prompt(anomalia)
        narrativa = _gerar_narrativa(prompt)
        logger.info("Narrativa gerada (%d caracteres)", len(narrativa))
        return narrativa
