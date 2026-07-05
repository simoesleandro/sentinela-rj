"""Persistência dos candidatos a conflito de interesse (Supabase/Postgres).

Ao contrário do dado bruto de folha de pagamento, esta tabela é pequena (poucas
centenas/milhares de linhas esperadas) — o problema de volume que tirou a folha
do Supabase não se repete aqui.
"""
from __future__ import annotations

from typing import Any, Iterable

from psycopg2.extras import execute_values

from .matcher import CandidatoConflito


class CandidatoConflitoRepository:
    """INSERT em lote via execute_values — nunca linha a linha (mesma lição do
    domínio folha_pagamento). Idempotente via ON CONFLICT (fornecedor_ni,
    matricula_servidor) DO NOTHING: rodar de novo não duplica candidatos.
    """

    def __init__(self, conn: Any, batch_size: int = 500):
        self._conn = conn
        self._batch_size = batch_size

    def salvar_candidatos(self, candidatos: Iterable[CandidatoConflito]) -> int:
        valores = [
            (
                c.fornecedor_ni,
                c.nome_socio,
                c.qualificacao_socio,
                c.matricula_servidor,
                c.nome_servidor,
                c.sigla_ua,
                c.score_similaridade,
            )
            for c in candidatos
        ]
        if not valores:
            return 0

        cur = self._conn.cursor()
        inseridos = execute_values(
            cur,
            """INSERT INTO candidatos_conflito_interesse (
                   fornecedor_ni, nome_socio, qualificacao_socio,
                   matricula_servidor, nome_servidor, sigla_ua,
                   score_similaridade
               ) VALUES %s
               ON CONFLICT (fornecedor_ni, matricula_servidor) DO NOTHING
               RETURNING id""",
            valores,
            page_size=self._batch_size,
            fetch=True,
        )
        self._conn.commit()
        return len(inseridos)
