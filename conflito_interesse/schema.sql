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
    contrato_ativo                 BOOLEAN NOT NULL DEFAULT FALSE,
    valor_total_contratos          NUMERIC(14,2),
    qtd_servidores_matched_mesmo_socio INTEGER NOT NULL DEFAULT 1,
    tem_alerta_severidade_alta     BOOLEAN NOT NULL DEFAULT FALSE,
    tem_sancao                     BOOLEAN NOT NULL DEFAULT FALSE,
    qtd_servidores_mesmo_nome      INTEGER NOT NULL DEFAULT 1,
    lotacao_orgao_contratante      BOOLEAN NOT NULL DEFAULT FALSE,
    analise_ia                     TEXT,
    analise_ia_em                  TIMESTAMP,
    analise_ia_provedor            TEXT,
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

-- Sinais de priorização (jul/2026): não provam identidade, só ordenam a fila
-- de revisão manual por relevância real (contrato vigente, valor, quantos
-- SERVIDORES DISTINTOS o MESMO sócio bateu). Não substituem score_similaridade.
--
-- A primeira versão deste sinal (deployada e depois corrigida no mesmo dia)
-- se chamava qtd_socios_matched_mesma_empresa e agrupava só por
-- fornecedor_ni — saturava (~97% dos candidatos com >=2) porque conta
-- qualquer sócio distinto da empresa batendo isoladamente com um servidor
-- diferente, o que reflete tamanho da empresa, não conflito sistêmico.
-- Agrupar por (fornecedor_ni, sócio) sozinho AINDA saturava (93.8%, dados
-- reais de jul/2026): sobrenome comum bate via fuzzy matching (score 80-84)
-- com dezenas de servidores de nome só parecido, que não são a mesma
-- pessoa. A versão final (conflito_interesse.enriquecimento) só conta
-- matches de nome EXATO (score 100) dentro do grupo — caiu para 13.2%
-- (128/972). O bloco abaixo renomeia a coluna em bancos que já rodaram a
-- versão antiga, e cria do zero em bancos que ainda não tinham nenhum dos
-- dois nomes.
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS contrato_ativo BOOLEAN DEFAULT FALSE;
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS valor_total_contratos NUMERIC(14,2);
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'candidatos_conflito_interesse'
          AND column_name = 'qtd_socios_matched_mesma_empresa'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'candidatos_conflito_interesse'
          AND column_name = 'qtd_servidores_matched_mesmo_socio'
    ) THEN
        ALTER TABLE candidatos_conflito_interesse
            RENAME COLUMN qtd_socios_matched_mesma_empresa TO qtd_servidores_matched_mesmo_socio;
    END IF;
END $$;
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS qtd_servidores_matched_mesmo_socio INTEGER NOT NULL DEFAULT 1;

-- Mais 3 sinais de priorização (jul/2026), também sem fonte externa nova:
-- tem_alerta_severidade_alta e tem_sancao cruzam com 'alertas'/'fornecedor_sancoes'
-- (evidência de irregularidade do fornecedor já existente, independente do
-- match de nome sócio-servidor). qtd_servidores_mesmo_nome é só informativo
-- pro revisor (quantos servidores de TODA a base, 286k, têm esse nome exato —
-- um nome comum dentro do próprio funcionalismo do Rio, ex. "LUIZ CARLOS
-- SILVA" com 28 homônimos, não deve ser lido como forte mesmo com match
-- exato) — não entra na fórmula de prioridade, só explicita pro humano o que
-- ele teria que descobrir manualmente.
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS tem_alerta_severidade_alta BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS tem_sancao BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS qtd_servidores_mesmo_nome INTEGER NOT NULL DEFAULT 1;

-- Lotação × órgão contratante (jul/2026): o sinal mais forte do domínio.
-- Cruza a raiz da sigla_ua do servidor (S/, E/, GM/, RS/...) com o prefixo de
-- órgão do campo `processo` dos contratos do fornecedor (SMS-PRO, SME-PRO...),
-- já que o PNCP registra todos os contratos da PCRJ sob o órgão genérico
-- "MUNICIPIO DE RIO DE JANEIRO". Medido em jul/2026: 118/966 candidatos
-- (12,2%). Mapa e limitações em conflito_interesse/lotacao.py.
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS lotacao_orgao_contratante BOOLEAN NOT NULL DEFAULT FALSE;

-- Parecer de IA sob demanda (jul/2026): sintetiza os sinais do candidato num
-- parecer estruturado (plausibilidade/confiança/análise/verificar) via cascata
-- Gemma4→Gemini→Groq do motor central. Persistido para não gastar cota de IA
-- repetida no mesmo candidato. A qualificação do sócio (84,7% da base é
-- "gestão") NÃO virou coluna nem prioridade — é derivada na serialização
-- (conflito_interesse/qualificacao.py) para não saturar a fila.
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS analise_ia TEXT;
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS analise_ia_em TIMESTAMP;
ALTER TABLE candidatos_conflito_interesse ADD COLUMN IF NOT EXISTS analise_ia_provedor TEXT;
