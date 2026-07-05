"""Persistência da folha de pagamento.

Dado bruto/histórico (dezenas de milhões de linhas em 60 meses) vive em SQLite
local (SqliteFolhaPagamentoRepository, data/folha_pagamento.db) — o mesmo padrão
dos outros bancos do projeto. Esse volume estourava o free tier de 500MB do
Supabase mesmo já agregado por matricula+competencia.

SupabaseFolhaPagamentoRepository é mantida para uma tabela futura, pequena, de
candidatos a conflito de interesse — que precisa ser consultada remotamente
pelo dashboard e por isso faz sentido morar no Supabase.

Interface de repositório separada da implementação para permitir testes sem
depender de uma instância real de banco.
"""
from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "folha_pagamento.db"


def get_conn() -> sqlite3.Connection:
    """Abre a conexão com data/folha_pagamento.db, criando a pasta se necessário."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


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


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS servidores (
    matricula       TEXT PRIMARY KEY,
    nome_atual      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orgaos (
    sigla_ua        TEXT PRIMARY KEY,
    nome            TEXT
);

CREATE TABLE IF NOT EXISTS folha_mensal (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula                   TEXT NOT NULL REFERENCES servidores(matricula),
    sigla_ua                    TEXT NOT NULL REFERENCES orgaos(sigla_ua),
    competencia                 TEXT NOT NULL,
    remuneracao_bruta_total     NUMERIC,
    excedeu_teto                INTEGER NOT NULL DEFAULT 0,
    UNIQUE (matricula, competencia)
);
"""


class SqliteFolhaPagamentoRepository(FolhaPagamentoRepository):
    """Implementação sobre sqlite3 (biblioteca padrão) — dado bruto/histórico local.

    Mesmo padrão dos outros bancos do projeto (um arquivo .db em data/). Usa
    executemany para os lotes, equivalente ao execute_values do psycopg2 adaptado
    ao paramstyle '?' do sqlite3. UNIQUE (matricula, competencia) + INSERT OR IGNORE
    garantem a mesma idempotência de reimportação que o ON CONFLICT DO NOTHING.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._conn.executescript(_SQLITE_SCHEMA)
        self._conn.commit()

    def upsert_servidores_em_lote(self, itens: Iterable[tuple[str, str]]) -> None:
        self._conn.executemany(
            """INSERT INTO servidores (matricula, nome_atual) VALUES (?, ?)
               ON CONFLICT (matricula) DO UPDATE SET nome_atual = excluded.nome_atual""",
            list(itens),
        )
        self._conn.commit()

    def upsert_orgaos_em_lote(self, itens: Iterable[tuple[str, str | None]]) -> None:
        self._conn.executemany(
            """INSERT INTO orgaos (sigla_ua, nome) VALUES (?, ?)
               ON CONFLICT (sigla_ua) DO UPDATE SET nome = excluded.nome""",
            list(itens),
        )
        self._conn.commit()

    def insert_folha_mensal(self, registros: Iterable[AgregadoFolhaMensal]) -> int:
        valores = [
            (
                r.matricula, r.sigla_ua, r.competencia.isoformat(),
                r.remuneracao_bruta_total, int(r.excedeu_teto),
            )
            for r in registros
        ]
        cur = self._conn.executemany(
            """INSERT OR IGNORE INTO folha_mensal (
                   matricula, sigla_ua, competencia,
                   remuneracao_bruta_total, excedeu_teto
               ) VALUES (?, ?, ?, ?, ?)""",
            valores,
        )
        self._conn.commit()
        return cur.rowcount if cur.rowcount >= 0 else 0
