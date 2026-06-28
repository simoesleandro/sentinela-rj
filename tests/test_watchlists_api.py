"""Testes Flask — CRUD de watchlists e regras de alerta."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from db.conexao import SCHEMA_PATH, aplicar_migracoes


def _bootstrap_db(db_file: Path) -> None:
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conn)
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    import web_app as wa
    import web_auth

    wa._migracoes_aplicadas = True
    db_file = tmp_path / "flask_api.db"
    _bootstrap_db(db_file)

    def _fake_get_db() -> sqlite3.Connection:
        conexao = sqlite3.connect(db_file, check_same_thread=False)
        conexao.row_factory = sqlite3.Row
        return conexao

    wa.get_db = _fake_get_db
    # CRUD de watchlists/regras exige login (requer_login); simula usuário logado.
    monkeypatch.setattr(
        web_auth, "usuario_atual",
        lambda conn: {"id": 1, "is_admin": 0, "email_verificado": 1},
    )
    with wa.app.test_client() as test_client:
        yield test_client


@pytest.fixture
def client_anon(tmp_path: Path):
    """Cliente sem login — para checar bloqueio de escrita (requer_login)."""
    import web_app as wa

    wa._migracoes_aplicadas = True
    db_file = tmp_path / "flask_api_anon.db"
    _bootstrap_db(db_file)

    def _fake_get_db() -> sqlite3.Connection:
        conexao = sqlite3.connect(db_file, check_same_thread=False)
        conexao.row_factory = sqlite3.Row
        return conexao

    wa.get_db = _fake_get_db
    with wa.app.test_client() as test_client:
        yield test_client


def test_escrita_sem_login_bloqueada(client_anon) -> None:
    """POST/PATCH/DELETE sem sessão → 401; GET continua público."""
    res = client_anon.post("/api/watchlists", json={"rotulo": "x"})
    assert res.status_code == 401
    res = client_anon.post("/api/regras-alerta", json={"severidade_min": "alta"})
    assert res.status_code == 401
    res = client_anon.patch("/api/alertas/1", json={"status": "investigando"})
    assert res.status_code == 401
    # leitura pública permanece liberada
    assert client_anon.get("/api/watchlists").status_code == 200


def test_watchlists_post_e_listagem(client) -> None:
    res = client.post(
        "/api/watchlists",
        json={"rotulo": "Monitorar Alfa", "fornecedor_ni": "98765432000111"},
    )
    assert res.status_code == 201
    payload = res.get_json()
    assert payload["rotulo"] == "Monitorar Alfa"

    lista = client.get("/api/watchlists")
    assert lista.status_code == 200
    items = lista.get_json()["items"]
    assert len(items) == 1
    assert items[0]["fornecedor_ni"] == "98765432000111"


def test_watchlists_patch_e_delete(client) -> None:
    criado = client.post(
        "/api/watchlists",
        json={"rotulo": "WL", "palavra_chave_objeto": "software"},
    ).get_json()

    res = client.patch(
        f"/api/watchlists/{criado['id']}",
        json={"rotulo": "WL atualizada", "ativo": 0},
    )
    assert res.status_code == 200
    assert res.get_json()["rotulo"] == "WL atualizada"
    assert res.get_json()["ativo"] == 0

    res_del = client.delete(f"/api/watchlists/{criado['id']}")
    assert res_del.status_code == 200
    assert res_del.get_json()["ativo"] == 0


def test_regras_post_e_listagem(client) -> None:
    res = client.post(
        "/api/regras-alerta",
        json={"severidade_min": "alta", "tipo": "outlier_valor", "valor_min": 1_000_000},
    )
    assert res.status_code == 201
    assert res.get_json()["severidade_min"] == "alta"

    lista = client.get("/api/regras-alerta")
    assert lista.status_code == 200
    assert len(lista.get_json()["items"]) == 1


def test_regras_validacao_severidade(client) -> None:
    res = client.post(
        "/api/regras-alerta",
        json={"severidade_min": "critica"},
    )
    assert res.status_code == 422


def test_pipeline_status_endpoint(client) -> None:
    res = client.get("/api/pipeline/status")
    assert res.status_code == 200
    payload = res.get_json()
    assert "saude" in payload
    assert "pipeline" in payload
    assert "janela_dias" in payload["pipeline"]
