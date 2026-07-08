"""
Conexão e inicialização do banco de dados Sentinela RJ.
"""
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_DB_ENV = os.environ.get("DB_PATH", "")
if _DB_ENV:
    DB_PATH = Path(_DB_ENV)
else:
    DB_PATH = ROOT / "data" / "sentinela_rj.db"

# Garante que o diretório do banco exista antes de qualquer sqlite3.connect().
# Sem isso, abrir o banco em um checkout/deploy limpo (onde data/ ainda não foi
# criado) falha com "unable to open database file".
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

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
    """
    CREATE TABLE IF NOT EXISTS watchlists (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        fornecedor_ni           TEXT REFERENCES fornecedores(ni),
        orgao_cnpj              TEXT REFERENCES orgaos(cnpj),
        palavra_chave_objeto    TEXT,
        rotulo                  TEXT NOT NULL,
        ativo                   INTEGER NOT NULL DEFAULT 1,
        criado_em               TEXT DEFAULT (datetime('now')),
        CHECK (
            fornecedor_ni IS NOT NULL
            OR orgao_cnpj IS NOT NULL
            OR (palavra_chave_objeto IS NOT NULL AND TRIM(palavra_chave_objeto) != '')
        )
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_watchlists_ativo ON watchlists(ativo)",
    "CREATE INDEX IF NOT EXISTS idx_watchlists_fornecedor ON watchlists(fornecedor_ni)",
    "CREATE INDEX IF NOT EXISTS idx_watchlists_orgao ON watchlists(orgao_cnpj)",
    """
    CREATE TABLE IF NOT EXISTS regras_alerta (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo                TEXT,
        severidade_min      TEXT NOT NULL DEFAULT 'media'
            CHECK (severidade_min IN ('baixa', 'media', 'alta')),
        valor_min           REAL NOT NULL DEFAULT 0,
        ativo               INTEGER NOT NULL DEFAULT 1,
        criado_em           TEXT DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_regras_alerta_ativo ON regras_alerta(ativo)",
    "CREATE INDEX IF NOT EXISTS idx_regras_alerta_tipo ON regras_alerta(tipo)",
    """
    CREATE TABLE IF NOT EXISTS transparencia_rj_lancamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fornecedor_ni TEXT NOT NULL,
        valor REAL,
        data_lancamento TEXT,
        descricao TEXT,
        orgao TEXT,
        documento TEXT,
        coletado_em TEXT DEFAULT (datetime('now')),
        UNIQUE(fornecedor_ni, data_lancamento, valor, documento)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transparencia_rj_cruzamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_controle_pncp TEXT REFERENCES contratos(numero_controle_pncp),
        lancamento_id INTEGER REFERENCES transparencia_rj_lancamentos(id),
        score REAL,
        detectado_em TEXT DEFAULT (datetime('now')),
        UNIQUE(numero_controle_pncp, lancamento_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_transp_rj_fornecedor ON transparencia_rj_lancamentos(fornecedor_ni)",
    "CREATE INDEX IF NOT EXISTS idx_transp_rj_cruz_pncp ON transparencia_rj_cruzamentos(numero_controle_pncp)",
    """
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
    """,
    "CREATE INDEX IF NOT EXISTS idx_investigacoes_alerta ON investigacoes(alerta_id)",
    """
    CREATE TABLE IF NOT EXISTS casos (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo          TEXT NOT NULL,
        fornecedor_nome TEXT,
        fornecedor_cnpj TEXT,
        valor           REAL,
        tipo_anomalia   TEXT,
        status          TEXT NOT NULL DEFAULT 'ativo'
                            CHECK (status IN ('ativo', 'investigando', 'suspenso')),
        resumo          TEXT,
        ordem           INTEGER NOT NULL DEFAULT 0,
        criado_em       TEXT DEFAULT (datetime('now')),
        atualizado_em   TEXT DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        email             TEXT NOT NULL UNIQUE,
        nome              TEXT,
        senha_hash        TEXT NOT NULL,
        is_admin          INTEGER NOT NULL DEFAULT 0,
        email_verificado  INTEGER NOT NULL DEFAULT 0,
        token_verificacao TEXT,
        token_expira_em   TEXT,
        criado_em         TEXT DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ia_consumo (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
        endpoint    TEXT,
        criado_em   TEXT DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ia_consumo_usuario_dia ON ia_consumo(usuario_id, criado_em)",
]

_MIGRACOES_CASOS_CNPJ = [
    ("UPDATE casos SET fornecedor_cnpj = '05851921000181' "
     "WHERE fornecedor_cnpj IN ('12345678000190') "
     "OR (fornecedor_cnpj IS NULL AND titulo LIKE '%MJRE%')"),
    ("UPDATE casos SET fornecedor_cnpj = '07072702000120' "
     "WHERE fornecedor_cnpj IN ('98765432000155') "
     "OR (fornecedor_cnpj IS NULL AND titulo LIKE '%Bonus Track%')"),
    ("UPDATE casos SET fornecedor_cnpj = '30307631000119' "
     "WHERE fornecedor_cnpj IN ('11223344000177') "
     "OR (fornecedor_cnpj IS NULL AND titulo LIKE '%Entre os Rios%')"),
]

_MIGRACOES_COLUNAS = [
    "ALTER TABLE alertas ADD COLUMN notas_triagem TEXT",
    "ALTER TABLE alertas ADD COLUMN status_atualizado_em TEXT",
    "ALTER TABLE fornecedores ADD COLUMN tem_sancao INTEGER DEFAULT 0",
    "ALTER TABLE fornecedores ADD COLUMN ultima_consulta_sancao TEXT",
    "ALTER TABLE fornecedores ADD COLUMN capital_social REAL",
    "ALTER TABLE fornecedores ADD COLUMN data_inicio_atividade TEXT",
    "ALTER TABLE alertas ADD COLUMN score REAL",
    "ALTER TABLE alertas ADD COLUMN narrativa_gemma TEXT",
    "ALTER TABLE alertas ADD COLUMN gemma_utilizado INTEGER DEFAULT 0",
    "ALTER TABLE usuarios ADD COLUMN email_verificado INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE usuarios ADD COLUMN token_verificacao TEXT",
    "ALTER TABLE usuarios ADD COLUMN token_expira_em TEXT",
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
    for stmt in _MIGRACOES_CASOS_CNPJ:
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
