"""Testes de coleta multi-município."""
from __future__ import annotations

import pytest

from extrator.config_municipio import (
    MunicipioMonitorado,
    municipios_monitorados,
    rotulo_filtro,
)


def test_padrao_rm_rj_tem_rio_primeiro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUNICIPIOS_MONITORADOS", raising=False)
    alvos = municipios_monitorados()
    assert alvos[0].ibge == "3304557"
    assert alvos[0].nome == "Rio de Janeiro"
    assert len(alvos) >= 8


def test_parse_municipios_monitorados_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MUNICIPIOS_MONITORADOS",
        "3304557:Rio de Janeiro,3303302:Niterói",
    )
    alvos = municipios_monitorados()
    assert len(alvos) == 2
    assert alvos[0].ibge == "3304557"


def test_rotulo_multiplos_municipios(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUNICIPIOS_MONITORADOS", raising=False)
    rotulo = rotulo_filtro()
    assert "municípios" in rotulo


def test_pncp_resolver_alvo() -> None:
    from extrator.pncp import _resolver_alvo

    alvos = [
        MunicipioMonitorado(ibge="3304557", nome="Rio de Janeiro"),
        MunicipioMonitorado(ibge="3303302", nome="Niterói"),
    ]
    registro_rj = {
        "unidadeOrgao": {"codigoIbge": "3304557"},
        "orgaoEntidade": {"esferaId": "M"},
    }
    registro_sp = {
        "unidadeOrgao": {"codigoIbge": "3550308"},
        "orgaoEntidade": {"esferaId": "M"},
    }
    assert _resolver_alvo(registro_rj, alvos) is not None
    assert _resolver_alvo(registro_sp, alvos) is None
