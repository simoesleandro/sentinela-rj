"""Integração com IA para narrativas investigativas de anomalias."""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
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
    narrativa_ia: str  # corpo + veredito primário
    narrativa_gemma: str | None = None  # texto bruto do veredito secundário (A/B)
    veredito_gemini: dict[str, str] | None = None  # veredito primário
    veredito_gemma: dict[str, str] | None = None  # veredito secundário (A/B)
    gemini_utilizado: bool = False
    gemma4_utilizado: bool = False
    provedor_primario: str | None = None  # ex.: "gemini", "groq", "gemma4"
    provedor_secundario: str | None = None

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


# ── Parecer único de triagem (reformulação jul/2026) ────────────────────────
# Uma só chamada de IA, domain-aware, que substitui o trio corpo + veredito +
# comparação A/B. Entrega plausibilidade + análise + status e MOTIVO sugeridos.
_PLAUSIBILIDADE_CANON = {
    "provável problema": "provavel_problema",
    "provavel problema": "provavel_problema",
    "provavelmente explicável": "provavel_explicavel",
    "provavelmente explicavel": "provavel_explicavel",
    "inconclusivo": "inconclusivo",
}
# Rótulos idênticos aos do frontend (MOTIVOS_DESCARTE em static/app.js).
_MOTIVO_DESCARTE_KEYS = {
    "rotineiro": "valor_rotineiro",
    "não se aplica": "categoria_diferente",
    "nao se aplica": "categoria_diferente",
    "categoria": "categoria_diferente",
    "insuficient": "dados_incompletos",
    "inconsistent": "dados_incompletos",
    "duplicad": "duplicado",
    "já investigado": "duplicado",
    "outro": "outro",
}

_PROMPT_PARECER = (
    "Você é um auditor sênior de contratos públicos do município do Rio de Janeiro. "
    "Receberá o JSON factual de um alerta de anomalia. Emita um parecer de triagem "
    "conciso e ORIENTADO PELO CONTEXTO: pondere a natureza do objeto, do órgão e do "
    "valor — um contrato alto pode ser rotineiro para o setor (energia, folha, "
    "merenda, concessão) e não constituir problema.\n\n"
    "Responda SOMENTE com o bloco abaixo, copiando os títulos exatamente:\n\n"
    "**[Parecer]**\n"
    "Plausibilidade: <Provável problema | Provavelmente explicável | Inconclusivo>\n"
    "Análise: <2 a 4 frases: nomeie o padrão, diga se o indício se sustenta e por quê, "
    "e oriente o próximo passo do auditor. Sem repetir o JSON, sem exageros jurídicos>\n"
    "Status sugerido: <Aberto | Investigando | Confirmado | Descartado>\n"
    "Motivo do descarte: <preencha SÓ se Descartado, com um de: "
    "'Valor rotineiro para a categoria', 'Categoria/objeto não se aplica ao detector', "
    "'Dados insuficientes ou inconsistentes', 'Alerta duplicado ou já investigado', "
    "'Outro motivo'; caso contrário escreva '—'>\n\n"
    "Coerência obrigatória:\n"
    "- 'Provavelmente explicável' -> Descartado; 'Provável problema' -> Investigando "
    "ou Confirmado (Confirmado só com evidência clara nos dados); 'Inconclusivo' -> "
    "Aberto ou Investigando.\n"
    "- Se a Análise recomenda CONFIRMAR, VERIFICAR, CHECAR ou INVESTIGAR algo antes "
    "de concluir (ou seja, há pendência), o Status NÃO pode ser Descartado — use "
    "Investigando. Descartar exige que o indício esteja explicado, sem pendências.\n"
    "- NÃO descarte um alerta só porque o contrato é de outro município: o Sentinela "
    "monitora vários municípios da região metropolitana do Rio, então ele está no "
    "escopo de fiscalização.\n"
    "Linguagem prudente — indício, não acusação."
)


def _montar_prompt_parecer(anomalia: dict[str, Any]) -> str:
    return f"{_PROMPT_PARECER}\n\nDados factuais da anomalia:\n{_serializar_anomalia(anomalia)}"


def _mapear_plausibilidade(txt: str) -> str:
    chave = (txt or "").strip().lower()
    for rotulo, canon in _PLAUSIBILIDADE_CANON.items():
        if rotulo in chave:
            return canon
    return "inconclusivo"


def _mapear_motivo(txt: str) -> str | None:
    chave = (txt or "").strip().lower()
    if not chave or chave in ("—", "-", "n/a", "nao se aplica"):
        return None
    for termo, key in _MOTIVO_DESCARTE_KEYS.items():
        if termo in chave:
            return key
    return None


# Pistas de que a análise ainda pede apuração — incompatíveis com "Descartado".
_PISTAS_INVESTIGACAO = (
    "proximo passo",
    "confirmar",
    "verificar",
    "checar",
    "investigar",
    "apurar",
    "esclarecer",
    "aprofundar",
    "assegurar que",
    "e preciso",
    "seria necessario",
)


