"""Triagem de candidatos a conflito de interesse (Supabase/Postgres).

Implementa o mesmo Protocol TriagemRepository (db.triagem_core) usado por
AlertaTriagemRepository, reaproveitando a máquina de estados genérica
(normalizar_status/validar_transicao) — só a persistência muda (Postgres,
tabela candidatos_conflito_interesse, sem tabela de histórico ainda).
"""
from __future__ import annotations

from typing import Any, Iterable

from db.triagem_core import (
    STATUS_DESCARTADO,
    TriagemError,
    normalizar_status,
    validar_transicao,
)

MOTIVOS_DESCARTE_PADRAO: tuple[str, ...] = (
    "nome coincidente, pessoas diferentes",
    "servidor nao esta mais ativo",
    "sem vinculo real identificado",
)


class CandidatoConflitoNaoEncontradoError(LookupError):
    """Candidato a conflito de interesse inexistente."""


class ConflitoTriagemRepository:
    """Triagem para candidatos_conflito_interesse via Postgres/Supabase.

    A tabela de histórico ainda não existe no lado Postgres, então
    registrar_historico() é um no-op por enquanto (TODO abaixo).
    """

    def __init__(
        self,
        conn: Any,
        motivos_descarte: Iterable[str] | None = None,
    ):
        self._conn = conn
        self._motivos_descarte = frozenset(
            m.strip().lower() for m in (motivos_descarte or MOTIVOS_DESCARTE_PADRAO)
        )

    def _status_atual(self, id: int) -> str:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT status FROM candidatos_conflito_interesse WHERE id = %s",
            (id,),
        )
        row = cur.fetchone()
        if row is None:
            raise CandidatoConflitoNaoEncontradoError(
                f"Candidato a conflito de interesse não encontrado: id={id}"
            )
        return normalizar_status(row[0])

    def atualizar_status(
        self,
        id: int,
        novo_status: str,
        nota: str | None = None,
        motivo_descarte: str | None = None,
    ) -> None:
        anterior = self._status_atual(id)
        novo = normalizar_status(novo_status)

        if anterior != novo:
            validar_transicao(anterior, novo)

        if novo == STATUS_DESCARTADO and anterior != STATUS_DESCARTADO:
            motivo = (motivo_descarte or "").strip().lower()
            if not motivo:
                raise TriagemError(
                    "Informe o motivo do descarte (feedback de falso positivo)."
                )
            if motivo not in self._motivos_descarte:
                raise TriagemError(
                    f"Motivo inválido: '{motivo}'. "
                    f"Use: {', '.join(sorted(self._motivos_descarte))}."
                )

        cur = self._conn.cursor()
        cur.execute(
            """
            UPDATE candidatos_conflito_interesse
            SET status = %s, revisado_em = now()
            WHERE id = %s
            """,
            (novo, id),
        )
        self._conn.commit()

    def registrar_historico(
        self,
        id: int,
        status_anterior: str,
        status_novo: str,
        nota: str | None = None,
    ) -> None:
        # TODO: sem tabela de histórico no Postgres ainda (ver
        # conflito_interesse/schema.sql). Implementar quando a auditoria de
        # triagem de conflito de interesse virar requisito — por ora, a
        # única trilha é revisado_em na própria linha.
        return None

    def resumo_status(self) -> dict[str, int]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT status, COUNT(*) FROM candidatos_conflito_interesse GROUP BY status"
        )
        return {normalizar_status(status): int(n) for status, n in cur.fetchall()}
