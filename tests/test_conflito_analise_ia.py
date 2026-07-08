"""Testes do parecer de IA de conflito de interesse — prompt e endpoint."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from conflito_interesse.analise_ia import montar_prompt_candidato


def _item(**extra) -> dict:
    base = {
        "id": 7,
        "fornecedor_ni": "12345678000199",
        "nome_socio": "MARIA DA SILVA SANTOS",
        "nome_servidor": "MARIA SILVA SANTOS",
        "qualificacao_socio": "Sócio-Administrador",
        "qualificacao_classe": "gestao",
        "score_similaridade": 92.5,
        "qtd_servidores_mesmo_nome": 3,
        "faixa_etaria_socio": "41-50",
        "primeira_competencia_servidor": "2010-05-01",
        "compatibilidade_data": "compativel",
        "data_entrada_sociedade": "2018-03-01",
        "sigla_ua": "S/SUBPAV/CAP-3.3",
        "lotacao_orgao_contratante": True,
        "contrato_ativo": True,
        "valor_total_contratos": 4_500_000.0,
        "tem_alerta_severidade_alta": False,
        "tem_sancao": False,
        "status": "aberto",
    }
    base.update(extra)
    return base


# ── prompt ───────────────────────────────────────────────────────────────────

def test_prompt_inclui_sinais_e_guardas():
    prompt = montar_prompt_candidato(_item())
    # dados estruturados
    assert "MARIA DA SILVA SANTOS" in prompt
    assert "MARIA SILVA SANTOS" in prompt
    assert "92.5" in prompt
    assert "Sócio-Administrador" in prompt
    assert "PODER DE GESTÃO" in prompt
    assert "MESMO órgão de origem dos contratos do fornecedor: sim" in prompt
    # guardas de responsabilidade
    assert "HOMÔNIMOS SÃO ESPERADOS" in prompt
    assert "não de acusação" in prompt
    assert "nunca afirme" in prompt
    # formato estruturado do parecer
    assert "PLAUSIBILIDADE:" in prompt
    assert "VERIFICAR:" in prompt


def test_prompt_cotista_sem_alarde():
    prompt = montar_prompt_candidato(
        _item(qualificacao_socio="Sócio", qualificacao_classe="cotista")
    )
    assert "cotista" in prompt
    assert "PODER DE GESTÃO" not in prompt


# ── endpoint ─────────────────────────────────────────────────────────────────

class _FakeCursorIA:
    COLS = [
        "id", "fornecedor_ni", "nome_socio", "qualificacao_socio",
        "matricula_servidor", "nome_servidor", "sigla_ua",
        "score_similaridade", "data_entrada_sociedade",
        "faixa_etaria_socio", "primeira_competencia_servidor",
        "contrato_ativo", "valor_total_contratos",
        "qtd_servidores_matched_mesmo_socio",
        "tem_alerta_severidade_alta", "tem_sancao",
        "qtd_servidores_mesmo_nome", "lotacao_orgao_contratante",
        "status", "detectado_em", "revisado_em",
    ]

    def __init__(self, conn):
        self._conn = conn
        self.description = [(c,) for c in self.COLS]
        self._row = None

    def execute(self, sql: str, params: tuple = ()) -> None:
        sql_norm = " ".join(sql.split())
        if sql_norm.startswith("SELECT") and "WHERE id = %s" in sql_norm:
            registro = self._conn.tabela.get(params[0])
            self._row = (
                tuple(registro.get(c) for c in self.COLS) if registro else None
            )
        elif "SET analise_ia" in sql_norm:
            parecer, provedor, id_ = params
            self._conn.tabela[id_]["analise_ia"] = parecer
            self._conn.tabela[id_]["analise_ia_provedor"] = provedor

    def fetchone(self):
        return self._row


class _FakeConnIA:
    def __init__(self, tabela: dict[int, dict]):
        self.tabela = tabela
        self.commits = 0

    def cursor(self):
        return _FakeCursorIA(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def _registro(id_: int = 7) -> dict:
    item = _item()
    item["id"] = id_
    item["matricula_servidor"] = "0001"
    item["qtd_servidores_matched_mesmo_socio"] = 1
    item["detectado_em"] = None
    item["revisado_em"] = None
    # colunas de data chegam como date/None do psycopg2; None simplifica o fake
    item["primeira_competencia_servidor"] = None
    item["data_entrada_sociedade"] = None
    return item


@pytest.fixture
def client(monkeypatch):
    import web_app as wa

    wa._migracoes_aplicadas = True
    with wa.app.test_client() as test_client:
        yield test_client


def test_analise_ia_sucesso(client, monkeypatch):
    import web_app as wa

    fake = _FakeConnIA({7: _registro(7)})
    monkeypatch.setattr(wa, "get_conflito_conn", lambda: fake)
    monkeypatch.setattr(
        "conflito_interesse.analise_ia.analisar_candidato",
        lambda item: ("PLAUSIBILIDADE: inconclusivo\nANÁLISE: teste.", "gemini"),
    )
    with patch("web_app.checar_cota_ia", return_value=({"id": 1, "is_admin": True}, None)), \
         patch("web_app.registrar_consumo_ia") as consumo:
        res = client.post("/conflitos-interesse/7/analise-ia")

    assert res.status_code == 200
    payload = res.get_json()
    assert payload["analise_ia"].startswith("PLAUSIBILIDADE:")
    assert payload["analise_ia_provedor"] == "gemini"
    # persistiu e contabilizou a cota
    assert fake.tabela[7]["analise_ia"].startswith("PLAUSIBILIDADE:")
    assert fake.commits == 1
    consumo.assert_called_once()


def test_analise_ia_candidato_inexistente_404(client, monkeypatch):
    import web_app as wa

    monkeypatch.setattr(wa, "get_conflito_conn", lambda: _FakeConnIA({}))
    with patch("web_app.checar_cota_ia", return_value=({"id": 1, "is_admin": True}, None)):
        res = client.post("/conflitos-interesse/999/analise-ia")
    assert res.status_code == 404


def test_analise_ia_sem_provedor_503(client, monkeypatch):
    import web_app as wa

    def _sem_provedor(item):
        raise ValueError("Nenhum provedor de IA disponível.")

    monkeypatch.setattr(wa, "get_conflito_conn", lambda: _FakeConnIA({7: _registro(7)}))
    monkeypatch.setattr("conflito_interesse.analise_ia.analisar_candidato", _sem_provedor)
    with patch("web_app.checar_cota_ia", return_value=({"id": 1, "is_admin": True}, None)):
        res = client.post("/conflitos-interesse/7/analise-ia")
    assert res.status_code == 503


def test_analise_ia_exige_login(client):
    # sem sessão: checar_cota_ia real devolve 401 de login
    res = client.post("/conflitos-interesse/7/analise-ia")
    assert res.status_code == 401
    assert res.get_json()["auth"] == "login"
