"""Testes unitários do cliente de API de despesas."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import requests
import responses

from extrator.api_client import SentinelaAPI


@pytest.fixture
def raw_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    diretorio = tmp_path / "raw"
    monkeypatch.setenv("DATA_RAW_DIR", str(diretorio))
    monkeypatch.setenv("SENTINELA_API_BASE_URL", "https://api.test.local")
    monkeypatch.setenv("SENTINELA_API_DESPESAS_PATH", "/despesas")
    return diretorio


@responses.activate
def test_buscar_despesas_sucesso(raw_dir: Path) -> None:
    payload: dict[str, Any] = {"despesas": [{"valor": 100.0, "orgao_id": "org-1"}]}
    responses.add(
        responses.GET,
        re.compile(r"https://api\.test\.local/despesas"),
        json=payload,
        status=200,
    )

    api = SentinelaAPI()
    resultado = api.buscar_despesas("org-1", "20260101", "20260131")

    assert resultado == payload
    arquivo = raw_dir / "despesas_org-1_20260101_20260131.json"
    assert arquivo.is_file()
    with arquivo.open(encoding="utf-8") as handle:
        assert json.load(handle) == payload


def test_buscar_despesas_timeout(
    raw_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = SentinelaAPI()

    with caplog.at_level(logging.ERROR, logger="extrator.api_client"):
        with patch(
            "extrator.api_client.requests.get",
            side_effect=requests.Timeout("timed out"),
        ):
            resultado = api.buscar_despesas("org-1", "20260101", "20260131")

    assert resultado is None
    assert len(caplog.records) == 1
    registro = caplog.records[0]
    assert registro.levelno == logging.ERROR
    assert "Falha de conexão ao buscar despesas" in registro.getMessage()
    assert "org-1" in registro.getMessage()
    assert not list(raw_dir.glob("*.json"))
