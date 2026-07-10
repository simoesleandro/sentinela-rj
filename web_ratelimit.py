"""Rate limiting da API pública (flask-limiter).

Limita por IP os endpoints de leitura sob /api/v1. O storage é em memória
(por processo) — suficiente para o deploy do Fly, que roda tipicamente uma
máquina; se escalar horizontalmente, cada instância teria seu próprio balde
(limite efetivo = N × o configurado). Trocar por Redis se isso virar problema.

Atrás do proxy do Fly, request.remote_addr é o IP do proxy — todos os usuários
cairiam no mesmo balde. Por isso a chave usa o IP real do cliente, que o Fly
entrega no header Fly-Client-IP (com fallback para X-Forwarded-For).
"""
from __future__ import annotations

import os

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Limite por IP dos endpoints públicos de leitura. Configurável por env.
LIMITE_API_PUBLICA = os.environ.get("SENTINELA_API_RATELIMIT", "60 per minute")


def client_ip() -> str:
    """IP real do cliente atrás do proxy do Fly (Fly-Client-IP / XFF)."""
    fly = request.headers.get("Fly-Client-IP")
    if fly:
        return fly.strip()
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address()


# default_limits vazio: NADA é limitado por padrão — só as views que recebem
# @limiter.limit explicitamente (os endpoints públicos). O dashboard e as APIs
# internas (protegidas por sessão) ficam livres.
limiter = Limiter(
    key_func=client_ip,
    default_limits=[],
    storage_uri="memory://",
    headers_enabled=True,  # expõe X-RateLimit-* e Retry-After nas respostas
)
