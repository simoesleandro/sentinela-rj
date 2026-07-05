"""Persistência da folha de pagamento (Supabase/Postgres).

Interface de repositório separada da implementação para permitir testes sem
depender de uma instância real do Supabase (produção: psycopg2 + execute_values).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from psycopg2.extras import execute_values

from .parser import RegistroFolha


class FolhaPagamentoRepository(ABC):
    @abstractmethod
    def upsert_servidores_em_lote(self, itens: Iterable[tuple[str, str]]) -> None:
        ...

    @abstractmethod
    def upsert_orgaos_em_lote(self, itens: Iterable[tuple[str, str | None]]) -> None:
        ...

    @abstractmethod
    def insert_folha_mensal(self, registros: Iterable[RegistroFolha]) -> int:
        """Insere registros de folha mensal, ignorando conflitos de chave única.

        Returns:
            Número de linhas efetivamente inseridas (exclui as ignoradas por conflito).
        """


class SupabaseFolhaPagamentoRepository(FolhaPagamentoRepository):
    """Implementação em lote (execute_values) sobre psycopg2, contra o Postgres do Supabase.

    Em volumes de ~230 mil linhas/mês, inserir linha a linha significa um round-trip
    de rede por linha — na prática horas. execute_values agrupa `batch_size` linhas por
    round-trip, reduzindo isso a dezenas/centenas de statements.

    ON CONFLICT ... DO NOTHING não gera erro em reimportação, mas também não aparece no
    RETURNING — por isso insert_folha_mensal usa `RETURNING id` + `fetch=True`: é o único
    jeito de saber quantas linhas foram REALMENTE inseridas quando execute_values divide
    a carga em várias páginas internamente (cur.rowcount só refletiria a última página).
    """

    def __init__(self, conn: Any, batch_size: int = 2000):
        self._conn = conn
        self._batch_size = batch_size

    def upsert_servidores_em_lote(self, itens: Iterable[tuple[str, str]]) -> None:
        cur = self._conn.cursor()
        execute_values(
            cur,
            """INSERT INTO servidores (matricula, nome_atual) VALUES %s
               ON CONFLICT (matricula) DO UPDATE SET nome_atual = EXCLUDED.nome_atual""",
            list(itens),
            page_size=self._batch_size,
        )
        self._conn.commit()

    def upsert_orgaos_em_lote(self, itens: Iterable[tuple[str, str | None]]) -> None:
        cur = self._conn.cursor()
        execute_values(
            cur,
            """INSERT INTO orgaos (sigla_ua, nome) VALUES %s
               ON CONFLICT (sigla_ua) DO UPDATE SET nome = EXCLUDED.nome""",
            list(itens),
            page_size=self._batch_size,
        )
        self._conn.commit()

    def insert_folha_mensal(self, registros: Iterable[RegistroFolha]) -> int:
        cur = self._conn.cursor()
        valores = [
            (
                r.matricula, r.sigla_ua, r.competencia, r.tipo_folha,
                r.remuneracao_bruta, r.desconto_previdencia, r.desconto_ir,
                r.outros_descontos, r.desconto_excedente_teto, r.remuneracao_liquida,
            )
            for r in registros
        ]
        inseridos = execute_values(
            cur,
            """INSERT INTO folha_mensal (
                   matricula, sigla_ua, competencia, tipo_folha,
                   remuneracao_bruta, desconto_previdencia, desconto_ir,
                   outros_descontos, desconto_excedente_teto, remuneracao_liquida
               ) VALUES %s
               ON CONFLICT (matricula, tipo_folha, competencia) DO NOTHING
               RETURNING id""",
            valores,
            page_size=self._batch_size,
            fetch=True,
        )
        self._conn.commit()
        return len(inseridos)
