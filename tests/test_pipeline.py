"""Testes do pipeline agendado Sentinela RJ."""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from analisador.engine import AnomaliaResult
from automacoes.pipeline import (
    EtapaResult,
    PipelineConfig,
    executar_pipeline,
)
from automacoes.utils.notificador import NotificadorAlertas
from db.alertas_sync import sincronizar_alertas


@pytest.fixture
def conn() -> sqlite3.Connection:
    from db.conexao import SCHEMA_PATH, aplicar_migracoes

    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    conexao.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conexao)
    return conexao


def test_notificador_embed_novo_alerta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")
    enviados: list[dict] = []

    def _fake_post(url: str, json: dict, timeout: int) -> MagicMock:
        enviados.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    monkeypatch.setattr(
        "automacoes.utils.notificador.requests.post",
        _fake_post,
    )
    notificador = NotificadorAlertas()
    notificador.enviar_novo_alerta({
        "id": 1,
        "tipo": "outlier_valor",
        "descricao": "Valor atipico detectado",
        "valor_referencia": 1_000_000.0,
        "score": 0.91,
        "status": "aberto",
        "fornecedor": "Empresa Teste LTDA",
        "numero_controle_pncp": "PNCP-001",
    })
    assert enviados
    embed = enviados[0]["embeds"][0]
    assert "Novo alerta" in embed["title"]
    assert embed["url"] == "https://pncp.gov.br/app/contratos/PNCP-001"


def test_sync_retorna_ids_inseridos_alta(conn) -> None:
    anomalias = [
        AnomaliaResult(
            tipo="outlier_valor",
            severidade="alta",
            score=0.9,
            titulo="Alta",
            descricao="desc",
            metodologia="IQR",
            contratos=["PNCP-A"],
        ),
        AnomaliaResult(
            tipo="sem_licitacao_dispensa",
            severidade="media",
            score=0.5,
            titulo="Media",
            descricao="desc",
            metodologia="regex",
            contratos=["PNCP-B"],
        ),
    ]
    resumo = sincronizar_alertas(conn, anomalias)
    assert len(resumo["ids_inseridos"]) == 2
    assert len(resumo["ids_inseridos_alta"]) == 1


def test_pipeline_ordem_etapas(monkeypatch: pytest.MonkeyPatch) -> None:
    ordem: list[str] = []
    config = PipelineConfig(
        skip_enriquecer=True,
        skip_investigar=True,
        skip_notificar=True,
    )

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "")

    def _coletar(_cfg: PipelineConfig) -> EtapaResult:
        ordem.append("coletar")
        return EtapaResult(True, "ok")

    def _enriquecer(_cfg: PipelineConfig) -> EtapaResult:
        ordem.append("enriquecer")
        return EtapaResult(True, "ok")

    def _analisar(_cfg: PipelineConfig) -> tuple[EtapaResult, list]:
        ordem.append("analisar")
        return EtapaResult(True, "ok"), []

    def _investigar(_cfg: PipelineConfig) -> EtapaResult:
        ordem.append("investigar")
        return EtapaResult(True, "ok")

    def _notificar(_cfg, _novos, _resumo) -> EtapaResult:
        ordem.append("notificar")
        return EtapaResult(True, "ok")

    with patch("automacoes.pipeline._etapa_coletar", _coletar), patch(
        "automacoes.pipeline._etapa_enriquecer", _enriquecer
    ), patch("automacoes.pipeline._etapa_analisar", _analisar), patch(
        "automacoes.pipeline._etapa_investigar", _investigar
    ), patch("automacoes.pipeline._etapa_notificar", _notificar):
        resultado = executar_pipeline(config)

    assert ordem == ["coletar", "enriquecer", "analisar", "investigar", "notificar"]
    assert resultado.sucesso


def test_pipeline_fail_soft_enriquecer(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PipelineConfig(skip_investigar=True, skip_notificar=True)

    with patch(
        "automacoes.pipeline._etapa_coletar",
        return_value=EtapaResult(True, "ok"),
    ), patch(
        "automacoes.pipeline._etapa_enriquecer",
        return_value=EtapaResult(False, "falhou", erro="api"),
    ), patch(
        "automacoes.pipeline._etapa_analisar",
        return_value=(EtapaResult(True, "ok"), []),
    ), patch(
        "automacoes.pipeline._etapa_investigar",
        return_value=EtapaResult(True, "ok"),
    ), patch(
        "automacoes.pipeline._etapa_notificar",
        return_value=EtapaResult(True, "ok"),
    ):
        resultado = executar_pipeline(config)

    assert resultado.sucesso
    assert any("enriquecer" in e for e in resultado.erros)


def test_notificar_respeita_limite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")
    chamadas = 0

    def _fake_post(url: str, json: dict, timeout: int) -> MagicMock:
        nonlocal chamadas
        chamadas += 1
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    monkeypatch.setattr(
        "automacoes.utils.notificador.requests.post",
        _fake_post,
    )
    alertas = [{"id": i, "tipo": "outlier_valor", "descricao": "x"} for i in range(10)]
    notificador = NotificadorAlertas()
    enviados = notificador.enviar_novos_alertas(alertas, max_embeds=3)
    assert enviados == 3
    assert chamadas == 3
