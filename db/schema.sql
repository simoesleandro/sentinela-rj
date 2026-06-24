-- Sentinela RJ — Schema do banco de dados
-- Aplicar com: conn.executescript(schema_sql)

CREATE TABLE IF NOT EXISTS orgaos (
    cnpj            TEXT PRIMARY KEY,
    razao_social    TEXT,
    poder_id        TEXT,           -- E/L/J (Executivo/Legislativo/Judiciário)
    esfera_id       TEXT,           -- F/E/M (Federal/Estadual/Municipal)
    municipio_nome  TEXT,
    municipio_ibge  TEXT,
    uf_sigla        TEXT,
    primeira_vez    TEXT DEFAULT (datetime('now')),
    atualizado_em   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fornecedores (
    ni              TEXT PRIMARY KEY,   -- CNPJ ou CPF
    tipo_pessoa     TEXT,               -- PJ/PF/PE
    razao_social    TEXT,
    primeira_vez    TEXT DEFAULT (datetime('now')),
    atualizado_em   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contratos (
    numero_controle_pncp        TEXT PRIMARY KEY,
    numero_controle_compra      TEXT,
    ano_contrato                INTEGER,
    sequencial_contrato         INTEGER,
    tipo_contrato_id            INTEGER,
    tipo_contrato_nome          TEXT,
    numero_contrato_empenho     TEXT,
    processo                    TEXT,

    orgao_cnpj                  TEXT REFERENCES orgaos(cnpj),
    fornecedor_ni               TEXT REFERENCES fornecedores(ni),

    municipio_ibge              TEXT,
    municipio_nome              TEXT,
    uf_sigla                    TEXT,
    esfera_id                   TEXT,
    poder_id                    TEXT,
    unidade_nome                TEXT,
    unidade_codigo              TEXT,

    objeto                      TEXT,
    categoria_processo_id       INTEGER,
    categoria_processo_nome     TEXT,
    informacao_complementar     TEXT,

    valor_inicial               REAL,
    valor_global                REAL,
    valor_acumulado             REAL,
    valor_parcela               REAL,
    numero_parcelas             INTEGER,
    receita                     INTEGER,    -- 0/1

    data_assinatura             TEXT,
    data_vigencia_inicio        TEXT,
    data_vigencia_fim           TEXT,
    data_publicacao_pncp        TEXT,
    data_atualizacao            TEXT,

    fruto_adesao                INTEGER,    -- 0/1 (adesão a ata de registro de preços)
    tem_remanejamento           INTEGER,    -- 0/1
    numero_retificacao          INTEGER,
    emenda_parlamentar          TEXT,       -- JSON
    identificador_cipi          TEXT,
    url_cipi                    TEXT,

    coletado_em                 TEXT DEFAULT (datetime('now')),
    raw_json                    TEXT
);

CREATE TABLE IF NOT EXISTS alertas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_controle_pncp TEXT REFERENCES contratos(numero_controle_pncp),
    tipo                TEXT,       -- 'outlier_valor', 'concentracao_fornecedor', 'sem_licitacao', 'fracionamento'
    severidade          TEXT,       -- 'baixa'/'media'/'alta'
    descricao           TEXT,
    metodologia         TEXT,
    valor_referencia    REAL,
    score               REAL,       -- risco normalizado 0.0-1.0 (AnomaliaResult.score)
    status              TEXT DEFAULT 'aberto',   -- aberto/investigando/confirmado/descartado
    notas_triagem       TEXT,
    status_atualizado_em TEXT,
    criado_em           TEXT DEFAULT (datetime('now')),
    narrativa_ia        TEXT
);

CREATE TABLE IF NOT EXISTS alertas_historico (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    alerta_id           INTEGER NOT NULL REFERENCES alertas(id) ON DELETE CASCADE,
    status_anterior     TEXT,
    status_novo         TEXT NOT NULL,
    nota                TEXT,
    criado_em           TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS coletas_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte               TEXT,
    data_inicial        TEXT,
    data_final          TEXT,
    paginas_lidas       INTEGER,
    registros_brutos    INTEGER,
    registros_municipio INTEGER,
    iniciado_em         TEXT,
    finalizado_em       TEXT,
    observacao          TEXT
);

CREATE TABLE IF NOT EXISTS fornecedor_sancoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fornecedor_ni       TEXT NOT NULL,
    fonte               TEXT NOT NULL,          -- 'CEIS', 'CNEP', 'CEPIM'
    tipo_sancao         TEXT,
    orgao_sancionador   TEXT,
    data_inicio         TEXT,
    data_fim            TEXT,
    descricao           TEXT,
    coletado_em         TEXT DEFAULT (datetime('now')),
    UNIQUE(fornecedor_ni, fonte, data_inicio)
);

