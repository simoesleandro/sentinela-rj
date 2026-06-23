"""Integração com IA para narrativas investigativas de anomalias."""
from __future__ import annotations

import json
import logging
import os
import re
import warnings
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class ResultadoInvestigacao:
    corpo: str
    narrativa_ia: str  # corpo + veredito_gemini (formato atual)
    narrativa_gemma: str | None = None  # só veredito Gemma4
    veredito_gemini: dict[str, str] | None = None
    veredito_gemma: dict[str, str] | None = None
    gemini_utilizado: bool = False
    gemma4_utilizado: bool = False

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
_PROMPT_VEREDITO = (
    "Você é um auditor sênior de contratos públicos. "
    "Receberá o JSON factual da anomalia e a narrativa investigativa já gerada.\n\n"
    "Sua tarefa: APENAS gerar a recomendação de veredito.\n\n"
    "Responda SOMENTE com o bloco abaixo (copie o título exatamente):\n\n"
    "**[Recomendação de Veredito]**\n"
    "Status sugerido: <Aberto | Investigando | Confirmado | Descartado>\n"
    "Justificativa: 1 ou 2 linhas simples explicando por que esse status faz sentido.\n\n"
    "Use apenas um dos quatro status. "
    "Prefira Investigando quando houver indícios que exijam checagem; "
    "Confirmado só com evidências claras; "
    "Descartado quando a anomalia parecer explicável; "
    "Aberto se faltar contexto mínimo.\n"
    "Sem prefácio, sem repetir a narrativa, sem comentários adicionais."
)
_OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
_OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))
_GEMMA4_MODEL = os.environ.get("GEMMA4_MODEL", "gemma4:12b")
_GEMMA4_TIMEOUT = int(os.environ.get("GEMMA4_TIMEOUT", "180"))

_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


def _gemini_retryable(exc: Exception) -> bool:
    """True para erros de quota/sobrecarga que justificam tentar o próximo modelo."""
    msg = str(exc).lower()
    return any(kw in msg for kw in ("429", "503", "quota", "resource_exhausted", "unavailable", "overloaded"))


def _serializar_anomalia(anomalia: dict[str, Any]) -> str:
    return json.dumps(anomalia, ensure_ascii=False, default=str)


def _montar_prompt(anomalia: dict[str, Any]) -> str:
    return f"{_PROMPT_AUDITOR}\n\nDados da anomalia:\n{_serializar_anomalia(anomalia)}"


def _montar_prompt_veredito(
    anomalia: dict[str, Any],
    corpo: str,
    extra: str | None = None,
) -> str:
    prompt = _PROMPT_VEREDITO
    if extra:
        prompt = f"{prompt}\n\n{extra.strip()}"
    return (
        f"{prompt}\n\n"
        f"Dados factuais:\n{_serializar_anomalia(anomalia)}\n\n"
        f"Narrativa gerada:\n{corpo.strip()}"
    )


def _parse_veredito(texto: str) -> dict[str, str] | None:
    """Extrai status e justificativa do bloco de veredito."""
    if not texto or "[Recomendação de Veredito]" not in texto:
        return None
    status_match = re.search(
        r"Status sugerido:\s*(.+?)(?:\n|$)", texto, re.IGNORECASE
    )
    just_match = re.search(
        r"Justificativa:\s*(.+?)(?:\n\n|\Z)", texto, re.IGNORECASE | re.DOTALL
    )
    if not status_match:
        return None
    return {
        "status": status_match.group(1).strip(),
        "justificativa": just_match.group(1).strip() if just_match else "",
    }


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


def _revisao_gemma4_disponivel() -> bool:
    flag = os.environ.get("SENTINELA_IA_REVISAO_GEMMA4", "true").strip().lower()
    return flag in ("true", "1", "yes", "sim")


