"""Testes do motor de IA — Gemma4 corpo + vereditos A/B."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from analise.motor_ia import (
    InvestigadorIA,
    ResultadoInvestigacao,
    _limpar_latex,
    _parse_veredito,
    _revisao_gemini_disponivel,
)

_VEREDITO_GEMINI = (
    "**[Recomendação de Veredito]**\n"
    "Status sugerido: Investigando\n"
    "Justificativa: Valor acima do padrão; requer checagem documental."
)
_VEREDITO_GEMMA = (
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


def test_revisao_gemini_desligada_sem_chave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
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


def test_investigar_fluxo_gemma4_corpo_vereditos_ab(
    monkeypatch: pytest.MonkeyPatch,
    anomalia: dict,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _gemma_side_effect(prompt: str) -> str:
        if "APENAS gerar a recomendação de veredito" in prompt:
            return _VEREDITO_GEMMA
        return _CORPO

    with patch(
        "analise.motor_ia._call_gemma4", side_effect=_gemma_side_effect
    ) as mock_gemma, patch(
        "analise.motor_ia._call_gemini", return_value=_VEREDITO_GEMINI
    ) as mock_gemini:
        resultado = InvestigadorIA().investigar_anomalia(anomalia)

    assert isinstance(resultado, ResultadoInvestigacao)
    assert resultado.corpo == _CORPO
    assert "[Recomendação de Veredito]" in resultado.narrativa_ia
    assert resultado.narrativa_ia.startswith(_CORPO)
    assert resultado.narrativa_gemma == _VEREDITO_GEMMA
    assert resultado.veredito_gemini["status"] == "Investigando"
    assert resultado.veredito_gemma["status"] == "Descartado"
    assert resultado.gemini_utilizado is True
    assert resultado.gemma4_utilizado is True
    assert mock_gemma.call_count == 2
    mock_gemini.assert_called_once()
    prompt_veredito = mock_gemini.call_args[0][0]
    assert "APENAS gerar a recomendação de veredito" in prompt_veredito
    assert _CORPO in prompt_veredito


def test_investigar_sem_chave_somente_corpo_gemma4(
    monkeypatch: pytest.MonkeyPatch,
    anomalia: dict,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("SENTINELA_IA_REVISAO_GEMMA4", "false")

    with patch("analise.motor_ia._call_gemma4", return_value=_CORPO) as mock_gemma:
        resultado = InvestigadorIA().investigar_anomalia(anomalia)

    assert resultado.narrativa_ia == _CORPO
    assert resultado.narrativa_gemma is None
    assert resultado.gemini_utilizado is False
    mock_gemma.assert_called_once()


def test_veredito_gemini_falha_retorna_somente_corpo(
    monkeypatch: pytest.MonkeyPatch,
    anomalia: dict,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    with patch("analise.motor_ia._call_gemma4", return_value=_CORPO), patch(
        "analise.motor_ia._call_gemini",
        side_effect=ValueError("Gemini indisponível"),
    ):
        resultado = InvestigadorIA().investigar_anomalia(anomalia)

    assert resultado.narrativa_ia == _CORPO
    assert resultado.veredito_gemini is None


def test_gemma4_corpo_falha_fallback_gemini(
    monkeypatch: pytest.MonkeyPatch,
    anomalia: dict,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _gemma_side_effect(prompt: str) -> str:
        if "APENAS gerar a recomendação de veredito" in prompt:
            return _VEREDITO_GEMMA
        raise ValueError("Gemma4 indisponível")

    with patch("analise.motor_ia._call_gemma4", side_effect=_gemma_side_effect), patch(
        "analise.motor_ia._call_gemini", side_effect=[_CORPO, _VEREDITO_GEMINI]
    ) as mock_gemini:
        resultado = InvestigadorIA().investigar_anomalia(anomalia)

    assert resultado.corpo == _CORPO
    assert "[Recomendação de Veredito]" in resultado.narrativa_ia
    assert mock_gemini.call_count == 2


def test_pipeline_prompt_extra_incluido_no_veredito(
    monkeypatch: pytest.MonkeyPatch,
    anomalia: dict,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    extra = "MODO LOTE — seja direto"

    with patch("analise.motor_ia._call_gemma4", return_value=_CORPO), patch(
        "analise.motor_ia._call_gemini", return_value=_VEREDITO_GEMINI
    ) as mock_gemini:
        InvestigadorIA(prompt_revisao_extra=extra).investigar_anomalia(anomalia)

    prompt_veredito = mock_gemini.call_args[0][0]
    assert extra in prompt_veredito
    assert "APENAS gerar a recomendação de veredito" in prompt_veredito
