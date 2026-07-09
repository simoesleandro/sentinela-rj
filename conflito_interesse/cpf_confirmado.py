"""Fecha a identidade do sócio no conflito de interesse com o CPF confirmado.

O match sócio×servidor nasceu "sem CPF": o QSA só traz o CPF do sócio mascarado
(``***MMMMMM**``), então a confirmação de que sócio e servidor são a mesma pessoa
dependia de nome + sinais indiretos. O detector socio_doou_campanha
(analisador/doacoes.py) resolve isso cruzando o QSA com as doações de campanha do
TSE (que trazem o CPF completo): quando o nome bate e os 6 dígitos do meio
conferem, gravamos o CPF completo em ``socios_cpf_confirmado`` no banco core.

Este módulo propaga esse CPF para os candidatos do conflito de interesse
(Supabase). O casamento é EXATO por ``(fornecedor_ni, nome_socio)`` — os dois
lados vêm da mesma fonte (fornecedor_cadastro.socios), então não há necessidade
de fuzzy matching aqui.
"""
from __future__ import annotations

import sqlite3
from typing import Any


def atualizar_cpf_confirmado(conn_destino: Any, conn_sentinela: sqlite3.Connection) -> int:
    """Copia socios_cpf_confirmado (core) -> candidatos_conflito_interesse (Supabase).

    `conn_destino` é a conexão do Supabase (psycopg2) em produção, mas a função
    também aceita uma conexão sqlite3 (usada nos testes) — o placeholder de
    parâmetro é escolhido conforme o driver. Retorna quantas linhas de candidato
    foram atualizadas.
    """
    confirmados = conn_sentinela.execute(
        "SELECT fornecedor_ni, nome_socio, cpf FROM socios_cpf_confirmado"
    ).fetchall()
    if not confirmados:
        return 0

    ph = "?" if isinstance(conn_destino, sqlite3.Connection) else "%s"
    sql = (
        f"UPDATE candidatos_conflito_interesse SET cpf_socio_confirmado = {ph} "
        f"WHERE fornecedor_ni = {ph} AND nome_socio = {ph}"
    )
    cur = conn_destino.cursor()
    atualizados = 0
    for fornecedor_ni, nome_socio, cpf in confirmados:
        cur.execute(sql, (cpf, fornecedor_ni, nome_socio))
        atualizados += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn_destino.commit()
    return atualizados
