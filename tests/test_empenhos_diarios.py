"""Testes para extrator/empenhos_diarios.py."""
from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from extrator.empenhos_diarios import (
    _fornecedores_monitorados,
    _salvar_lancamento,
    coletar_empenhos_novos,
    coletar_empenhos_retroativo,
)


def _make_conn() -> sqlite3.Connection:
    from db.conexao import SCHEMA_PATH, aplicar_migracoes

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conn)
    return conn


def _contrato(
    ni: str = "12345678000100",
    numero: str = "PNCP-001",
    valor: float = 100_000.0,
    data: str = "2026-06-14",
) -> dict[str, Any]:
    return {
        "niFornecedor": ni,
        "valorGlobal": valor,
        "dataPublicacaoPncp": data,
        "objetoContrato": "Fornecimento de materiais",
        "orgaoEntidade": {"cnpj": "42498733000148"},
        "numeroControlePNCP": numero,
    }


@pytest.fixture
def conn_com_fornecedor():
    conn = _make_conn()
    conn.execute(
        "INSERT INTO fornecedores (ni, tipo_pessoa, razao_social) VALUES (?, ?, ?)",
        ("12345678000100", "PJ", "Empresa Monitorada LTDA"),
    )
    conn.commit()
    return conn


# ──────────────────────────── unit ────────────────────────────


def test_fornecedores_monitorados_retorna_set(conn_com_fornecedor):
    monitorados = _fornecedores_monitorados(conn_com_fornecedor)
    assert isinstance(monitorados, set)
    assert "12345678000100" in monitorados


def test_fornecedores_monitorados_vazio():
    conn = _make_conn()
    assert _fornecedores_monitorados(conn) == set()


def test_salvar_lancamento_novo(conn_com_fornecedor):
    salvo = _salvar_lancamento(conn_com_fornecedor, _contrato())
    assert salvo is True
    row = conn_com_fornecedor.execute(
        "SELECT * FROM transparencia_rj_lancamentos"
    ).fetchone()
    assert row is not None


def test_salvar_lancamento_campos(conn_com_fornecedor):
    conn_com_fornecedor.row_factory = sqlite3.Row
    _salvar_lancamento(conn_com_fornecedor, _contrato(ni="12345678000100", numero="PNCP-X", valor=50_000.0))
    row = conn_com_fornecedor.execute(
        "SELECT * FROM transparencia_rj_lancamentos WHERE documento = 'PNCP-X'"
    ).fetchone()
    assert row["fornecedor_ni"] == "12345678000100"
    assert row["valor"] == 50_000.0
    assert row["orgao"] == "42498733000148"
    assert row["documento"] == "PNCP-X"


def test_salvar_lancamento_duplicado_ignorado(conn_com_fornecedor):
    d = _contrato()
    _salvar_lancamento(conn_com_fornecedor, d)
    conn_com_fornecedor.commit()
    segundo = _salvar_lancamento(conn_com_fornecedor, d)
    assert segundo is False
    total = conn_com_fornecedor.execute(
        "SELECT COUNT(*) FROM transparencia_rj_lancamentos"
    ).fetchone()[0]
    assert total == 1


# ──────────────────────────── integração (mock API) ────────────────────────────


def test_coletar_paginado(monkeypatch: pytest.MonkeyPatch):
    """Percorre 2 páginas e salva todos os registros monitorados."""
    chamadas: list[int] = []

    def _fake_get(params, tentativas=5):
        pg = params["pagina"]
        chamadas.append(pg)
        if pg == 1:
            return {"totalRegistros": 2, "totalPaginas": 2, "data": [_contrato(numero="P-001")]}
        if pg == 2:
            return {"totalRegistros": 2, "totalPaginas": 2, "data": [_contrato(numero="P-002")]}
        return None

    monkeypatch.setattr("extrator.empenhos_diarios._get_pncp", _fake_get)
    monkeypatch.setattr("extrator.empenhos_diarios.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "extrator.empenhos_diarios.get_conn",
        lambda: (
            lambda c: (
                c.execute(
                    "INSERT INTO fornecedores (ni, tipo_pessoa, razao_social) VALUES (?, ?, ?)",
                    ("12345678000100", "PJ", "Empresa"),
                ),
                c.commit(),
                c,
            )[-1]
        )(_make_conn()),
    )

    resultado = coletar_empenhos_novos("20260614", "20260615")

    assert resultado["total_pncp"] == 2
    assert resultado["novos_monitorados"] == 2
    assert resultado["salvos"] == 2
    assert chamadas == [1, 2]


def test_coletar_filtra_nao_monitorados(monkeypatch: pytest.MonkeyPatch):
    """Contratos de NIs ausentes na tabela fornecedores não são persistidos."""

    def _fake_get(params, tentativas=5):
        return {
            "totalRegistros": 1,
            "totalPaginas": 1,
            "data": [_contrato(ni="99999999000199", numero="PNCP-X")],
        }

    monkeypatch.setattr("extrator.empenhos_diarios._get_pncp", _fake_get)
    monkeypatch.setattr("extrator.empenhos_diarios.time.sleep", lambda _: None)
    monkeypatch.setattr("extrator.empenhos_diarios.get_conn", _make_conn)

    resultado = coletar_empenhos_novos("20260614", "20260615")

    assert resultado["total_pncp"] == 1
    assert resultado["novos_monitorados"] == 0
    assert resultado["salvos"] == 0


