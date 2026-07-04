"""Persistência da folha de pagamento (Supabase/Postgres).

Interface de repositório separada da implementação para permitir testes com
uma conexão DBAPI qualquer (produção: psycopg2 contra o Postgres do Supabase).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from .parser import RegistroFolha


class FolhaPagamentoRepository(ABC):
    @abstractmethod
    def upsert_servidor(self, matricula: str, nome: str) -> None:
        ...

    @abstractmethod
    def upsert_orgao(self, sigla_ua: str, nome: str | None) -> None:
        ...

    @abstractmethod
    def insert_folha_mensal(self, registros: Iterable[RegistroFolha]) -> int:
        """Insere registros de folha mensal, ignorando conflitos de chave única.

        Returns:
            Número de linhas efetivamente inseridas (exclui as ignoradas por conflito).
        """


class SupabaseFolhaPagamentoRepository(FolhaPagamentoRepository):
    """Implementação sobre uma conexão DBAPI (psycopg2) ao Postgres do Supabase.

    PLACEHOLDER é definido como atributo de classe (em vez de fixo em '%s') para
    permitir testes com sqlite3 (paramstyle '?'), que suporta a mesma sintaxe
    ON CONFLICT ... DO NOTHING usada aqui.
    """

    PLACEHOLDER = "%s"

    def __init__(self, conn: Any):
        self._conn = conn

    def upsert_servidor(self, matricula: str, nome: str) -> None:
        p = self.PLACEHOLDER
        cur = self._conn.cursor()
        cur.execute(
            f"""INSERT INTO servidores (matricula, nome_atual) VALUES ({p}, {p})
                ON CONFLICT (matricula) DO UPDATE SET nome_atual = EXCLUDED.nome_atual""",
            (matricula, nome),
        )
        self._conn.commit()

    def upsert_orgao(self, sigla_ua: str, nome: str | None) -> None:
        p = self.PLACEHOLDER
        cur = self._conn.cursor()
        cur.execute(
            f"""INSERT INTO orgaos (sigla_ua, nome) VALUES ({p}, {p})
                ON CONFLICT (sigla_ua) DO UPDATE SET nome = EXCLUDED.nome""",
            (sigla_ua, nome),
        )
        self._conn.commit()

    def insert_folha_mensal(self, registros: Iterable[RegistroFolha]) -> int:
        p = self.PLACEHOLDER
        sql = f"""
            INSERT INTO folha_mensal (
                matricula, sigla_ua, competencia, tipo_folha,
                remuneracao_bruta, desconto_previdencia, desconto_ir,
                outros_descontos, desconto_excedente_teto, remuneracao_liquida
            ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            ON CONFLICT (matricula, tipo_folha, competencia) DO NOTHING
        """
        cur = self._conn.cursor()
        inseridos = 0
        for r in registros:
            cur.execute(
                sql,
                (
                    r.matricula,
                    r.sigla_ua,
                    r.competencia,
                    r.tipo_folha,
                    r.remuneracao_bruta,
                    r.desconto_previdencia,
                    r.desconto_ir,
                    r.outros_descontos,
                    r.desconto_excedente_teto,
                    r.remuneracao_liquida,
                ),
            )
            if cur.rowcount > 0:
                inseridos += 1
        self._conn.commit()
        return inseridos
