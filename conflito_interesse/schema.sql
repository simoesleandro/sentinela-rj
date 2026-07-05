-- Schema Postgres/Supabase de candidatos a conflito de interesse.
-- Projeto Supabase sentinela-dados-publicos (mesmo já usado pelo domínio folha_pagamento).
-- Tabela pequena (poucas centenas/milhares de linhas esperadas) — não repete o
-- problema de volume que tirou o dado bruto de folha do Supabase.

CREATE TABLE IF NOT EXISTS candidatos_conflito_interesse (
    id                    SERIAL PRIMARY KEY,
    fornecedor_ni         TEXT NOT NULL,
    nome_socio            TEXT NOT NULL,
    qualificacao_socio    TEXT,
    matricula_servidor    TEXT NOT NULL,
    nome_servidor         TEXT NOT NULL,
    sigla_ua              TEXT,
    score_similaridade    NUMERIC(5,2) NOT NULL,
    status                TEXT NOT NULL DEFAULT 'aberto',
    detectado_em          TIMESTAMP NOT NULL DEFAULT now(),
    revisado_em           TIMESTAMP,
    UNIQUE (fornecedor_ni, matricula_servidor)
);
