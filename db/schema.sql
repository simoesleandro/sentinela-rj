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
    criado_em           TEXT DEFAULT (datetime('now')),
    narrativa_ia        TEXT
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

-- Índices
CREATE INDEX IF NOT EXISTS idx_sancoes_fornecedor    ON fornecedor_sancoes(fornecedor_ni);
CREATE INDEX IF NOT EXISTS idx_contratos_fornecedor  ON contratos(fornecedor_ni);
CREATE INDEX IF NOT EXISTS idx_contratos_orgao        ON contratos(orgao_cnpj);
CREATE INDEX IF NOT EXISTS idx_contratos_valor        ON contratos(valor_global);
CREATE INDEX IF NOT EXISTS idx_contratos_data_pub     ON contratos(data_publicacao_pncp);
CREATE INDEX IF NOT EXISTS idx_contratos_cipi         ON contratos(identificador_cipi);
CREATE INDEX IF NOT EXISTS idx_alertas_contrato       ON alertas(numero_controle_pncp);
CREATE INDEX IF NOT EXISTS idx_alertas_tipo           ON alertas(tipo);
