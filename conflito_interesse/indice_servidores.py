"""Índice em memória de servidores por primeiro token do nome normalizado.

286k servidores, nomes curtos — cabe tudo em RAM. Construído uma vez e reutilizado
para todas as buscas do ConflictMatcherService, em vez de consultar o SQLite por
sócio (o que seria uma query por fornecedor x sócio).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from .normalizador import normalizar_nome


class IndiceServidoresPorToken:
    """dict {primeiro_token_normalizado: [(matricula, nome_normalizado), ...]}."""

    def __init__(self, conn: sqlite3.Connection):
        self._indice: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for matricula, nome in conn.execute("SELECT matricula, nome_atual FROM servidores"):
            nome_normalizado = normalizar_nome(nome)
            if not nome_normalizado:
                continue
            primeiro_token = nome_normalizado.split(" ", 1)[0]
            self._indice[primeiro_token].append((matricula, nome_normalizado))

    def candidatos(self, primeiro_token: str) -> list[tuple[str, str]]:
        return self._indice.get(primeiro_token, [])
