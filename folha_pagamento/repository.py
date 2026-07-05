"""Persistência da folha de pagamento (Supabase/Postgres).

Interface de repositório separada da implementação para permitir testes sem
depender de uma instância real do Supabase (produção: psycopg2 + execute_values).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from psycopg2.extras import execute_values


@dataclass
class AgregadoFolhaMensal:
    """Uma linha de folha_mensal: já agregada por (matricula, competencia).

    Produzida pelo PayrollImportService a partir dos RegistroFolha crus do CSV
    (que podem ter várias linhas por matrícula/mês, uma por tipo_folha).
    """

    matricula: str
    sigla_ua: str
    competencia: date
    remuneracao_bruta_total: float
    excedeu_teto: bool


class FolhaPagamentoRepository(ABC):
    @abstractmethod
    def upsert_servidores_em_lote(self, itens: Iterable[tuple[str, str]]) -> None:
        ...

    @abstractmethod
    def upsert_orgaos_em_lote(self, itens: Iterable[tuple[str, str | None]]) -> None:
        ...

    @abstractmethod
    def insert_folha_mensal(self, registros: Iterable[AgregadoFolhaMensal]) -> int:
        """Insere registros agregados de folha mensal, ignorando conflitos de chave única.

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

    def insert_folha_mensal(self, registros: Iterable[AgregadoFolhaMensal]) -> int:
        cur = self._conn.cursor()
        valores = [
            (
                r.matricula, r.sigla_ua, r.competencia,
                r.remuneracao_bruta_total, r.excedeu_teto,
            )
            for r in registros
        ]
        inseridos = execute_values(
            cur,
            """INSERT INTO folha_mensal (
                   matricula, sigla_ua, competencia,
                   remuneracao_bruta_total, excedeu_teto
               ) VALUES %s
               ON CONFLICT (matricula, competencia) DO NOTHING
               RETURNING id""",
            valores,
            page_size=self._batch_size,
            fetch=True,
        )
        self._conn.commit()
        return len(inseridos)
