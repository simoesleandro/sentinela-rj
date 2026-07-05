"""Testes das rotas Flask de /conflitos-interesse e da integração com
/api/fornecedores/<ni> — usam uma conexão Postgres fake (mesmo padrão de
tests/test_conflito_repository.py) para não depender de um Supabase real.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest


class _FakeCursor:
    def __init__(self, tabela: dict[int, dict]):
        self._tabela = tabela
        self.description: list[tuple[str]] = []
        self._resultado: list[tuple] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        sql_norm = " ".join(sql.split())

        if sql_norm.startswith("SELECT id, fornecedor_ni, nome_socio"):
            cols = [
                "id", "fornecedor_ni", "nome_socio", "qualificacao_socio",
                "matricula_servidor", "nome_servidor", "sigla_ua",
                "score_similaridade", "data_entrada_sociedade",
                "faixa_etaria_socio", "primeira_competencia_servidor",
                "status", "detectado_em", "revisado_em",
            ]
            rows = list(self._tabela.values())
            if "WHERE status = %s" in sql_norm:
                rows = [r for r in rows if r["status"] == params[0]]
            rows = sorted(rows, key=lambda r: -r["score_similaridade"])
            self.description = [(c,) for c in cols]
            self._resultado = [tuple(r[c] for c in cols) for r in rows]

        elif sql_norm.startswith("SELECT id, nome_socio, qualificacao_socio"):
            cols = [
                "id", "nome_socio", "qualificacao_socio", "matricula_servidor",
                "nome_servidor", "sigla_ua", "score_similaridade", "status",
            ]
            fornecedor_ni = params[0]
            rows = [r for r in self._tabela.values() if r["fornecedor_ni"] == fornecedor_ni]
            rows = sorted(rows, key=lambda r: -r["score_similaridade"])
            self.description = [(c,) for c in cols]
            self._resultado = [tuple(r[c] for c in cols) for r in rows]

        elif "SELECT status FROM candidatos_conflito_interesse WHERE id" in sql_norm:
            row = self._tabela.get(params[0])
            self._resultado = [(row["status"],)] if row else []

        elif sql_norm.startswith("UPDATE candidatos_conflito_interesse"):
            novo_status, id_ = params
            self._tabela[id_]["status"] = novo_status
            self._resultado = []

        elif "GROUP BY status" in sql_norm:
            contagem: dict[str, int] = {}
            for r in self._tabela.values():
                contagem[r["status"]] = contagem.get(r["status"], 0) + 1
            self._resultado = list(contagem.items())

        else:
            self._resultado = []

    def fetchall(self):
        return self._resultado

    def fetchone(self):
        return self._resultado[0] if self._resultado else None


class _FakeConn:
    def __init__(self, tabela: dict[int, dict]):
        self.tabela = tabela
        self.commits = 0

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.tabela)

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        pass


def _candidato(
    id_: int,
    status: str = "aberto",
    fornecedor_ni: str = "12345678000199",
    score: float = 92.5,
) -> dict:
    return {
        "id": id_,
        "fornecedor_ni": fornecedor_ni,
        "nome_socio": "MARIA DA SILVA SANTOS",
        "qualificacao_socio": "Presidente",
        "matricula_servidor": "0001",
        "nome_servidor": "MARIA SILVA SANTOS",
        "sigla_ua": "SMS",
        "score_similaridade": score,
        "data_entrada_sociedade": None,
        "faixa_etaria_socio": None,
        "primeira_competencia_servidor": None,
        "status": status,
        "detectado_em": datetime.now(timezone.utc),
        "revisado_em": None,
    }


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    import sqlite3

    import web_app as wa
    from db.conexao import SCHEMA_PATH, aplicar_migracoes

    # Aplica schema completo + migrações numa conexão de setup isolada, e só
    # depois aponta wa.DB_PATH para o arquivo pronto — evita repetir todo o
    # DDL de aplicar_migracoes() a cada wa.get_db() chamado durante os
    # requests do teste (fonte de "database is locked" no Windows).
    db_file = tmp_path / "test.db"
    setup_conn = sqlite3.connect(db_file)
    setup_conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(setup_conn)
    setup_conn.execute(
        "INSERT INTO fornecedores (ni, tipo_pessoa, razao_social) VALUES (?, ?, ?)",
        ("12345678000199", "PJ", "Empresa Teste Ltda"),
    )
    setup_conn.commit()
    setup_conn.close()

    # Monkeypatcha wa.get_db() diretamente (em vez de wa.DB_PATH +
    # wa._migracoes_aplicadas) para não depender de globals mutáveis
    # compartilhados entre todos os arquivos de teste do processo — outros
    # testes que rodam antes deste no mesmo processo já mudam esses globals
    # e podem interferir de forma não determinística.
    def _get_db_isolado() -> sqlite3.Connection:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(wa, "get_db", _get_db_isolado)

    tabela = {
        1: _candidato(1, status="aberto"),
        2: _candidato(2, status="investigando", fornecedor_ni="99999999000199", score=80.0),
    }
    monkeypatch.setattr(wa, "get_conflito_conn", lambda: _FakeConn(tabela))

    with wa.app.test_client() as test_client:
        yield test_client


def test_lista_default_filtra_aberto(client) -> None:
    res = client.get("/api/conflitos-interesse")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == 1
    assert data["items"][0]["status"] == "aberto"


def test_lista_filtra_por_status_explicito(client) -> None:
    res = client.get("/api/conflitos-interesse?status=investigando")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == 2


def test_lista_todos_retorna_tudo(client) -> None:
    res = client.get("/api/conflitos-interesse?status=todos")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["items"]) == 2


def test_lista_inclui_resumo_e_motivos(client) -> None:
    res = client.get("/api/conflitos-interesse?status=todos")
    data = res.get_json()
    assert data["resumo"]["aberto"] == 1
    assert data["resumo"]["investigando"] == 1
    assert data["resumo"]["confirmado"] == 0
    assert len(data["motivos_descarte"]) == 3


def test_lista_status_invalido_400(client) -> None:
    res = client.get("/api/conflitos-interesse?status=lixo")
    assert res.status_code == 400


def test_post_status_sem_login_401(client) -> None:
    res = client.post("/conflitos-interesse/1/status", json={"status": "investigando"})
    assert res.status_code == 401


def _autenticar(monkeypatch, client) -> str:
    """Simula sessão logada sem depender das tabelas de auth: patcheia
    web_auth.usuario_atual (usado por requer_login/requer_admin) para
    retornar um usuário fixo sempre que houver 'usuario_id' na sessão.

    Retorna um token CSRF real, obtido navegando pela própria página
    /conflitos-interesse (mesmo padrão que o frontend usa) — @csrf_required
    valida contra a sessão, então um token fake não passaria."""
    import web_auth

    monkeypatch.setattr(web_auth, "usuario_atual", lambda conn: {"id": 1, "is_admin": False})
    with client.session_transaction() as sess:
        sess["usuario_id"] = 1

    page = client.get("/conflitos-interesse")
    match = re.search(r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
    assert match, "token CSRF não encontrado na página"
    return match.group(1)


def test_post_status_sucesso(client, monkeypatch) -> None:
    token = _autenticar(monkeypatch, client)

    res = client.post(
        "/conflitos-interesse/1/status",
        json={"status": "investigando", "nota": "Analisando"},
        headers={"X-CSRFToken": token},
    )
    assert res.status_code == 200
    assert res.get_json()["status"] == "investigando"


def test_post_status_motivo_obrigatorio_faltando(client, monkeypatch) -> None:
    token = _autenticar(monkeypatch, client)

    res = client.post(
        "/conflitos-interesse/2/status",
        json={"status": "descartado"},
        headers={"X-CSRFToken": token},
    )
    assert res.status_code == 422
    assert "motivo" in res.get_json()["error"].lower()


def test_post_status_candidato_inexistente_404(client, monkeypatch) -> None:
    token = _autenticar(monkeypatch, client)

    res = client.post(
        "/conflitos-interesse/999/status",
        json={"status": "investigando"},
        headers={"X-CSRFToken": token},
    )
    assert res.status_code == 404


def test_fornecedor_dossie_mostra_secao_quando_ha_candidato(client) -> None:
    res = client.get("/api/fornecedores/12345678000199")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["conflitos_interesse"]) == 1
    assert data["conflitos_interesse"][0]["nome_servidor"] == "MARIA SILVA SANTOS"


def test_fornecedor_dossie_sem_candidato_lista_vazia(client) -> None:
    import web_app as wa

    db_conn = wa.get_db()
    db_conn.execute(
        "INSERT INTO fornecedores (ni, tipo_pessoa, razao_social) VALUES (?, ?, ?)",
        ("00000000000000", "PJ", "Sem Conflito Ltda"),
    )
    db_conn.commit()
    db_conn.close()

    res = client.get("/api/fornecedores/00000000000000")
    assert res.status_code == 200
    data = res.get_json()
    assert data["conflitos_interesse"] == []
