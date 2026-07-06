"""Testes para conflito_interesse/repository.py (CandidatoConflitoRepository).

Mesma abordagem usada para SupabaseFolhaPagamentoRepository: como
psycopg2.extras.execute_values depende de cur.mogrify (só existe em cursores
psycopg2 reais), usamos uma FakeCursor/FakeConn que mimetiza o suficiente da
API do psycopg2 para exercitar a SQL real gerada por execute_values.
"""
from __future__ import annotations

from typing import Any

import pytest

from conflito_interesse.matcher import CandidatoConflito
from conflito_interesse.repository import CandidatoConflitoRepository


class _FakeCursor:
    """Simula a tabela candidatos_conflito_interesse com UNIQUE (fornecedor_ni,
    matricula_servidor) e ON CONFLICT DO UPDATE dos 3 campos de sinal extra
    (data_entrada_sociedade, faixa_etaria_socio, primeira_competencia_servidor),
    preservando status/revisado_em — não fazem parte do SET do UPDATE real."""

    _COLUNAS = (
        "fornecedor_ni", "nome_socio", "qualificacao_socio",
        "matricula_servidor", "nome_servidor", "sigla_ua",
        "score_similaridade", "data_entrada_sociedade",
        "faixa_etaria_socio", "primeira_competencia_servidor",
        "contrato_ativo", "valor_total_contratos",
        "qtd_servidores_matched_mesmo_socio",
    )

    def __init__(self, tabela: dict[tuple[str, str], dict], linhas_por_chave: dict[tuple[str, str], int]):
        self._tabela = tabela
        self._linhas_por_chave = linhas_por_chave
        self._proximo_id = max(linhas_por_chave.values(), default=0) + 1
        self.queries: list[str] = []
        self._resultado: list[tuple[int]] = []
        self.connection = type("_FakeRawConn", (), {"encoding": "UTF8"})()

    def execute(self, sql: str | bytes) -> None:
        if isinstance(sql, bytes):
            sql = sql.decode("utf-8")
        self.queries.append(sql)
        self._resultado = []
        if "INSERT INTO candidatos_conflito_interesse" not in sql:
            return
        import re

        tuplas = re.findall(r"\(([^()]+)\)", sql.split("VALUES")[1].split("ON CONFLICT")[0])
        for t in tuplas:
            valores = [None if v.strip() == "NULL" else v.strip().strip("'") for v in t.split(",")]
            linha = dict(zip(self._COLUNAS, valores))
            chave = (linha["fornecedor_ni"], linha["matricula_servidor"])
            if chave in self._linhas_por_chave:
                registro = self._tabela[self._linhas_por_chave[chave]]
                registro["data_entrada_sociedade"] = linha["data_entrada_sociedade"]
                registro["faixa_etaria_socio"] = linha["faixa_etaria_socio"]
                registro["primeira_competencia_servidor"] = linha["primeira_competencia_servidor"]
                registro["contrato_ativo"] = linha["contrato_ativo"]
                registro["valor_total_contratos"] = linha["valor_total_contratos"]
                registro["qtd_servidores_matched_mesmo_socio"] = linha["qtd_servidores_matched_mesmo_socio"]
            else:
                id_ = self._proximo_id
                self._linhas_por_chave[chave] = id_
                self._tabela[id_] = {**linha, "status": "aberto", "revisado_em": None}
                self._proximo_id += 1
            self._resultado.append((self._linhas_por_chave[chave],))

    def fetchall(self) -> list[tuple[int]]:
        return self._resultado

    def mogrify(self, template: str, args: Any) -> bytes:
        valores = ", ".join("NULL" if v is None else f"'{v}'" for v in args)
        return f"({valores})".encode()


class _FakeConn:
    def __init__(self):
        self.tabela: dict[int, dict] = {}
        self.linhas_por_chave: dict[tuple[str, str], int] = {}
        self.commits = 0
        self.last_cursor: _FakeCursor | None = None

    def cursor(self) -> _FakeCursor:
        self.last_cursor = _FakeCursor(self.tabela, self.linhas_por_chave)
        return self.last_cursor

    def commit(self) -> None:
        self.commits += 1


def _candidato(
    fornecedor_ni: str = "12345678000199",
    matricula_servidor: str = "0001",
    score: float = 92.5,
    data_entrada_sociedade: str | None = None,
    faixa_etaria_socio: str | None = None,
    primeira_competencia_servidor: str | None = None,
    contrato_ativo: bool = False,
    valor_total_contratos: float | None = None,
    qtd_servidores_matched_mesmo_socio: int = 1,
) -> CandidatoConflito:
    return CandidatoConflito(
        fornecedor_ni=fornecedor_ni,
        nome_socio="MARIA DA SILVA SANTOS",
        qualificacao_socio="Presidente",
        matricula_servidor=matricula_servidor,
        nome_servidor="MARIA SILVA SANTOS",
        sigla_ua=None,
        score_similaridade=score,
        data_entrada_sociedade=data_entrada_sociedade,
        faixa_etaria_socio=faixa_etaria_socio,
        primeira_competencia_servidor=primeira_competencia_servidor,
        contrato_ativo=contrato_ativo,
        valor_total_contratos=valor_total_contratos,
        qtd_servidores_matched_mesmo_socio=qtd_servidores_matched_mesmo_socio,
    )


@pytest.fixture
def conn():
    return _FakeConn()


def test_salvar_candidatos_insere_novos(conn):
    repo = CandidatoConflitoRepository(conn)
    inseridos = repo.salvar_candidatos([_candidato()])

    assert inseridos == 1
    assert len(conn.tabela) == 1
    assert conn.commits == 1


