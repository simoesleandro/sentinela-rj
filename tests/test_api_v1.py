"""Testes da API pública versionada (/api/v1) e do OpenAPI/Swagger."""
from __future__ import annotations

import sqlite3

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes


@pytest.fixture
def client(tmp_path):
    import web_app as wa

    wa._migracoes_aplicadas = True
    db_file = tmp_path / "api_v1.db"
    conexao = sqlite3.connect(db_file)
    conexao.row_factory = sqlite3.Row
    conexao.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conexao)
    conexao.execute(
        "INSERT INTO orgaos (cnpj, razao_social, municipio_ibge, municipio_nome) "
        "VALUES (?, ?, ?, ?)",
        ("12345678000199", "Prefeitura Teste", "3304557", "Rio de Janeiro"),
    )
    conexao.execute(
        "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?)",
        ("98765432000111", "Fornecedor Alfa"),
    )
    conexao.execute(
        """
        INSERT INTO contratos (
            numero_controle_pncp, orgao_cnpj, fornecedor_ni, objeto,
            valor_global, data_assinatura, municipio_ibge, municipio_nome
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PNCP-001", "12345678000199", "98765432000111", "Consultoria",
            1_000_000.0, "2025-01-01", "3304557", "Rio de Janeiro",
        ),
    )
    for tipo, status in [
        ("outlier_valor", "confirmado"),
        ("outlier_valor", "descartado"),
        ("concentracao_fornecedor", "aberto"),
    ]:
        conexao.execute(
            """
            INSERT INTO alertas (
                numero_controle_pncp, tipo, severidade, score,
                descricao, valor_referencia, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("PNCP-001", tipo, "alta", 0.9, "desc", 1_000_000.0, status),
        )
    conexao.commit()
    conexao.close()

    def _fake_get_db() -> sqlite3.Connection:
        c = sqlite3.connect(db_file, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    wa.get_db = _fake_get_db
    with wa.app.test_client() as test_client:
        yield test_client


def test_openapi_json_valido(client) -> None:
    res = client.get("/api/v1/openapi.json")
    assert res.status_code == 200
    spec = res.get_json()
    assert spec["openapi"].startswith("3.")
    assert "/api/v1/alertas" in spec["paths"]
    assert "/api/v1/contratos" in spec["paths"]
    assert "/api/v1/precisao" in spec["paths"]
    # server_url é injetado a partir do host da requisição
    assert spec["servers"][0]["url"]


def test_openapi_server_url_honra_forwarded_proto(client) -> None:
    # Atrás do proxy TLS do Fly a app vê http; o header preserva o https real.
    res = client.get("/api/v1/openapi.json", headers={"X-Forwarded-Proto": "https"})
    assert res.get_json()["servers"][0]["url"].startswith("https://")


def test_docs_page_renderiza(client) -> None:
    res = client.get("/api/docs")
    assert res.status_code == 200
    assert b"swagger-ui" in res.data


def test_v1_alertas_envelope_e_contrato(client) -> None:
    res = client.get("/api/v1/alertas")
    assert res.status_code == 200
    body = res.get_json()
    assert body["total"] == 3
    assert {"items", "page", "per_page", "pages"} <= body.keys()
    a = body["items"][0]
    assert a["contrato"]["pncp"] == "PNCP-001"
    assert a["contrato"]["fornecedor"] == "Fornecedor Alfa"


def test_v1_alertas_filtra_por_tipo(client) -> None:
    res = client.get("/api/v1/alertas?tipo=outlier_valor")
    body = res.get_json()
    assert body["total"] == 2
    assert all(i["tipo"] == "outlier_valor" for i in body["items"])


def test_v1_alertas_per_page_limitado(client) -> None:
    res = client.get("/api/v1/alertas?per_page=9999")
    body = res.get_json()
    assert body["per_page"] == 100  # teto aplicado


def test_v1_contratos_lista(client) -> None:
    res = client.get("/api/v1/contratos?municipio_ibge=3304557")
    assert res.status_code == 200
    body = res.get_json()
    assert body["total"] == 1
    assert body["items"][0]["pncp"] == "PNCP-001"


def test_v1_precisao_mesma_fonte(client) -> None:
    res = client.get("/api/v1/precisao")
    assert res.status_code == 200
    body = res.get_json()
    outlier = next(i for i in body["itens"] if i["tipo"] == "outlier_valor")
    assert outlier["confirmados"] == 1
    assert outlier["descartados"] == 1


def test_v1_alertas_tem_cors(client) -> None:
    res = client.get("/api/v1/alertas")
    assert res.headers.get("Access-Control-Allow-Origin") == "*"
