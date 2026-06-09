"""
Conexão e inicialização do banco de dados Sentinela RJ.
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sentinela_rj.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

_MIGRACOES_DDL = [
    """
    CREATE TABLE IF NOT EXISTS alertas_historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alerta_id INTEGER NOT NULL REFERENCES alertas(id) ON DELETE CASCADE,
        status_anterior TEXT,
        status_novo TEXT NOT NULL,
        nota TEXT,
        criado_em TEXT DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_alertas_historico ON alertas_historico(alerta_id)",
    "CREATE INDEX IF NOT EXISTS idx_alertas_status ON alertas(status)",
]

_MIGRACOES_COLUNAS = [
    "ALTER TABLE alertas ADD COLUMN notas_triagem TEXT",
    "ALTER TABLE alertas ADD COLUMN status_atualizado_em TEXT",
    "ALTER TABLE fornecedores ADD COLUMN tem_sancao INTEGER DEFAULT 0",
    "ALTER TABLE fornecedores ADD COLUMN ultima_consulta_sancao TEXT",
    "ALTER TABLE fornecedores ADD COLUMN capital_social REAL",
    "ALTER TABLE fornecedores ADD COLUMN data_inicio_atividade TEXT",
    "ALTER TABLE alertas ADD COLUMN score REAL",
]


def aplicar_migracoes(conn: sqlite3.Connection) -> None:
    """Aplica DDL/colunas incrementais (idempotente)."""
    for stmt in _MIGRACOES_DDL:
        conn.execute(stmt)
    for stmt in _MIGRACOES_COLUNAS:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.execute(
        """
        UPDATE alertas
        SET status = 'aberto'
        WHERE status IS NULL OR TRIM(status) = ''
        """
    )
    conn.commit()


def get_conn(row_factory: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn


def init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    aplicar_migracoes(conn)
    return conn