def _pede_apuracao(analise: str) -> bool:
    """True se a análise recomenda uma checagem antes de concluir."""
    norm = (
        unicodedata.normalize("NFKD", analise or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return any(p in norm for p in _PISTAS_INVESTIGACAO)


def _parse_parecer(texto: str) -> dict[str, Any] | None:
    """Extrai plausibilidade, análise, status e motivo do bloco [Parecer]."""
    if not texto:
        return None
    plaus = re.search(r"Plausibilidade:\s*(.+?)(?:\n|$)", texto, re.IGNORECASE)
    analise = re.search(
        r"An[aá]lise:\s*(.+?)(?:\n\s*Status sugerido:|\Z)", texto, re.IGNORECASE | re.DOTALL
    )
    status = re.search(
        r"Status sugerido:\s*(Aberto|Investigando|Confirmado|Descartado)", texto, re.IGNORECASE
    )
    motivo = re.search(r"Motivo do descarte:\s*(.+?)(?:\n|$)", texto, re.IGNORECASE)
    if not status and not analise:
        return None
    status_val = status.group(1).lower() if status else "aberto"
    motivo_key = _mapear_motivo(motivo.group(1)) if (motivo and status_val == "descartado") else None
    return {
        "plausibilidade": _mapear_plausibilidade(plaus.group(1) if plaus else ""),
        "analise": analise.group(1).strip() if analise else "",
        "status_sugerido": status_val,
        "motivo_sugerido": motivo_key,
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


def _gemma4_habilitado() -> bool:
    """Gemma 4 (Ollama local) é OPT-IN — só usado se explicitamente ligado.

    Em produção (Fly) e na máquina de qualquer outra pessoa não há Ollama,
    então o padrão é desligado: o pipeline roda 100% em nuvem.
    """
    flag = os.environ.get("SENTINELA_IA_GEMMA4", "false").strip().lower()
    return flag in ("true", "1", "yes", "sim")


# Nomes de exibição dos provedores (para rótulos honestos no A/B do frontend).
NOMES_PROVEDOR = {
    "gemini": "Gemini 2.5 Flash",
    "groq": "Groq · Llama 3.3 70B",
    "gemma4": "Gemma 4 · local",
}


def _provedores_disponiveis() -> list[str]:
    """Ordem de preferência dos provedores de IA realmente disponíveis.

    Nuvem primeiro (Gemini, depois Groq). Gemma 4 local só entra se opt-in.
    ``SENTINELA_IA_PROVIDER`` pode forçar um provedor para o topo da fila.
    """
    provedores: list[str] = []
    if os.environ.get("GEMINI_API_KEY", "").strip():
        provedores.append("gemini")
    if os.environ.get("GROQ_API_KEY", "").strip():
        provedores.append("groq")
    if _gemma4_habilitado():
        provedores.append("gemma4")

    forcado = os.environ.get("SENTINELA_IA_PROVIDER", "").strip().lower()
    if forcado in provedores:
        provedores.remove(forcado)
        provedores.insert(0, forcado)
    return provedores


def _call_provedor(nome: str, prompt: str) -> str:
    if nome == "gemini":
        return _call_gemini(prompt)
    if nome == "groq":
        return _call_groq(prompt)
    if nome == "gemma4":
        return _limpar_latex(_call_gemma4(prompt))
    raise ValueError(f"Provedor de IA desconhecido: {nome}")


def gerar_texto(
    prompt: str, provedores: list[str] | None = None
) -> tuple[str, str]:
    """Gera texto tentando os provedores em ordem. Retorna (texto, provedor_usado).

    Lança ValueError se não houver provedor disponível ou se todos falharem.
    """
    provs = provedores if provedores is not None else _provedores_disponiveis()
    if not provs:
        raise ValueError(
            "Nenhum provedor de IA disponível. "
            "Configure GEMINI_API_KEY ou GROQ_API_KEY."
        )
    ultimo_erro: Exception | None = None
    for nome in provs:
        try:
            texto = _call_provedor(nome, prompt)
            if texto and texto.strip():
                return texto, nome
            ultimo_erro = ValueError(f"Provedor {nome} retornou resposta vazia.")
        except Exception as exc:
            logger.warning("Provedor de IA %s falhou: %s", nome, exc)
            ultimo_erro = exc
    raise ValueError(
        f"Todos os provedores de IA falharam. Último erro: {ultimo_erro}"
    )


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

    def emitir_parecer(self, anomalia: dict[str, Any]) -> dict[str, Any]:
        """Parecer único de triagem — uma chamada de IA, domain-aware.

        Substitui o trio corpo + veredito + comparação A/B. Retorna
        {plausibilidade, analise, status_sugerido, motivo_sugerido, provedor}.
        """
        provedores = _provedores_disponiveis()
        if not provedores:
            raise ValueError(
                "Nenhum provedor de IA disponível. "
                "Configure GEMINI_API_KEY ou GROQ_API_KEY."
            )
        prompt = _montar_prompt_parecer(anomalia)
        if self._prompt_revisao_extra:
            prompt = f"{prompt}\n\n{self._prompt_revisao_extra}"
        texto, provedor = gerar_texto(prompt, provedores)
        parecer = _parse_parecer(texto) or {
            "plausibilidade": "inconclusivo",
            "analise": _limpar_latex(texto).strip(),
            "status_sugerido": "aberto",
            "motivo_sugerido": None,
        }
        parecer["analise"] = _limpar_latex(parecer.get("analise") or "").strip()

        # Trava de coerência: um "Descartado" cuja análise ainda pede apuração é
        # contraditório (descartar = encerrado, sem pendências). Rebaixa para
        # Investigando e limpa o motivo, que só faz sentido em descarte.
        if parecer.get("status_sugerido") == "descartado" and _pede_apuracao(parecer["analise"]):
            parecer["status_sugerido"] = "investigando"
            parecer["motivo_sugerido"] = None
            if parecer.get("plausibilidade") == "provavel_explicavel":
                parecer["plausibilidade"] = "inconclusivo"

        parecer["provedor"] = provedor
        self._gemini_utilizado = provedor == "gemini"
        self._gemma4_utilizado = provedor == "gemma4"
        return parecer

    def investigar_anomalia(
        self, anomalia: dict[str, Any]
    ) -> ResultadoInvestigacao:
        self._gemini_utilizado = False
        self._gemma4_utilizado = False

        provedores = _provedores_disponiveis()
        if not provedores:
            raise ValueError(
                "Nenhum provedor de IA disponível. "
                "Configure GEMINI_API_KEY ou GROQ_API_KEY."
            )
        logger.info(
            "Investigando anomalia id=%s — provedores disponíveis: %s",
            anomalia.get("id", "?"),
            ", ".join(provedores),
        )

        # 1. Corpo da narrativa — cascata cloud-first com fallback real.
        prompt_corpo = _montar_prompt(anomalia)
        if self._prompt_revisao_extra:
            prompt_corpo = f"{prompt_corpo}\n\n{self._prompt_revisao_extra}"
        corpo, prov_corpo = gerar_texto(prompt_corpo, provedores)
        logger.info("Corpo gerado por %s (%d chars)", prov_corpo, len(corpo))

        prompt_v = _montar_prompt_veredito(
            anomalia, corpo, extra=self._prompt_revisao_extra
        )

        # 2. Veredito primário — mesmo provedor do corpo (coerência).
        veredito_primario_txt: str | None = None
        veredito_primario_dict: dict[str, str] | None = None
        usados: set[str] = {prov_corpo}
        try:
            veredito_primario_txt, _ = gerar_texto(prompt_v, [prov_corpo])
            veredito_primario_dict = _parse_veredito(veredito_primario_txt)
            logger.info("Veredito primário gerado por %s", prov_corpo)
        except ValueError as exc:
            logger.warning("Veredito primário (%s) falhou: %s", prov_corpo, exc)

        # 3. Veredito secundário — primeiro provedor diferente (A/B), se houver.
        prov_secundario = next((p for p in provedores if p != prov_corpo), None)
        veredito_sec_txt: str | None = None
        veredito_sec_dict: dict[str, str] | None = None
        if prov_secundario:
            try:
                veredito_sec_txt, _ = gerar_texto(prompt_v, [prov_secundario])
                veredito_sec_dict = _parse_veredito(veredito_sec_txt)
                usados.add(prov_secundario)
                logger.info("Veredito secundário gerado por %s", prov_secundario)
            except ValueError as exc:
                logger.warning(
                    "Veredito secundário (%s) falhou: %s", prov_secundario, exc
                )

        # A narrativa carrega o veredito primário; se ele falhar mas o
        # secundário existir, usa o secundário para não perder a recomendação.
        veredito_narrativa = veredito_primario_txt or veredito_sec_txt
        if veredito_narrativa:
            narrativa_ia = f"{corpo}\n\n{veredito_narrativa}"
        else:
            narrativa_ia = corpo

        self._gemini_utilizado = "gemini" in usados
        self._gemma4_utilizado = "gemma4" in usados
        logger.info(
            "Investigação concluída (%d chars narrativa_ia)", len(narrativa_ia)
        )

        return ResultadoInvestigacao(
            corpo=corpo,
            narrativa_ia=narrativa_ia,
            narrativa_gemma=veredito_sec_txt,
            veredito_gemini=veredito_primario_dict,
            veredito_gemma=veredito_sec_dict,
            gemini_utilizado=self._gemini_utilizado,
            gemma4_utilizado=self._gemma4_utilizado,
            provedor_primario=prov_corpo,
            provedor_secundario=prov_secundario if veredito_sec_dict else None,
        )
