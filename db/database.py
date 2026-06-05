"""Persistência de despesas via sqlite3."""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "sentinela_rj.db"
_MEMORIA = ":memory:"
_TABELA_ANOMALIAS = "alertas"
_DDL_ANOMALIAS = """
CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_controle_pncp TEXT,
    tipo TEXT,
    severidade TEXT,
    descricao TEXT,
    metodologia TEXT,
    valor_referencia REAL,
    status TEXT DEFAULT 'aberto',
    criado_em TEXT DEFAULT (datetime('now')),
    narrativa_ia TEXT
)
"""


def _eh_banco_memoria(db_path: Path) -> bool:
    return str(db_path) == _MEMORIA


def _resolver_caminho_db(
    database_url: str | None,
    db_path: Path | None,
) -> Path:
    if db_path is not None:
        return db_path
    for candidato in (database_url, os.getenv("DB_PATH"), os.getenv("DATABASE_URL")):
        if not candidato or not str(candidato).strip():
            continue
        texto = str(candidato).strip()
        if texto.startswith("sqlite:///"):
            return Path(texto.removeprefix("sqlite:///"))
        if texto.startswith("sqlite://"):
            return Path(texto.removeprefix("sqlite://"))
        return Path(texto)
    return _DEFAULT_DB


def _validar_registros(registros: list[dict[str, Any]]) -> None:
    if not registros:
        raise ValueError("Lista vazia: nada a persistir.")


def _validar_nome_tabela(nome_tabela: str) -> str:
    nome = nome_tabela.strip()
    if not nome:
        raise ValueError("nome_tabela não pode ser vazio.")
    if not nome.replace("_", "").isalnum():
        raise ValueError(f"nome_tabela inválido: {nome_tabela!r}")
    return nome


def _extrair_colunas(registros: list[dict[str, Any]]) -> list[str]:
    colunas: list[str] = []
    vistas: set[str] = set()
    for registro in registros:
        for chave in registro:
            if chave not in vistas:
                vistas.add(chave)
                colunas.append(chave)
    return colunas


def _coluna_chave_primaria(colunas: list[str]) -> str:
    if "id" in colunas:
        return "id"
    return colunas[0]


def _ddl_criar_tabela(tabela: str, colunas: list[str], pk: str) -> str:
    defs = [
        f'"{c}" TEXT PRIMARY KEY' if c == pk else f'"{c}" TEXT'
        for c in colunas
    ]
    return f'CREATE TABLE IF NOT EXISTS "{tabela}" ({", ".join(defs)})'


def _sql_upsert(tabela: str, colunas: list[str]) -> str:
    cols = ", ".join(f'"{c}"' for c in colunas)
    placeholders = ", ".join("?" for _ in colunas)
    return f'INSERT OR REPLACE INTO "{tabela}" ({cols}) VALUES ({placeholders})'


