"""Testes do motor de IA — pipeline cloud-first (Gemini/Groq) + A/B."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from analise.motor_ia import (
    InvestigadorIA,
    ResultadoInvestigacao,
    _limpar_latex,
    _parse_veredito,
    _provedores_disponiveis,
    _revisao_gemini_disponivel,
    gerar_texto,
)

_VEREDITO_GEMINI = (
    "**[Recomendação de Veredito]**\n"
    "Status sugerido: Investigando\n"
    "Justificativa: Valor acima do padrão; requer checagem documental."
)
_VEREDITO_GROQ = (
    "**[Recomendação de Veredito]**\n"
    "Status sugerido: Descartado\n"
    "Justificativa: Desvio explicável pelo contexto disponível."
)
_CORPO = (
    "Contrato com valor acima do padrão estatístico; fornecedor e órgão "
    "identificados nos dados."
)


@pytest.fixture
def anomalia() -> dict:
    return {
        "id": 1,
        "tipo": "outlier_valor",
        "severidade": "alta",
        "descricao": "Valor acima do padrão",
        "fornecedor": "Empresa Teste LTDA",
        "valor_referencia": 1_000_000.0,
    }


@pytest.fixture(autouse=True)
def _ambiente_limpo(monkeypatch: pytest.MonkeyPatch):
    """Cada teste parte de um ambiente sem chaves nem Gemma4 opt-in."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("SENTINELA_IA_GEMMA4", raising=False)
    monkeypatch.delenv("SENTINELA_IA_PROVIDER", raising=False)


# ── Helpers de flag/parse ──────────────────────────────────────────────────

