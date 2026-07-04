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
    tipo_folha                  TEXT NOT NULL,
    remuneracao_bruta           NUMERIC(12,2),
    desconto_previdencia        NUMERIC(12,2),
    desconto_ir                 NUMERIC(12,2),
    outros_descontos            NUMERIC(12,2),
    desconto_excedente_teto     NUMERIC(12,2),
    remuneracao_liquida         NUMERIC(12,2),
    UNIQUE (matricula, tipo_folha, competencia)
);
