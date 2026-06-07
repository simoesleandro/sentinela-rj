"""
Conexão e inicialização do banco de dados Sentinela RJ.
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sentinela_rj.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_conn(row_factory: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn


def init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    # Migrações de coluna — ignoradas se já existirem (SQLite não suporta IF NOT EXISTS em ADD COLUMN)
    for stmt in [
        "ALTER TABLE fornecedores ADD COLUMN tem_sancao INTEGER DEFAULT 0",
        "ALTER TABLE fornecedores ADD COLUMN ultima_consulta_sancao TEXT",
        "ALTER TABLE fornecedores ADD COLUMN capital_social REAL",
        "ALTER TABLE fornecedores ADD COLUMN data_inicio_atividade TEXT",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    return conn