def test_coletar_api_falha_total(monkeypatch: pytest.MonkeyPatch):
    """RuntimeError da API é absorvida e retorna zeros sem levantar exceção."""

    def _fake_get(params, tentativas=5):
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr("extrator.empenhos_diarios._get_pncp", _fake_get)
    monkeypatch.setattr("extrator.empenhos_diarios.time.sleep", lambda _: None)
    monkeypatch.setattr("extrator.empenhos_diarios.get_conn", _make_conn)

    resultado = coletar_empenhos_novos("20260614", "20260615")

    assert resultado["total_pncp"] == 0
    assert resultado["salvos"] == 0


def test_coletar_sem_dados(monkeypatch: pytest.MonkeyPatch):
    """API retornando None/vazio encerra o loop imediatamente."""

    def _fake_get(params, tentativas=5):
        return None

    monkeypatch.setattr("extrator.empenhos_diarios._get_pncp", _fake_get)
    monkeypatch.setattr("extrator.empenhos_diarios.get_conn", _make_conn)

    resultado = coletar_empenhos_novos("20260614", "20260615")

    assert set(resultado.keys()) == {"total_pncp", "novos_monitorados", "salvos"}
    assert resultado["total_pncp"] == 0


def test_coletar_duplicados_contam_uma_vez(monkeypatch: pytest.MonkeyPatch):
    """Mesmo contrato vindo em duas páginas é salvo só na primeira vez."""
    pagina_count = [0]

    def _fake_get(params, tentativas=5):
        pagina_count[0] += 1
        if pagina_count[0] == 1:
            return {
                "totalRegistros": 2,
                "totalPaginas": 2,
                "data": [_contrato(numero="PNCP-DUP")],
            }
        return {
            "totalRegistros": 2,
            "totalPaginas": 2,
            "data": [_contrato(numero="PNCP-DUP")],  # mesmo contrato
        }

    monkeypatch.setattr("extrator.empenhos_diarios._get_pncp", _fake_get)
    monkeypatch.setattr("extrator.empenhos_diarios.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "extrator.empenhos_diarios.get_conn",
        lambda: (
            lambda c: (
                c.execute(
                    "INSERT INTO fornecedores (ni, tipo_pessoa, razao_social) VALUES (?, ?, ?)",
                    ("12345678000100", "PJ", "Empresa"),
                ),
                c.commit(),
                c,
            )[-1]
        )(_make_conn()),
    )

    resultado = coletar_empenhos_novos("20260614", "20260615")

    assert resultado["total_pncp"] == 2
    assert resultado["novos_monitorados"] == 2
    assert resultado["salvos"] == 1  # segundo insert rejeitado por UNIQUE


# ──────────────────────────── coletar_empenhos_retroativo ────────────────────


def test_retroativo_1_chunk_sem_sleep(monkeypatch: pytest.MonkeyPatch):
    """dias=6 cabe em 1 chunk de 7 dias → coletar_empenhos_novos chamado 1 vez, sem sleep."""
    chamadas: list[tuple[str, str]] = []
    sleeps: list[float] = []

    def _fake_coletar(data_ini, data_fim):
        chamadas.append((data_ini, data_fim))
        return {"total_pncp": 3, "novos_monitorados": 1, "salvos": 1}

    monkeypatch.setattr("extrator.empenhos_diarios.coletar_empenhos_novos", _fake_coletar)
    monkeypatch.setattr("extrator.empenhos_diarios.time.sleep", lambda s: sleeps.append(s))

    resultado = coletar_empenhos_retroativo(dias=6)

    assert len(chamadas) == 1
    assert sleeps == []
    assert resultado["chunks_processados"] == 1


def test_retroativo_acumula_metricas_por_chunk(monkeypatch: pytest.MonkeyPatch):
    """dias=13 → 2 chunks; métricas de cada chunk são somadas no retorno."""

    def _fake_coletar(data_ini, data_fim):
        return {"total_pncp": 10, "novos_monitorados": 4, "salvos": 2}

    monkeypatch.setattr("extrator.empenhos_diarios.coletar_empenhos_novos", _fake_coletar)
    monkeypatch.setattr("extrator.empenhos_diarios.time.sleep", lambda _: None)

    resultado = coletar_empenhos_retroativo(dias=13)

    assert resultado["chunks_processados"] == 2
    assert resultado["total_pncp"] == 20
    assert resultado["novos_monitorados"] == 8
    assert resultado["salvos"] == 4


def test_retroativo_dorme_1s_apenas_entre_chunks(monkeypatch: pytest.MonkeyPatch):
    """dias=13 → 2 chunks → time.sleep(1) chamado exatamente 1 vez (não após o último)."""
    sleeps: list[float] = []

    monkeypatch.setattr(
        "extrator.empenhos_diarios.coletar_empenhos_novos",
        lambda d_ini, d_fim: {"total_pncp": 0, "novos_monitorados": 0, "salvos": 0},
    )
    monkeypatch.setattr("extrator.empenhos_diarios.time.sleep", lambda s: sleeps.append(s))

    coletar_empenhos_retroativo(dias=13)

    assert sleeps == [1]


def test_retroativo_formato_data_yyyymmdd(monkeypatch: pytest.MonkeyPatch):
    """As strings de data passadas a coletar_empenhos_novos seguem o formato YYYYMMDD."""
    import re

    datas_recebidas: list[str] = []

    def _fake_coletar(data_ini, data_fim):
        datas_recebidas.extend([data_ini, data_fim])
        return {"total_pncp": 0, "novos_monitorados": 0, "salvos": 0}

    monkeypatch.setattr("extrator.empenhos_diarios.coletar_empenhos_novos", _fake_coletar)
    monkeypatch.setattr("extrator.empenhos_diarios.time.sleep", lambda _: None)

    coletar_empenhos_retroativo(dias=6)

    assert len(datas_recebidas) == 2
    for data in datas_recebidas:
        assert re.fullmatch(r"\d{8}", data), f"Formato inválido: {data}"
