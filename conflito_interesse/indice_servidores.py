"""Índice em memória de servidores por último token (sobrenome) do nome normalizado.

286k servidores, nomes curtos — cabe tudo em RAM. Construído uma vez e reutilizado
para todas as buscas do ConflictMatcherService, em vez de consultar o SQLite por
sócio (o que seria uma query por fornecedor x sócio).

Bloqueio pelo ÚLTIMO token (sobrenome), não pelo primeiro: em nomes brasileiros o
primeiro token é majoritariamente um prenome comum (JOSE, MARIA, JOAO...), o que
gera blocos enormes e ruído na faixa de score 80-89. O último token varia mais e
produz blocos menores e mais discriminativos.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from .normalizador import normalizar_nome


class IndiceServidoresPorToken:
    """dict {ultimo_token_normalizado: [(matricula, nome_normalizado), ...]}."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._indice: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for matricula, nome in conn.execute("SELECT matricula, nome_atual FROM servidores"):
            nome_normalizado = normalizar_nome(nome)
            if not nome_normalizado:
                continue
            ultimo_token = nome_normalizado.rsplit(" ", 1)[-1]
            self._indice[ultimo_token].append((matricula, nome_normalizado))

    def candidatos(self, ultimo_token: str) -> list[tuple[str, str]]:
        return self._indice.get(ultimo_token, [])

    def sigla_ua_mais_recente(self, matricula: str) -> str | None:
        """Órgão da competência mais recente daquela matrícula em folha_mensal."""
        row = self._conn.execute(
            "SELECT sigla_ua FROM folha_mensal WHERE matricula = ? "
            "ORDER BY competencia DESC LIMIT 1",
            (matricula,),
        ).fetchone()
        return row[0] if row else None