CREATE TABLE IF NOT EXISTS fornecedor_cadastro (
    fornecedor_ni           TEXT PRIMARY KEY,
    situacao_cadastral      INTEGER,
    descricao_situacao      TEXT,
    data_inicio_atividade   TEXT,
    cnae_fiscal             INTEGER,
    cnae_fiscal_descricao   TEXT,
    capital_social          REAL,
    porte                   TEXT,
    natureza_juridica       TEXT,
    socios                  TEXT,               -- JSON serializado da lista qsa
    cnaes_secundarios       TEXT,               -- JSON serializado
    municipio               TEXT,
    uf                      TEXT,
    atualizado_em           TEXT
);

CREATE TABLE IF NOT EXISTS socios_compartilhados (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_socio          TEXT NOT NULL,
    fornecedores        TEXT NOT NULL,   -- JSON: lista de {ni, razao_social, valor_total}
    total_fornecedores  INTEGER,
    total_contratos     INTEGER,
    valor_total         REAL,
    detectado_em        TEXT DEFAULT (datetime('now')),
    UNIQUE(nome_socio)
);

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
);

CREATE TABLE IF NOT EXISTS regras_alerta (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo                TEXT,
    severidade_min      TEXT NOT NULL DEFAULT 'media'
        CHECK (severidade_min IN ('baixa', 'media', 'alta')),
    valor_min           REAL NOT NULL DEFAULT 0,
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transparencia_rj_lancamentos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fornecedor_ni       TEXT NOT NULL,
    valor               REAL,
    data_lancamento     TEXT,
    descricao           TEXT,
    orgao               TEXT,
    documento           TEXT,
    coletado_em         TEXT DEFAULT (datetime('now')),
    UNIQUE(fornecedor_ni, data_lancamento, valor, documento)
);

CREATE TABLE IF NOT EXISTS transparencia_rj_cruzamentos (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_controle_pncp    TEXT REFERENCES contratos(numero_controle_pncp),
    lancamento_id           INTEGER REFERENCES transparencia_rj_lancamentos(id),
    score                   REAL,
    detectado_em            TEXT DEFAULT (datetime('now')),
    UNIQUE(numero_controle_pncp, lancamento_id)
);

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
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_sancoes_fornecedor    ON fornecedor_sancoes(fornecedor_ni);
CREATE INDEX IF NOT EXISTS idx_contratos_fornecedor  ON contratos(fornecedor_ni);
CREATE INDEX IF NOT EXISTS idx_contratos_orgao        ON contratos(orgao_cnpj);
CREATE INDEX IF NOT EXISTS idx_contratos_valor        ON contratos(valor_global);
CREATE INDEX IF NOT EXISTS idx_contratos_data_pub     ON contratos(data_publicacao_pncp);
CREATE INDEX IF NOT EXISTS idx_contratos_cipi         ON contratos(identificador_cipi);
CREATE INDEX IF NOT EXISTS idx_alertas_contrato       ON alertas(numero_controle_pncp);
CREATE INDEX IF NOT EXISTS idx_alertas_tipo           ON alertas(tipo);
CREATE INDEX IF NOT EXISTS idx_alertas_status         ON alertas(status);
CREATE INDEX IF NOT EXISTS idx_alertas_historico      ON alertas_historico(alerta_id);
CREATE INDEX IF NOT EXISTS idx_watchlists_ativo       ON watchlists(ativo);
CREATE INDEX IF NOT EXISTS idx_watchlists_fornecedor  ON watchlists(fornecedor_ni);
CREATE INDEX IF NOT EXISTS idx_watchlists_orgao       ON watchlists(orgao_cnpj);
CREATE INDEX IF NOT EXISTS idx_regras_alerta_ativo    ON regras_alerta(ativo);
CREATE INDEX IF NOT EXISTS idx_regras_alerta_tipo     ON regras_alerta(tipo);
CREATE INDEX IF NOT EXISTS idx_transp_rj_fornecedor   ON transparencia_rj_lancamentos(fornecedor_ni);
CREATE INDEX IF NOT EXISTS idx_transp_rj_cruz_pncp    ON transparencia_rj_cruzamentos(numero_controle_pncp);