def _call_gemma4(prompt: str) -> str:
    """Chama Gemma 4 12B via Ollama para revisão alternativa."""
    url = f"{_OLLAMA_BASE}/api/chat"
    payload = {
        "model": _GEMMA4_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    try:
        resposta = requests.post(url, json=payload, timeout=_GEMMA4_TIMEOUT)
        resposta.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(
            f"Gemma 4 indisponível em {_OLLAMA_BASE} (modelo {_GEMMA4_MODEL}): {exc}"
        ) from exc
    dados = resposta.json()
    texto = (dados.get("message") or {}).get("content", "").strip()
    if not texto:
        raise ValueError("Resposta do Gemma 4 sem conteúdo textual.")
    return texto


def _limpar_latex(texto: str) -> str:
    """Remove artefatos LaTeX que vazam do Gemma 4."""
    texto = re.sub(r'\$([^$]+)\$', r'\1', texto)
    texto = texto.replace(r'\times', '×')
    texto = texto.replace(r'\%', '%')
    texto = texto.replace(r'\cdot', '·')
    texto = texto.replace(r'\approx', '≈')
    texto = re.sub(r'\\[a-zA-Z]+\{([^}]+)\}', r'\1', texto)
    return texto.strip()


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
        from google import genai
    except ImportError as exc:
        raise ValueError(
            "Pacote google-genai não instalado (pip install google-genai)."
        ) from exc

    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        raise ValueError("GEMINI_API_KEY não definida.")

    client = genai.Client(api_key=chave)
    last_exc: Exception | None = None
    for model in _GEMINI_MODELS:
        try:
            resposta = client.models.generate_content(model=model, contents=prompt)
            texto = (resposta.text or "").strip()
            if not texto:
                raise ValueError(f"Resposta do modelo {model} sem conteúdo textual.")
            if model != _GEMINI_MODELS[0]:
                logger.info("Gemini cascade: respondeu com %s", model)
            return texto
        except Exception as exc:
            if _gemini_retryable(exc):
                logger.warning("Gemini %s indisponível (%s) — tentando próximo modelo", model, exc)
                last_exc = exc
                continue
            raise
    raise ValueError(f"Todos os modelos Gemini falharam. Último erro: {last_exc}") from last_exc


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
    """Gera narrativas investigativas (Gemma4 corpo + vereditos A/B)."""

    def __init__(self, prompt_revisao_extra: str | None = None) -> None:
        self._prompt_revisao_extra = prompt_revisao_extra
        self._gemini_utilizado = False
        self._gemma4_utilizado = False

    @property
    def gemini_utilizado(self) -> bool:
        return self._gemini_utilizado

    @property
    def gemma4_utilizado(self) -> bool:
        return self._gemma4_utilizado

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

    def _revisar_com_gemma4(self, anomalia: dict[str, Any], rascunho: str) -> str:
        """Revisão alternativa usando Gemma 4 12B local."""
        prompt = _montar_prompt_revisao(
            anomalia, rascunho, extra=self._prompt_revisao_extra
        )
        revisado = _limpar_latex(_call_gemma4(prompt))
        logger.info(
            "Revisão Gemma 4 concluída (rascunho=%d chars, final=%d chars)",
            len(rascunho),
            len(revisado),
        )
        return revisado

    def _gerar_com_revisao_gemini(
        self, anomalia: dict[str, Any], prompt: str
    ) -> str:
        warnings.warn(
            "_gerar_com_revisao_gemini está obsoleto — use investigar_anomalia()",
            DeprecationWarning,
            stacklevel=2,
        )
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

    def investigar_anomalia(
        self, anomalia: dict[str, Any]
    ) -> ResultadoInvestigacao:
        self._gemini_utilizado = False
        self._gemma4_utilizado = False
        logger.info(
            "Investigando anomalia id=%s — fluxo: Gemma4 corpo + vereditos A/B",
            anomalia.get("id", "?"),
        )

        prompt_corpo = _montar_prompt(anomalia)
        if self._prompt_revisao_extra:
            prompt_corpo = f"{prompt_corpo}\n\n{self._prompt_revisao_extra}"

        try:
            corpo = _limpar_latex(_call_gemma4(prompt_corpo))
            logger.info("Corpo Gemma4 gerado (%d chars)", len(corpo))
        except ValueError as exc:
            logger.warning("Gemma4 falhou — fallback Gemini para corpo: %s", exc)
            try:
                corpo = _call_gemini(prompt_corpo)
                self._gemini_utilizado = True
            except ValueError as exc2:
                logger.warning("Gemini corpo falhou — fallback Groq: %s", exc2)
                corpo = _call_groq(prompt_corpo)

        veredito_gemma: str | None = None
        veredito_gemma_dict: dict[str, str] | None = None
        if _revisao_gemma4_disponivel():
            try:
                prompt_v = _montar_prompt_veredito(
                    anomalia, corpo, extra=self._prompt_revisao_extra
                )
                veredito_gemma = _limpar_latex(_call_gemma4(prompt_v))
                veredito_gemma_dict = _parse_veredito(veredito_gemma)
                self._gemma4_utilizado = True
                logger.info("Veredito Gemma4 gerado")
            except ValueError as exc:
                logger.warning("Veredito Gemma4 falhou: %s", exc)

        veredito_gemini: str | None = None
        veredito_gemini_dict: dict[str, str] | None = None
        if _revisao_gemini_disponivel():
            try:
                prompt_v = _montar_prompt_veredito(
                    anomalia, corpo, extra=self._prompt_revisao_extra
                )
                veredito_gemini = _call_gemini(prompt_v)
                veredito_gemini_dict = _parse_veredito(veredito_gemini)
                self._gemini_utilizado = True
                logger.info("Veredito Gemini gerado")
            except ValueError as exc:
                logger.warning("Veredito Gemini falhou: %s", exc)

        if veredito_gemini:
            narrativa_ia = f"{corpo}\n\n{veredito_gemini}"
        else:
            narrativa_ia = corpo

        logger.info(
            "Investigação concluída (%d chars narrativa_ia)", len(narrativa_ia)
        )

        return ResultadoInvestigacao(
            corpo=corpo,
            narrativa_ia=narrativa_ia,
            narrativa_gemma=veredito_gemma,
            veredito_gemini=veredito_gemini_dict,
            veredito_gemma=veredito_gemma_dict,
            gemini_utilizado=self._gemini_utilizado,
            gemma4_utilizado=self._gemma4_utilizado,
        )
