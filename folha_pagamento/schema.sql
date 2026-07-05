-- Schema Postgres/Supabase da folha de pagamento (PCRJ).
-- Projeto Supabase dedicado, separado do restante do Sentinela (SQLite) e do
-- Supabase de outros projetos (dados pessoais não devem se misturar com dado cívico).

CREATE TABLE IF NOT EXISTS servidores (
    matricula       TEXT PRIMARY KEY,
    nome_atual      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orgaos (
    sigla_ua        TEXT PRIMARY KEY,
    nome            TEXT
);

CREATE TABLE IF NOT EXISTS folha_mensal (
    id                          SERIAL PRIMARY KEY,
    matricula                   TEXT NOT NULL REFERENCES servidores(matricula),
    sigla_ua                    TEXT NOT NULL REFERENCES orgaos(sigla_ua),
    competencia                 DATE NOT NULL,
    remuneracao_bruta_total     NUMERIC(12,2),
    excedeu_teto                BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (matricula, competencia)
);
