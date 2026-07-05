"""Normalização de nomes para o match sócio x servidor.

Usada dos dois lados do match (nome_socio do fornecedor e nome_atual do servidor)
para que a comparação fuzzy compare texto no mesmo formato.
"""
from __future__ import annotations

import unicodedata

_PREPOSICOES = {"DE", "DA", "DO", "DOS"}


def normalizar_nome(nome: str | None) -> str:
    """Upper-case, remove acentos, remove DE/DA/DO/DOS como tokens soltos.

    Não reordena tokens — uma inversão de ordem (sobrenome antes do nome, por
    exemplo) permanece diferente aqui. Lidar com isso é responsabilidade do
    fuzzy matching (token_sort_ratio) no ConflictMatcherService, não do normalizador.
    """
    sem_acento = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode("ascii")
    tokens = [t for t in sem_acento.upper().split() if t not in _PREPOSICOES]
    return " ".join(tokens)