def _serializar_valor(valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(valor, (bool, int, float, str, bytes)):
        return valor
    return str(valor)


def _montar_linhas(
    registros: list[dict[str, Any]],
    colunas: list[str],
) -> list[tuple[Any, ...]]:
    return [
        tuple(_serializar_valor(r.get(c)) for c in colunas)
        for r in registros
    ]


def _garantir_tabela_anomalias(conn: sqlite3.Connection) -> None:
    conn.execute(_DDL_ANOMALIAS.strip())
    colunas = {row[1] for row in conn.execute("PRAGMA table_info(alertas)")}
    if "narrativa_ia" not in colunas:
        conn.execute("ALTER TABLE alertas ADD COLUMN narrativa_ia TEXT")
    conn.commit()


def _executar_upsert(
    conn: sqlite3.Connection,
    tabela: str,
    colunas: list[str],
    registros: list[dict[str, Any]],
) -> None:
    pk = _coluna_chave_primaria(colunas)
    conn.execute(_ddl_criar_tabela(tabela, colunas, pk))
    conn.executemany(_sql_upsert(tabela, colunas), _montar_linhas(registros, colunas))
    conn.commit()


class GerenciadorBanco:
    """Gerencia persistência tabular de despesas em SQLite."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        db_path: Path | str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self._connection = connection
        self._owns_connection = connection is None
        self._db_path = _resolver_caminho_db(
            database_url,
            Path(db_path) if db_path is not None else None,
        )

    def _obter_conexao(self) -> sqlite3.Connection:
        if self._connection is not None:
            return self._connection
        if _eh_banco_memoria(self._db_path):
            self._connection = sqlite3.connect(_MEMORIA)
            return self._connection
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self._db_path)

    def salvar_despesas(
        self,
        registros: list[dict[str, Any]],
        nome_tabela: str,
    ) -> None:
        tabela = _validar_nome_tabela(nome_tabela)
        logger.info("Início da persistência em '%s'", tabela)
        _validar_registros(registros)
        colunas = _extrair_colunas(registros)
        conn = self._obter_conexao()
        try:
            _executar_upsert(conn, tabela, colunas, registros)
        except sqlite3.Error as exc:
            logger.error("Falha ao persistir despesas em '%s': %s", tabela, exc)
            raise
        finally:
            if self._owns_connection and not _eh_banco_memoria(self._db_path):
                conn.close()
        logger.info(
            "Persistência concluída: %d registros em '%s'",
            len(registros),
            tabela,
        )

    def garantir_tabela_anomalias(self) -> None:
        conn = self._obter_conexao()
        try:
            _garantir_tabela_anomalias(conn)
        except sqlite3.Error as exc:
            logger.error("Falha ao garantir tabela '%s': %s", _TABELA_ANOMALIAS, exc)
            raise
        finally:
            if self._owns_connection and not _eh_banco_memoria(self._db_path):
                conn.close()

    def listar_anomalias_sem_narrativa(
        self,
        limite: int = 10,
    ) -> list[dict[str, Any]]:
        self.garantir_tabela_anomalias()
        conn = self._obter_conexao()
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                """
                SELECT a.id, a.numero_controle_pncp, a.tipo, a.severidade,
                       a.descricao, a.metodologia, a.valor_referencia, a.status,
                       COALESCE(c.objeto, '') AS objeto,
                       COALESCE(c.valor_global, 0) AS valor_global,
                       COALESCE(f.razao_social, '') AS fornecedor
                FROM alertas a
                LEFT JOIN contratos c
                       ON c.numero_controle_pncp = a.numero_controle_pncp
                LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
                WHERE a.narrativa_ia IS NULL OR TRIM(a.narrativa_ia) = ''
                ORDER BY CASE a.severidade
                         WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END,
                         a.valor_referencia DESC, a.id DESC
                LIMIT ?
                """,
                (limite,),
            )
            return [dict(linha) for linha in cur.fetchall()]
        except sqlite3.Error as exc:
            logger.error("Falha ao listar anomalias sem narrativa: %s", exc)
            raise
        finally:
            if self._owns_connection and not _eh_banco_memoria(self._db_path):
                conn.close()

    def atualizar_narrativa_anomalia(self, id_anomalia: int, texto: str) -> None:
        if id_anomalia <= 0:
            raise ValueError("id_anomalia deve ser positivo.")
        narrativa = texto.strip()
        if not narrativa:
            raise ValueError("texto da narrativa não pode ser vazio.")
        self.garantir_tabela_anomalias()
        conn = self._obter_conexao()
        try:
            cur = conn.execute(
                f'UPDATE "{_TABELA_ANOMALIAS}" SET narrativa_ia = ? WHERE id = ?',
                (narrativa, id_anomalia),
            )
            conn.commit()
            if cur.rowcount == 0:
                raise ValueError(f"Anomalia não encontrada: id={id_anomalia}")
        except sqlite3.Error as exc:
            logger.error(
                "Falha ao atualizar narrativa (id=%s): %s",
                id_anomalia,
                exc,
            )
            raise
        finally:
            if self._owns_connection and not _eh_banco_memoria(self._db_path):
                conn.close()
        logger.info("Narrativa IA salva para anomalia id=%s", id_anomalia)
