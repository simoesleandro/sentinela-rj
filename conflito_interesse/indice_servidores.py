"""Índice em memória de servidores por primeiro token do nome normalizado.

286k servidores, nomes curtos — cabe tudo em RAM. Construído uma vez e reutilizado
para todas as buscas do ConflictMatcherService, em vez de consultar o SQLite por
sócio (o que seria uma query por fornecedor x sócio).

Bloqueio pelo PRIMEIRO token (prenome). Chegou a ser trocado para o último token
(sobrenome) sob a hipótese de que prenomes comuns (MARIA, JOSE, JOAO...) geram
blocos grandes demais — mas nos dados reais dessa base os sobrenomes são AINDA
mais concentrados (SILVA: 29.475 ocorrências, SANTOS: 15.651, contra MARIA: 14.672
pelo primeiro token), e bloquear pelo último token gerou mais ruído, não menos
(1368 candidatos contra 972, 1288 contra 917 na faixa 80-89). Revertido para
primeiro token por decisão de operação — a fila de triagem manual precisa ser
gerenciável.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from .normalizador import normalizar_nome


class IndiceServidoresPorToken:
    """dict {primeiro_token_normalizado: [(matricula, nome_normalizado), ...]}."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._indice: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for matricula, nome in conn.execute("SELECT matricula, nome_atual FROM servidores"):
            nome_normalizado = normalizar_nome(nome)
            if not nome_normalizado:
                continue
            primeiro_token = nome_normalizado.split(" ", 1)[0]
            self._indice[primeiro_token].append((matricula, nome_normalizado))

    def candidatos(self, primeiro_token: str) -> list[tuple[str, str]]:
        return self._indice.get(primeiro_token, [])

    def sigla_ua_mais_recente(self, matricula: str) -> str | None:
        """Órgão da competência mais recente daquela matrícula em folha_mensal."""
        row = self._conn.execute(
            "SELECT sigla_ua FROM folha_mensal WHERE matricula = ? "
            "ORDER BY competencia DESC LIMIT 1",
            (matricula,),
        ).fetchone()
        return row[0] if row else None
