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
    matricula_servidor) DO UPDATE: rodar de novo não duplica candidatos, mas
    atualiza os sinais extras (data_entrada_sociedade, faixa_etaria_socio,
    primeira_competencia_servidor) dos já existentes — sem tocar status nem
    revisado_em, que pertencem exclusivamente ao fluxo de triagem manual
    (ConflitoTriagemRepository).
    """

    def __init__(self, conn: Any, batch_size: int = 500):
        self._conn = conn
        self._batch_size = batch_size

    def salvar_candidatos(self, candidatos: Iterable[CandidatoConflito]) -> int:
        candidatos_dedup = self._deduplicar(candidatos)
        valores = [
            (
                c.fornecedor_ni,
                c.nome_socio,
                c.qualificacao_socio,
                c.matricula_servidor,
                c.nome_servidor,
                c.sigla_ua,
                c.score_similaridade,
                c.data_entrada_sociedade,
                c.faixa_etaria_socio,
                c.primeira_competencia_servidor,
            )
            for c in candidatos_dedup
        ]
        if not valores:
            return 0

        cur = self._conn.cursor()
        afetados = execute_values(
            cur,
            """INSERT INTO candidatos_conflito_interesse (
                   fornecedor_ni, nome_socio, qualificacao_socio,
                   matricula_servidor, nome_servidor, sigla_ua,
                   score_similaridade, data_entrada_sociedade,
                   faixa_etaria_socio, primeira_competencia_servidor
               ) VALUES %s
               ON CONFLICT (fornecedor_ni, matricula_servidor) DO UPDATE SET
                   data_entrada_sociedade = EXCLUDED.data_entrada_sociedade,
                   faixa_etaria_socio = EXCLUDED.faixa_etaria_socio,
                   primeira_competencia_servidor = EXCLUDED.primeira_competencia_servidor
               RETURNING id""",
            valores,
            page_size=self._batch_size,
            fetch=True,
        )
        self._conn.commit()
        return len(afetados)

    @staticmethod
    def _deduplicar(candidatos: Iterable[CandidatoConflito]) -> list[CandidatoConflito]:
        """Um mesmo par (fornecedor_ni, matricula_servidor) pode aparecer mais de
        uma vez no lote (sócios diferentes do mesmo fornecedor batendo com o
        mesmo servidor) — o UNIQUE da tabela é só nesse par, então o Postgres
        rejeita UPSERT afetando a mesma linha duas vezes no mesmo comando
        (CardinalityViolation). Mantém o candidato de maior score por chave."""
        melhores: dict[tuple[str, str], CandidatoConflito] = {}
        for c in candidatos:
            chave = (c.fornecedor_ni, c.matricula_servidor)
            atual = melhores.get(chave)
            if atual is None or c.score_similaridade > atual.score_similaridade:
                melhores[chave] = c
        return list(melhores.values())
