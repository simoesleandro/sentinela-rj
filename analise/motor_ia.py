"""Integração com IA para narrativas investigativas de anomalias."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_PROMPT_AUDITOR = (
    "Atue como um auditor investigativo. Seja direto: nas primeiras frases, "
    "identifique o padrão do alerta (tipo, fornecedor/órgão, valor e risco). "
    "Escreva 1 parágrafo curto, sem introduções nem repetição dos campos do JSON. "
    "Use apenas os dados fornecidos."
)
_PROMPT_REVISAO_GEMINI = (
    "Você é um revisor sênior de auditoria de contratos públicos. "
    "Receberá o JSON factual da anomalia e um rascunho gerado por um modelo local.\n\n"
    "Sua tarefa: reescrever o rascunho corrigindo erros, sem acrescentar fatos novos, "
    "e orientar o auditor humano (Leandro) sobre o próximo passo na triagem.\n\n"
    "ESTILO (obrigatório):\n"
    "- Seja direto: nas 2 primeiras frases, nomeie o padrão do alerta "
    "(tipo de anomalia, ator principal, valor e por que chama atenção).\n"
    "- Corpo enxuto (máximo 4–6 frases); sem prefácios, sem repetir o JSON, "
    "sem enrolação ou conclusões genéricas.\n\n"
    "REGRAS OBRIGATÓRIAS:\n"
    "1. Remova ou corrija erros contextuais (órgãos, fornecedores, valores, datas).\n"
    "2. Remova exageros jurídicos ou acusações não sustentadas pelos dados "
    "(ex.: evasão fiscal, fraude, crime, lavagem) — use linguagem prudente.\n"
    "3. Não invente nomes, CNPJs, valores, leis ou conclusas não presentes no JSON.\n"
    "4. Tom investigativo, neutro e factual, em português.\n"
    "5. Ao final, inclua SEMPRE a seção abaixo (copie o título exatamente):\n\n"
    "**[Recomendação de Veredito]**\n"
    "Status sugerido: <Aberto | Investigando | Confirmado | Descartado>\n"
    "Justificativa: 1 ou 2 linhas simples explicando por que esse status faz sentido "
    "com base nos fatos e dados da anomalia (severidade, tipo, valor, contexto).\n\n"
    "Use apenas um dos quatro status listados. "
    "Prefira Investigando quando houver indícios que exijam checagem; "
    "Confirmado só com evidências claras nos dados; "
    "Descartado quando a anomalia parecer explicável ou fraca; "
    "Aberto apenas se ainda faltar contexto mínimo para decidir.\n"
    "6. Responda com o parágrafo revisado seguido da seção de veredito — "
    "sem prefácio, sem repetir o JSON."
)
_OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
_OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))


def _serializar_anomalia(anomalia: dict[str, Any]) -> str:
    return json.dumps(anomalia, ensure_ascii=False, default=str)


def _montar_prompt(anomalia: dict[str, Any]) -> str:
    return f"{_PROMPT_AUDITOR}\n\nDados da anomalia:\n{_serializar_anomalia(anomalia)}"


def _montar_prompt_revisao(
    anomalia: dict[str, Any],
    rascunho: str,
    extra: str | None = None,
) -> str:
    prompt_base = _PROMPT_REVISAO_GEMINI
    if extra:
        prompt_base = f"{prompt_base}\n\n{extra.strip()}"
    return (
        f"{prompt_base}\n\n"
        f"Dados factuais (fonte de verdade):\n{_serializar_anomalia(anomalia)}\n\n"
        f"Rascunho a revisar:\n{rascunho.strip()}"
    )


def _revisao_gemini_disponivel() -> bool:
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        return False
    flag = os.environ.get("SENTINELA_IA_REVISAO_GEMINI", "true").strip().lower()
    return flag in ("true", "1", "yes", "sim")


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
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise ValueError(
            "Pacote google-generativeai não instalado (pip install google-generativeai)."
        ) from exc

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


def _gerar_narrativa_com_rastreio(prompt: str) -> tuple[str, bool]:
    provedor = os.environ.get("SENTINELA_IA_PROVIDER", "ollama").strip().lower()
    if provedor == "gemini":
        return _call_gemini(prompt), True
    if provedor == "groq":
        return _call_groq(prompt), False
    try:
        return _call_ollama(prompt), False
    except ValueError as exc:
        if os.environ.get("GEMINI_API_KEY", "").strip():
            logger.warning("Ollama falhou — fallback Gemini: %s", exc)
            return _call_gemini(prompt), True
        if os.environ.get("GROQ_API_KEY", "").strip():
            logger.warning("Ollama falhou — fallback Groq: %s", exc)
            return _call_groq(prompt), False
        raise


class InvestigadorIA:
    """Gera narrativas investigativas (Ollama + revisão opcional Gemini)."""

    def __init__(self, prompt_revisao_extra: str | None = None) -> None:
        self._prompt_revisao_extra = prompt_revisao_extra
        self._gemini_utilizado = False

    @property
    def gemini_utilizado(self) -> bool:
        return self._gemini_utilizado

    def _revisar_com_gemini(self, anomalia: dict[str, Any], rascunho: str) -> str:
        prompt = _montar_prompt_revisao(
            anomalia, rascunho, extra=self._prompt_revisao_extra
        )
        revisado = _call_gemini(prompt)
        logger.info(
            "Revisão Gemini concluída (rascunho=%d chars, final=%d chars)",
            len(rascunho),
            len(revisado),
        )
        return revisado

    def _gerar_com_revisao_gemini(
        self, anomalia: dict[str, Any], prompt: str
    ) -> str:
        try:
            rascunho = _call_ollama(prompt)
        except ValueError as exc:
            logger.warning(
                "Rascunho Ollama indisponível — revisão Gemini ignorada: %s", exc
            )
            narrativa, usou_gemini = _gerar_narrativa_com_rastreio(prompt)
            self._gemini_utilizado = usou_gemini
            return narrativa
        try:
            revisado = self._revisar_com_gemini(anomalia, rascunho)
            self._gemini_utilizado = True
            return revisado
        except ValueError as exc:
            logger.warning("Revisão Gemini falhou — usando rascunho Ollama: %s", exc)
            self._gemini_utilizado = False
            return rascunho

    def investigar_anomalia(self, anomalia: dict[str, Any]) -> str:
        self._gemini_utilizado = False
        logger.info(
            "Solicitando narrativa para anomalia id=%s (provider=%s, revisao_gemini=%s)",
            anomalia.get("id", "?"),
            os.environ.get("SENTINELA_IA_PROVIDER", "ollama"),
            _revisao_gemini_disponivel(),
        )
        prompt = _montar_prompt(anomalia)
        if _revisao_gemini_disponivel():
            narrativa = self._gerar_com_revisao_gemini(anomalia, prompt)
        else:
            narrativa, usou_gemini = _gerar_narrativa_com_rastreio(prompt)
            self._gemini_utilizado = usou_gemini
        logger.info("Narrativa final (%d caracteres)", len(narrativa))
        return narrativa
