"""Testes da materialização dos sinais de conflito por fornecedor
(db.conflito_flags.sincronizar_flags): agrega o Supabase para a tabela do core."""
import sqlite3

import pytest

from db.conflito_flags import sincronizar_flags

DDL = """
CREATE TABLE fornecedores_conflito (
    fornecedor_ni       TEXT PRIMARY KEY,
    qtd_candidatos      INTEGER NOT NULL DEFAULT 0,
    tem_lotacao         INTEGER NOT NULL DEFAULT 0,
    tem_cpf_confirmado  INTEGER NOT NULL DEFAULT 0,
    atualizado_em       TEXT DEFAULT (datetime('now'))
)
"""


class _FakeCursor:
    def __init__(self, rows, falha_primeira=False):
        self._rows = rows
        self._falha = falha_primeira
        self._executou = 0

    def execute(self, sql):
        self._executou += 1
        # Simula banco sem a coluna cpf: 1ª query falha, fallback (2ª) passa.
        if self._falha and self._executou == 1:
            raise Exception("column cpf_socio_confirmado does not exist")

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows, falha_primeira=False):
        self._rows = rows
        self._falha = falha_primeira

    def cursor(self):
        return _FakeCursor(self._rows, self._falha)

    def rollback(self):
        pass


@pytest.fixture
def core():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(DDL)
    yield conn
    conn.close()


def _linhas(core):
    return {
        r["fornecedor_ni"]: (r["qtd_candidatos"], r["tem_lotacao"], r["tem_cpf_confirmado"])
        for r in core.execute("SELECT * FROM fornecedores_conflito")
    }


def test_materializa_flags_booleanas(core):
    conflito = _FakeConn([("01047682000150", 3, True, False),
                          ("07072702000120", 1, False, True)])
    n = sincronizar_flags(core, conflito)
    assert n == 2
    linhas = _linhas(core)
    assert linhas["01047682000150"] == (3, 1, 0)
    assert linhas["07072702000120"] == (1, 0, 1)


def test_full_refresh_substitui_conteudo(core):
    sincronizar_flags(core, _FakeConn([("01", 2, True, False), ("02", 1, False, False)]))
    # Segunda sincronização com menos fornecedores deve refletir descartes.
    n = sincronizar_flags(core, _FakeConn([("01", 5, False, True)]))
    assert n == 1
    linhas = _linhas(core)
    assert set(linhas) == {"01"}
    assert linhas["01"] == (5, 0, 1)


def test_ignora_fornecedor_ni_vazio(core):
    n = sincronizar_flags(core, _FakeConn([(None, 2, True, False), ("", 1, False, False),
                                           ("03", 1, True, True)]))
    assert n == 1
    assert set(_linhas(core)) == {"03"}


def test_fallback_sem_coluna_cpf(core):
    # 1ª query levanta (banco sem cpf_socio_confirmado); usa a query alternativa.
    conflito = _FakeConn([("09", 4, True, False)], falha_primeira=True)
    n = sincronizar_flags(core, conflito)
    assert n == 1
    assert _linhas(core)["09"] == (4, 1, 0)
