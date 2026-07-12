"""Sincroniza, por fornecedor, os sinais de conflito de interesse (sócio-servidor)
do Supabase separado para a tabela materializada `fornecedores_conflito` do core.

Objetivo: cruzar a fila de alertas com o domínio de conflito de interesse sem
consultar o Supabase no caminho quente do dashboard. A materialização é um
resumo pequeno (um registro por fornecedor com candidato), atualizado sob
demanda por endpoint admin ou pela CLI `sync_conflito_flags.py`.

O sinal forte é `tem_lotacao` (há candidato cuja lotação bate com o órgão
contratante); `tem_cpf_confirmado` indica identidade fechada via TSE. Candidatos
já descartados (falso positivo triado) não entram, para não reacender homônimos.
"""
from __future__ import annotations

import sqlite3

# A coluna cpf_socio_confirmado foi adicionada depois em alguns bancos; a query
# tolera sua ausência caindo para um agregado sem ela (ver _consultar_agregado).
_SQL_AGREGADO = """
    SELECT fornecedor_ni,
           COUNT(*)                                          AS qtd,
           BOOL_OR(COALESCE(lotacao_orgao_contratante, FALSE)) AS tem_lotacao,
           BOOL_OR(cpf_socio_confirmado IS NOT NULL)         AS tem_cpf
    FROM candidatos_conflito_interesse
    WHERE status IS DISTINCT FROM 'descartado'
    GROUP BY fornecedor_ni
"""

_SQL_AGREGADO_SEM_CPF = """
    SELECT fornecedor_ni,
           COUNT(*)                                          AS qtd,
           BOOL_OR(COALESCE(lotacao_orgao_contratante, FALSE)) AS tem_lotacao,
           FALSE                                             AS tem_cpf
    FROM candidatos_conflito_interesse
    WHERE status IS DISTINCT FROM 'descartado'
    GROUP BY fornecedor_ni
"""


def _consultar_agregado(conn_conflito) -> list[tuple]:
    cur = conn_conflito.cursor()
    try:
        cur.execute(_SQL_AGREGADO)
    except Exception:
        # Banco sem a coluna cpf_socio_confirmado: refaz sem ela.
        conn_conflito.rollback()
        cur.execute(_SQL_AGREGADO_SEM_CPF)
    return cur.fetchall()


def sincronizar_flags(conn_core: sqlite3.Connection, conn_conflito) -> int:
    """Recarrega `fornecedores_conflito` a partir do Supabase. Full refresh numa
    transação (DELETE + INSERT) para refletir descartes e novos candidatos.
    Devolve a quantidade de fornecedores materializados."""
    linhas = _consultar_agregado(conn_conflito)

    registros = [
        (
            str(fornecedor_ni),
            int(qtd or 0),
            1 if tem_lotacao else 0,
            1 if tem_cpf else 0,
        )
        for (fornecedor_ni, qtd, tem_lotacao, tem_cpf) in linhas
        if fornecedor_ni
    ]

    conn_core.execute("DELETE FROM fornecedores_conflito")
    conn_core.executemany(
        """
        INSERT INTO fornecedores_conflito
            (fornecedor_ni, qtd_candidatos, tem_lotacao, tem_cpf_confirmado)
        VALUES (?, ?, ?, ?)
        """,
        registros,
    )
    conn_core.commit()
    return len(registros)