def test_revisao_gemini_desligada_sem_chave(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _revisao_gemini_disponivel() is False


def test_revisao_gemini_ativa_com_chave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    assert _revisao_gemini_disponivel() is True


def test_revisao_gemini_respeita_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("SENTINELA_IA_REVISAO_GEMINI", "false")
    assert _revisao_gemini_disponivel() is False


def test_parse_veredito_valido() -> None:
    parsed = _parse_veredito(_VEREDITO_GEMINI)
    assert parsed is not None
    assert parsed["status"] == "Investigando"
    assert "checagem documental" in parsed["justificativa"]


def test_parse_veredito_invalido() -> None:
    assert _parse_veredito("") is None
    assert _parse_veredito("Texto sem marker") is None
    assert _parse_veredito("**[Recomendação de Veredito]**\nSem status") is None


def test_limpar_latex() -> None:
    texto = r"Valor de $1.000.000$ com \times 2 \approx 50\%"
    limpo = _limpar_latex(texto)
    assert "×" in limpo
    assert "≈" in limpo
    assert "50%" in limpo
    assert "$1.000.000$" not in limpo


# ── Resolução de provedores (cloud-first) ──────────────────────────────────

def test_provedores_vazio_sem_chaves() -> None:
    assert _provedores_disponiveis() == []


def test_provedores_ordem_nuvem(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert _provedores_disponiveis() == ["gemini", "groq"]


def test_gemma4_e_optin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert _provedores_disponiveis() == ["gemini"]  # sem flag, nada de local
    monkeypatch.setenv("SENTINELA_IA_GEMMA4", "true")
    assert _provedores_disponiveis() == ["gemini", "gemma4"]


def test_provedor_forcado_vai_pro_topo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("SENTINELA_IA_PROVIDER", "groq")
    assert _provedores_disponiveis() == ["groq", "gemini"]


# ── gerar_texto: cascata ───────────────────────────────────────────────────

def test_gerar_texto_sem_provedor_levanta() -> None:
    with pytest.raises(ValueError, match="Nenhum provedor"):
        gerar_texto("prompt")


def test_gerar_texto_cascata_fallback() -> None:
    with patch(
        "analise.motor_ia._call_gemini", side_effect=ValueError("429 quota")
    ), patch("analise.motor_ia._call_groq", return_value="ok groq"):
        texto, prov = gerar_texto("prompt", ["gemini", "groq"])
    assert texto == "ok groq"
    assert prov == "groq"


# ── investigar_anomalia: cloud-first ───────────────────────────────────────

def test_investigar_sem_provedor_levanta(anomalia: dict) -> None:
    with pytest.raises(ValueError, match="Nenhum provedor"):
        InvestigadorIA().investigar_anomalia(anomalia)


def test_investigar_apenas_gemini(
    monkeypatch: pytest.MonkeyPatch, anomalia: dict
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    with patch(
        "analise.motor_ia._call_gemini", side_effect=[_CORPO, _VEREDITO_GEMINI]
    ) as mock_gemini:
        resultado = InvestigadorIA().investigar_anomalia(anomalia)

    assert isinstance(resultado, ResultadoInvestigacao)
    assert resultado.corpo == _CORPO
    assert resultado.narrativa_ia.startswith(_CORPO)
    assert "[Recomendação de Veredito]" in resultado.narrativa_ia
    assert resultado.veredito_gemini["status"] == "Investigando"
    assert resultado.veredito_gemma is None  # sem segundo provedor
    assert resultado.provedor_primario == "gemini"
    assert resultado.provedor_secundario is None
    assert resultado.gemini_utilizado is True
    assert mock_gemini.call_count == 2  # corpo + veredito


def test_investigar_ab_gemini_vs_groq(
    monkeypatch: pytest.MonkeyPatch, anomalia: dict
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")
    with patch(
        "analise.motor_ia._call_gemini", side_effect=[_CORPO, _VEREDITO_GEMINI]
    ) as mock_gemini, patch(
        "analise.motor_ia._call_groq", return_value=_VEREDITO_GROQ
    ) as mock_groq:
        resultado = InvestigadorIA().investigar_anomalia(anomalia)

    assert resultado.corpo == _CORPO
    assert resultado.provedor_primario == "gemini"
    assert resultado.provedor_secundario == "groq"
    assert resultado.veredito_gemini["status"] == "Investigando"
    assert resultado.veredito_gemma["status"] == "Descartado"
    assert resultado.narrativa_gemma == _VEREDITO_GROQ
    assert mock_gemini.call_count == 2  # corpo + veredito primário
    mock_groq.assert_called_once()  # veredito secundário


def test_investigar_corpo_cai_para_groq(
    monkeypatch: pytest.MonkeyPatch, anomalia: dict
) -> None:
    """Gemini fora do ar: corpo e veredito vêm do Groq; sem secundário válido."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")
    with patch(
        "analise.motor_ia._call_gemini", side_effect=ValueError("503 unavailable")
    ), patch(
        "analise.motor_ia._call_groq", side_effect=[_CORPO, _VEREDITO_GROQ]
    ):
        resultado = InvestigadorIA().investigar_anomalia(anomalia)

    assert resultado.corpo == _CORPO
    assert resultado.provedor_primario == "groq"
    assert resultado.veredito_gemini["status"] == "Descartado"
    # secundário seria gemini, que está fora → fica vazio
    assert resultado.veredito_gemma is None
    assert resultado.provedor_secundario is None


def test_veredito_primario_falha_retorna_somente_corpo(
    monkeypatch: pytest.MonkeyPatch, anomalia: dict
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    # corpo ok, veredito falha
    with patch(
        "analise.motor_ia._call_gemini",
        side_effect=[_CORPO, ValueError("Gemini indisponível")],
    ):
        resultado = InvestigadorIA().investigar_anomalia(anomalia)

    assert resultado.narrativa_ia == _CORPO
    assert resultado.veredito_gemini is None


def test_pipeline_prompt_extra_incluido_no_veredito(
    monkeypatch: pytest.MonkeyPatch, anomalia: dict
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    extra = "MODO LOTE — seja direto"
    with patch(
        "analise.motor_ia._call_gemini", side_effect=[_CORPO, _VEREDITO_GEMINI]
    ) as mock_gemini:
        InvestigadorIA(prompt_revisao_extra=extra).investigar_anomalia(anomalia)

    prompt_veredito = mock_gemini.call_args_list[1][0][0]
    assert extra in prompt_veredito
    assert "APENAS gerar a recomendação de veredito" in prompt_veredito
    assert _CORPO in prompt_veredito
