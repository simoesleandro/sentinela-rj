"""Testes do motor de IA — revisão Gemini pós-Ollama."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from analise.motor_ia import InvestigadorIA, _revisao_gemini_disponivel


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


def test_investigar_aplica_revisao_gemini(
    monkeypatch: pytest.MonkeyPatch,
    anomalia: dict,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    rascunho = "Suspeita de evasão fiscal e fraude no órgão errado."
    revisado = "Contrato com valor acima do padrão estatístico; merece verificação."

    with patch("analise.motor_ia._call_ollama", return_value=rascunho) as mock_ollama, patch(
        "analise.motor_ia._call_gemini", return_value=revisado
    ) as mock_gemini:
        texto = InvestigadorIA().investigar_anomalia(anomalia)

    assert texto == revisado
    mock_ollama.assert_called_once()
    mock_gemini.assert_called_once()
    prompt_revisao = mock_gemini.call_args[0][0]
    assert "evasão fiscal" in prompt_revisao
    assert "Dados factuais" in prompt_revisao


def test_investigar_sem_chave_usa_fluxo_simples(
    monkeypatch: pytest.MonkeyPatch,
    anomalia: dict,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with patch("analise.motor_ia._gerar_narrativa", return_value="Narrativa direta") as mock_gen:
        texto = InvestigadorIA().investigar_anomalia(anomalia)

    assert texto == "Narrativa direta"
    mock_gen.assert_called_once()


def test_revisao_falha_retorna_rascunho(
    monkeypatch: pytest.MonkeyPatch,
    anomalia: dict,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    rascunho = "Rascunho Llama preservado."

    with patch("analise.motor_ia._call_ollama", return_value=rascunho), patch(
        "analise.motor_ia._call_gemini",
        side_effect=ValueError("Gemini indisponível"),
    ):
        texto = InvestigadorIA().investigar_anomalia(anomalia)

    assert texto == rascunho
