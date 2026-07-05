-- Schema Postgres/Supabase de candidatos a conflito de interesse.
-- Projeto Supabase sentinela-dados-publicos (mesmo já usado pelo domínio folha_pagamento).
-- Tabela pequena (poucas centenas/milhares de linhas esperadas) — não repete o
-- problema de volume que tirou o dado bruto de folha do Supabase.

CREATE TABLE IF NOT EXISTS candidatos_conflito_interesse (
    id                             SERIAL PRIMARY KEY,
    fornecedor_ni                  TEXT NOT NULL,
    nome_socio                     TEXT NOT NULL,
    qualificacao_socio             TEXT,
    matricula_servidor             TEXT NOT NULL,
    nome_servidor                  TEXT NOT NULL,
    sigla_ua                       TEXT,
    score_similaridade             NUMERIC(5,2) NOT NULL,
    data_entrada_sociedade         DATE,
    faixa_etaria_socio             TEXT,
    primeira_competencia_servidor  DATE,
    status                         TEXT NOT NULL DEFAULT 'aberto',
    detectado_em                   TIMESTAMP NOT NULL DEFAULT now(),
    revisado_em                    TIMESTAMP,
    UNIQUE (fornecedor_ni, matricula_servidor)
);

-- Migração para tabelas já existentes no Supabase (criadas antes de 2026-07):
-- rodar manualmente no SQL Editor do projeto Supabase, ADD COLUMN IF NOT
-- EXISTS torna seguro repetir mesmo se a tabela já tiver essas colunas.
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS data_entrada_sociedade DATE;
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS faixa_etaria_socio TEXT;
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS primeira_competencia_servidor DATE;
