"""Especificação OpenAPI 3.0 da API pública do Sentinela RJ (v1).

Fonte única de verdade do contrato público — servida como JSON em
/api/v1/openapi.json e renderizada em /api/docs (Swagger UI). Só expõe os
endpoints de LEITURA; IA, admin e escrita continuam fora da API pública.
"""
from __future__ import annotations

API_VERSION = "1.0.0"

_PAGINACAO_PARAMS = [
    {
        "name": "page",
        "in": "query",
        "description": "Página (começa em 1).",
        "schema": {"type": "integer", "minimum": 1, "default": 1},
    },
    {
        "name": "per_page",
        "in": "query",
        "description": "Itens por página (máximo 100).",
        "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
    },
]

_MUNICIPIO_PARAM = {
    "name": "municipio_ibge",
    "in": "query",
    "description": "Filtra por código IBGE do município (ex.: 3304557 = Rio de Janeiro).",
    "schema": {"type": "string"},
}


def build_spec(server_url: str | None = None) -> dict:
    """Monta o documento OpenAPI. `server_url` fixa o host base (opcional)."""
    spec: dict = {
        "openapi": "3.0.3",
        "info": {
            "title": "Sentinela RJ — API pública",
            "version": API_VERSION,
            "description": (
                "API pública de leitura do Sentinela RJ: alertas de anomalia em "
                "contratos públicos, contratos monitorados e a precisão medida de "
                "cada detector. Dados abertos do PNCP, livres para reuso "
                "jornalístico e acadêmico. Somente leitura (GET); sem autenticação."
            ),
            "contact": {"name": "Sentinela RJ", "url": "https://sentinela-rj.fly.dev"},
            "license": {"name": "Dados abertos (PNCP)"},
        },
        "paths": {
            "/api/v1/alertas": {
                "get": {
                    "summary": "Lista alertas de anomalia",
                    "description": (
                        "Alertas gerados pelos detectores, com o contrato associado. "
                        "Filtre por tipo, severidade e município."
                    ),
                    "parameters": [
                        {
                            "name": "tipo",
                            "in": "query",
                            "description": "Tipo do detector (ex.: outlier_valor, "
                            "concentracao_fornecedor, sem_licitacao_dispensa).",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "severidade",
                            "in": "query",
                            "description": "Severidade do alerta.",
                            "schema": {
                                "type": "string",
                                "enum": ["alta", "media", "baixa"],
                            },
                        },
                        _MUNICIPIO_PARAM,
                        *_PAGINACAO_PARAMS,
                    ],
                    "responses": {
                        "200": {
                            "description": "Página de alertas.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/AlertasPage"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/contratos": {
                "get": {
                    "summary": "Lista contratos monitorados",
                    "description": "Contratos coletados do PNCP. Filtre por município "
                    "e por fornecedor (CNPJ).",
                    "parameters": [
                        _MUNICIPIO_PARAM,
                        {
                            "name": "fornecedor_ni",
                            "in": "query",
                            "description": "CNPJ do fornecedor (só dígitos).",
                            "schema": {"type": "string"},
                        },
                        *_PAGINACAO_PARAMS,
                    ],
                    "responses": {
                        "200": {
                            "description": "Página de contratos.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ContratosPage"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/precisao": {
                "get": {
                    "summary": "Precisão medida por detector",
                    "description": (
                        "Taxa de acerto de cada detector = confirmados / (confirmados "
                        "+ descartados), lida da triagem humana real. Detectores com "
                        "menos de `min_amostra` rótulos aparecem como "
                        "'amostra_insuficiente'."
                    ),
                    "responses": {
                        "200": {
                            "description": "Precisão por detector.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Precisao"}
                                }
                            },
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "Contrato": {
                    "type": "object",
                    "properties": {
                        "pncp": {"type": "string", "description": "Número de controle PNCP."},
                        "objeto": {"type": "string"},
                        "valor_global": {"type": "number", "nullable": True},
                        "data_assinatura": {"type": "string", "nullable": True},
                        "fornecedor_ni": {"type": "string", "nullable": True},
                        "fornecedor": {"type": "string", "nullable": True},
                        "orgao": {"type": "string", "nullable": True},
                        "municipio_nome": {"type": "string", "nullable": True},
                        "municipio_ibge": {"type": "string", "nullable": True},
                    },
                },
                "Alerta": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "tipo": {"type": "string"},
                        "severidade": {"type": "string"},
                        "score": {"type": "number", "nullable": True},
                        "descricao": {"type": "string", "nullable": True},
                        "valor_referencia": {"type": "number", "nullable": True},
                        "status": {"type": "string", "nullable": True},
                        "contrato": {"$ref": "#/components/schemas/Contrato"},
                    },
                },
                "Paginacao": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "per_page": {"type": "integer"},
                        "total": {"type": "integer"},
                        "pages": {"type": "integer"},
                    },
                },
                "AlertasPage": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Paginacao"},
                        {
                            "type": "object",
                            "properties": {
                                "items": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Alerta"},
                                }
                            },
                        },
                    ]
                },
                "ContratosPage": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Paginacao"},
                        {
                            "type": "object",
                            "properties": {
                                "items": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Contrato"},
                                }
                            },
                        },
                    ]
                },
                "PrecisaoItem": {
                    "type": "object",
                    "properties": {
                        "tipo": {"type": "string"},
                        "total": {"type": "integer"},
                        "confirmados": {"type": "integer"},
                        "descartados": {"type": "integer"},
                        "pendentes": {"type": "integer"},
                        "rotulados": {"type": "integer"},
                        "precisao": {
                            "type": "number",
                            "nullable": True,
                            "description": "Fração 0–1, ou null se amostra insuficiente.",
                        },
                        "amostra_status": {
                            "type": "string",
                            "enum": ["medida", "amostra_insuficiente"],
                        },
                    },
                },
                "Precisao": {
                    "type": "object",
                    "properties": {
                        "itens": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/PrecisaoItem"},
                        },
                        "min_amostra": {"type": "integer"},
                        "rotulados_total": {"type": "integer"},
                    },
                },
            }
        },
    }
    if server_url:
        spec["servers"] = [{"url": server_url}]
    return spec