def test_salvar_candidatos_reprocessamento_nao_duplica_linha(conn):
    """Rodar o matcher de novo com o mesmo candidato faz UPSERT (não INSERT
    ignorado) — a linha é atualizada, mas não duplicada."""
    repo = CandidatoConflitoRepository(conn)
    registros = [_candidato()]

    repo.salvar_candidatos(registros)
    repo.salvar_candidatos(registros)

    assert len(conn.tabela) == 1


def test_salvar_candidatos_reprocessamento_preserva_status_e_revisado_em(conn):
    """UPSERT não deve sobrescrever status nem revisado_em de um candidato
    já triado manualmente — só os sinais extras são atualizados."""
    repo = CandidatoConflitoRepository(conn)
    registros = [_candidato()]
    repo.salvar_candidatos(registros)

    id_ = next(iter(conn.tabela))
    conn.tabela[id_]["status"] = "confirmado"
    conn.tabela[id_]["revisado_em"] = "2026-01-01T00:00:00"

    repo.salvar_candidatos(
        [_candidato(data_entrada_sociedade="2010-05-01", faixa_etaria_socio="41 a 50 anos")]
    )

    assert conn.tabela[id_]["status"] == "confirmado"
    assert conn.tabela[id_]["revisado_em"] == "2026-01-01T00:00:00"


def test_salvar_candidatos_deduplica_mesma_chave_mantendo_maior_score(conn):
    """Dois sócios diferentes do mesmo fornecedor batendo com o mesmo servidor
    geram a mesma chave (fornecedor_ni, matricula_servidor) no lote — sem
    deduplicar, o Postgres real rejeitaria com CardinalityViolation (UPSERT
    afetando a mesma linha duas vezes no mesmo comando)."""
    repo = CandidatoConflitoRepository(conn)
    registros = [
        _candidato(score=82.0, data_entrada_sociedade="2005-01-01"),
        _candidato(score=95.0, data_entrada_sociedade="2012-06-01"),
    ]

    inseridos = repo.salvar_candidatos(registros)

    assert inseridos == 1
    assert len(conn.tabela) == 1
    id_ = next(iter(conn.tabela))
    assert conn.tabela[id_]["score_similaridade"] == "95.0"
    assert conn.tabela[id_]["data_entrada_sociedade"] == "2012-06-01"


def test_salvar_candidatos_reprocessamento_atualiza_sinais_extras(conn):
    repo = CandidatoConflitoRepository(conn)
    repo.salvar_candidatos([_candidato()])

    id_ = next(iter(conn.tabela))
    assert conn.tabela[id_]["data_entrada_sociedade"] is None

    repo.salvar_candidatos(
        [_candidato(
            data_entrada_sociedade="2010-05-01",
            faixa_etaria_socio="41 a 50 anos",
            primeira_competencia_servidor="2015-03-01",
        )]
    )

    assert conn.tabela[id_]["data_entrada_sociedade"] == "2010-05-01"
    assert conn.tabela[id_]["faixa_etaria_socio"] == "41 a 50 anos"
    assert conn.tabela[id_]["primeira_competencia_servidor"] == "2015-03-01"


def test_salvar_candidatos_matriculas_diferentes_mesmo_fornecedor(conn):
    repo = CandidatoConflitoRepository(conn)
    registros = [
        _candidato(matricula_servidor="0001"),
        _candidato(matricula_servidor="0002"),
    ]

    inseridos = repo.salvar_candidatos(registros)

    assert inseridos == 2
    assert len(conn.tabela) == 2


def test_salvar_candidatos_lista_vazia_nao_chama_execute_values(conn):
    repo = CandidatoConflitoRepository(conn)
    inseridos = repo.salvar_candidatos([])

    assert inseridos == 0
    assert conn.commits == 0
    assert conn.last_cursor is None


def test_salvar_candidatos_usa_sql_correta(conn):
    repo = CandidatoConflitoRepository(conn)
    repo.salvar_candidatos([_candidato()])

    sql = conn.last_cursor.queries[0]
    assert "INSERT INTO candidatos_conflito_interesse" in sql
    assert "ON CONFLICT (fornecedor_ni, matricula_servidor) DO UPDATE SET" in sql
    assert "data_entrada_sociedade = EXCLUDED.data_entrada_sociedade" in sql
    assert "faixa_etaria_socio = EXCLUDED.faixa_etaria_socio" in sql
    assert "primeira_competencia_servidor = EXCLUDED.primeira_competencia_servidor" in sql
    assert "contrato_ativo = EXCLUDED.contrato_ativo" in sql
    assert "valor_total_contratos = EXCLUDED.valor_total_contratos" in sql
    assert "qtd_servidores_matched_mesmo_socio = EXCLUDED.qtd_servidores_matched_mesmo_socio" in sql
    assert "status" not in sql.split("DO UPDATE SET")[1].split("RETURNING")[0]
    assert "RETURNING id" in sql


def test_salvar_candidatos_reprocessamento_atualiza_sinais_de_priorizacao(conn):
    repo = CandidatoConflitoRepository(conn)
    repo.salvar_candidatos([_candidato()])

    id_ = next(iter(conn.tabela))
    assert conn.tabela[id_]["qtd_servidores_matched_mesmo_socio"] == "1"

    repo.salvar_candidatos(
        [_candidato(
            contrato_ativo=True,
            valor_total_contratos=1500.5,
            qtd_servidores_matched_mesmo_socio=3,
        )]
    )

    assert conn.tabela[id_]["contrato_ativo"] == "True"
    assert conn.tabela[id_]["valor_total_contratos"] == "1500.5"
    assert conn.tabela[id_]["qtd_servidores_matched_mesmo_socio"] == "3"
