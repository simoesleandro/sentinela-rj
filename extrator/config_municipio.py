"""Configuração geográfica do monitoramento — zero hardcoding."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_PADRAO_IBGE = "3304557"
_PADRAO_ESFERA = "M"
_PADRAO_NOME = "Rio de Janeiro"


def municipio_ibge() -> str:
    return os.getenv("MUNICIPIO_IBGE", _PADRAO_IBGE).strip()


def municipio_esfera() -> str:
    return os.getenv("MUNICIPIO_ESFERA", _PADRAO_ESFERA).strip().upper()


def municipio_nome() -> str:
    return os.getenv("MUNICIPIO_NOME", _PADRAO_NOME).strip()


def rotulo_filtro() -> str:
    return f"IBGE {municipio_ibge()} ({municipio_nome()}) + esfera '{municipio_esfera()}'"
