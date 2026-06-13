"""Cria tabela investigacoes no banco Sentinela RJ."""
from __future__ import annotations

import sqlite3
from pathlib import Path

_DB = Path(__file__).resolve().parent / "data" / "sentinela_rj.db"

_DDL = """
CREATE TABLE IF NOT EXISTS investigacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alerta_id INTEGER NOT NULL REFERENCES alertas(id),
    status TEXT DEFAULT 'pendente',
    iniciado_em TEXT,
    concluido_em TEXT,
    evidencias TEXT,
    sintese TEXT,
    conclusao TEXT,
    grau_confianca TEXT,
    recomendacao TEXT,
    erro TEXT,
    criado_em TEXT DEFAULT (datetime('now'))
)
"""

_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_investigacoes_alerta "
    "ON investigacoes(alerta_id)"
)


def main() -> None:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB)
    try:
        conn.execute(_DDL)
        conn.execute(_IDX)
        conn.commit()
    finally:
        conn.close()
    print("OK — tabela investigacoes criada")


if __name__ == "__main__":
    main()
