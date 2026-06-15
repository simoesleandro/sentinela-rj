"""Testes do detector de fracionamento de empenhos."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from analisador import fracionamento_empenhos
from db.conexao import SCHEMA_PATH, aplicar_migracoes

_NI = "11111111000100"
_NI_2 = "22222222000100"


@pytest.fixture
def conn() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    conexao.row_factory = sqlite3.Row
    conexao.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conexao)
    conexao.execute(
        "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?)",
        (_NI, "Empresa Fracionadora Ltda"),
    )
    conexao.commit()
    return conexao


def _insere_lancamentos(conn: sqlite3.Connection, ni: str, datas_valores: list[tuple[str, float]]) -> None:
    for i, (data, valor) in enumerate(datas_valores):
        conn.execute(
            """
            INSERT INTO transparencia_rj_lancamentos
                (fornecedor_ni, valor, data_lancamento, descricao, orgao, documento)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ni, valor, data, "Serviço avulso", "ORGAO TESTE", f"DOC-{ni}-{i:03d}"),
        )
    conn.commit()


def _d(base: str, dias: int = 0) -> str:
    return str(date.fromisoformat(base) + timedelta(days=dias))


# ─── Testes positivos ────────────────────────────────────────────────────────


def test_dispara_quando_muitos_empenhos_pequenos(conn):
    """3 empenhos de R$ 20 mil em 30 dias: total R$ 60 k → deve disparar."""
    _insere_lancamentos(conn, _NI, [
        ("2025-06-01", 20_000.0),
        ("2025-06-10", 20_000.0),
        ("2025-06-20", 20_000.0),
    ])
    resultados = fracionamento_empenhos.detectar(conn)
    assert len(resultados) == 1
    r = resultados[0]
    assert r.tipo == "fracionamento_empenhos"
    assert r.metricas["qtd_empenhos"] == 3
    assert abs(r.metricas["valor_total"] - 60_000.0) < 0.01


def test_score_e_severidade_alta(conn):
    """5 empenhos de R$ 10 k em 30 dias → score ≥ 0,65 → severidade alta."""
    # score = 0,40×(5/10) + 0,60×(1 - 10000/50000) = 0,20 + 0,48 = 0,68
    base = "2025-03-01"
    _insere_lancamentos(conn, _NI, [
        (_d(base, i * 5), 10_000.0) for i in range(5)
    ])
    resultados = fracionamento_empenhos.detectar(conn)
    assert len(resultados) == 1
    r = resultados[0]
    assert r.severidade == "alta"
    assert r.score >= 0.65
    assert abs(r.score - 0.68) < 0.001


def test_score_e_severidade_media(conn):
    """3 empenhos de R$ 20 k → score 0,48 → severidade media."""
    # score = 0,40×(3/10) + 0,60×(1 - 20000/50000) = 0,12 + 0,36 = 0,48
    _insere_lancamentos(conn, _NI, [
        ("2025-06-01", 20_000.0),
        ("2025-06-10", 20_000.0),
        ("2025-06-20", 20_000.0),
    ])
    resultados = fracionamento_empenhos.detectar(conn)
    assert len(resultados) == 1
    r = resultados[0]
    assert r.severidade == "media"
    assert abs(r.score - 0.48) < 0.001


# ─── Testes negativos (não deve disparar) ───────────────────────────────────


def test_nao_dispara_poucos_empenhos(conn):
    """Apenas 2 empenhos na janela → não atinge mínimo de 3."""
    _insere_lancamentos(conn, _NI, [
        ("2025-06-01", 30_000.0),
        ("2025-06-15", 30_000.0),
    ])
    assert fracionamento_empenhos.detectar(conn) == []


def test_nao_dispara_valor_medio_alto(conn):
    """3 empenhos com valor médio ≥ R$ 50 k → não é fracionamento."""
    _insere_lancamentos(conn, _NI, [
        ("2025-06-01", 60_000.0),
        ("2025-06-10", 60_000.0),
        ("2025-06-20", 60_000.0),
    ])
    assert fracionamento_empenhos.detectar(conn) == []


def test_nao_dispara_total_abaixo_do_minimo(conn):
    """3 empenhos de R$ 1 k cada (total R$ 3 k) → total < R$ 50 k → não dispara."""
    _insere_lancamentos(conn, _NI, [
        ("2025-06-01", 1_000.0),
        ("2025-06-10", 1_000.0),
        ("2025-06-20", 1_000.0),
    ])
    assert fracionamento_empenhos.detectar(conn) == []


def test_janela_exclui_empenhos_fora_dos_30_dias(conn):
    """Empenhos espaçados > 30 dias entre si: nenhuma janela reúne 3."""
    # Datas: dia 0, dia 31, dia 62 — separados por 31 dias cada
    base = date(2025, 1, 1)
    _insere_lancamentos(conn, _NI, [
        (str(base), 30_000.0),
        (str(base + timedelta(days=31)), 30_000.0),
        (str(base + timedelta(days=62)), 30_000.0),
    ])
    assert fracionamento_empenhos.detectar(conn) == []


def test_banco_vazio_retorna_lista_vazia(conn):
    """Sem lançamentos → nenhuma anomalia."""
    assert fracionamento_empenhos.detectar(conn) == []


# ─── Testes adicionais ───────────────────────────────────────────────────────


def test_metricas_contidas_no_resultado(conn):
    """Resultado deve ter todas as chaves de métricas especificadas."""
    _insere_lancamentos(conn, _NI, [
        ("2025-06-01", 20_000.0),
        ("2025-06-10", 20_000.0),
        ("2025-06-20", 20_000.0),
    ])
    r = fracionamento_empenhos.detectar(conn)[0]
    for chave in ("qtd_empenhos", "valor_medio", "valor_total", "janela_inicio", "janela_fim"):
        assert chave in r.metricas, f"Chave ausente: {chave}"


def test_documentos_incluidos_em_contratos(conn):
    """Os números de documento dos empenhos da janela devem aparecer em r.contratos."""
    _insere_lancamentos(conn, _NI, [
        ("2025-06-01", 20_000.0),
        ("2025-06-10", 20_000.0),
        ("2025-06-20", 20_000.0),
    ])
    r = fracionamento_empenhos.detectar(conn)[0]
    assert len(r.contratos) == 3
    assert all(doc.startswith("DOC-") for doc in r.contratos)


def test_melhor_janela_escolhida_por_score(conn):
    """Quando há duas janelas possíveis, o resultado deve refletir a de maior score."""
    conn.execute(
        "INSERT INTO fornecedores (ni, razao_social) VALUES (?, ?)",
        (_NI_2, "Segundo Fornecedor"),
    )
    conn.commit()
    # Fornecedor _NI: janela A = 3 × R$20k (score 0,48) | janela B = 5 × R$10k (score 0,68)
    _insere_lancamentos(conn, _NI, [
        ("2025-01-01", 20_000.0),
        ("2025-01-10", 20_000.0),
        ("2025-01-20", 20_000.0),
        ("2025-03-01", 10_000.0),  # nova janela começa aqui
        ("2025-03-06", 10_000.0),
        ("2025-03-11", 10_000.0),
        ("2025-03-16", 10_000.0),
        ("2025-03-21", 10_000.0),
    ])
    resultados = fracionamento_empenhos.detectar(conn)
    # Deve emitir apenas 1 resultado para _NI com o maior score
    resultados_ni = [r for r in resultados if _NI in r.titulo or r.metricas["qtd_empenhos"] == 5]
    assert len(resultados_ni) == 1
    assert resultados_ni[0].score >= 0.65
    assert resultados_ni[0].metricas["qtd_empenhos"] == 5
