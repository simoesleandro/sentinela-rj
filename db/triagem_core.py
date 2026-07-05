"""Lógica pura da máquina de estados de triagem — sem I/O.

Extraído de db/triagem.py para ser reaproveitado por qualquer entidade que
precise de um fluxo aberto/investigando/confirmado/descartado, independente
do banco (SQLite, Postgres) ou da tabela de origem (alertas,
candidatos_conflito_interesse, etc.).
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

STATUS_ABERTO = "aberto"
STATUS_INVESTIGANDO = "investigando"
STATUS_CONFIRMADO = "confirmado"
STATUS_DESCARTADO = "descartado"

STATUS_VALIDOS: frozenset[str] = frozenset({
    STATUS_ABERTO,
    STATUS_INVESTIGANDO,
    STATUS_CONFIRMADO,
    STATUS_DESCARTADO,
})

TRANSICOES: dict[str, frozenset[str]] = {
    STATUS_ABERTO: frozenset({STATUS_INVESTIGANDO, STATUS_DESCARTADO}),
    STATUS_INVESTIGANDO: frozenset({
        STATUS_CONFIRMADO,
        STATUS_DESCARTADO,
        STATUS_ABERTO,
    }),
    STATUS_CONFIRMADO: frozenset({STATUS_INVESTIGANDO}),
    STATUS_DESCARTADO: frozenset({STATUS_ABERTO, STATUS_INVESTIGANDO}),
}


class TriagemError(ValueError):
    """Erro de validação na triagem."""


def normalizar_status(status: str | None) -> str:
    valor = (status or STATUS_ABERTO).strip().lower()
    return valor if valor in STATUS_VALIDOS else STATUS_ABERTO


def status_permitidos(status_atual: str | None) -> list[str]:
    atual = normalizar_status(status_atual)
    return sorted(TRANSICOES.get(atual, frozenset()))


def validar_transicao(atual: str, novo: str) -> None:
    if novo not in STATUS_VALIDOS:
        raise TriagemError(
            f"Status inválido: '{novo}'. Use: {', '.join(sorted(STATUS_VALIDOS))}."
        )
    permitidos = TRANSICOES.get(atual, frozenset())
    if novo not in permitidos:
        raise TriagemError(
            f"Transição '{atual}' → '{novo}' não permitida. "
            f"Opções: {', '.join(sorted(permitidos)) or 'nenhuma'}."
        )


@runtime_checkable
class TriagemRepository(Protocol):
    """Contrato comum para persistência de triagem, independente da entidade
    (alerta de contrato, candidato a conflito de interesse, etc.) ou do banco.
    """

    def atualizar_status(
        self, id: int, novo_status: str, nota: str | None = None
    ) -> None: ...

    def registrar_historico(
        self,
        id: int,
        status_anterior: str,
        status_novo: str,
        nota: str | None = None,
    ) -> None: ...

    def resumo_status(self) -> dict[str, Any]: ...
