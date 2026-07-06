"""Selo de compatibilidade de data para triagem manual de candidatos.

Sem CPF utilizável dos dois lados, o match sócio x servidor nunca tem certeza
de identidade — o objetivo aqui não é aumentar certeza automática, e sim dar
ao revisor humano um sinal rápido de "essa combinação é biologicamente
implausível" (nome comum, provavelmente pessoas diferentes), sem jamais mudar
o status do candidato sozinho.
"""
from __future__ import annotations

import re
from datetime import date, datetime

IDADE_MINIMA_INGRESSO_SERVICO = 16

_RE_FAIXA = re.compile(r"(\d+)\s*a\s*(\d+)\s*anos", re.IGNORECASE)
_RE_MAIOR_QUE = re.compile(r"maior\s*que\s*(\d+)\s*anos", re.IGNORECASE)


def _idade_estimada(faixa_etaria: str | None) -> float | None:
    """Ponto médio da faixa etária (ex.: "51 a 60 anos" -> 55.5)."""
    if not faixa_etaria:
        return None
    m = _RE_FAIXA.search(faixa_etaria)
    if m:
        minimo, maximo = int(m.group(1)), int(m.group(2))
        return (minimo + maximo) / 2
    m = _RE_MAIOR_QUE.search(faixa_etaria)
    if m:
        return float(m.group(1))
    return None


def _ano(valor: str | date | datetime | None) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, (date, datetime)):
        return valor.year
    m = re.match(r"(\d{4})", str(valor))
    return int(m.group(1)) if m else None


def calcular_compatibilidade(
    faixa_etaria_socio: str | None,
    primeira_competencia_servidor: str | date | datetime | None,
    ano_referencia: int | None = None,
) -> str | None:
    """Retorna 'incompativel', 'compativel' ou None (dados insuficientes p/ calcular).

    'incompativel' indica que, pela faixa etária estimada do sócio, ele teria
    ingressado no serviço público com menos de 16 anos -- sinal de que o match
    provavelmente é coincidência de nome, não a mesma pessoa.
    """
    idade_estimada = _idade_estimada(faixa_etaria_socio)
    if idade_estimada is None:
        return None

    ano_primeira_competencia = _ano(primeira_competencia_servidor)
    if ano_primeira_competencia is None:
        return None

    ano_ref = ano_referencia if ano_referencia is not None else date.today().year
    ano_nascimento_estimado = ano_ref - idade_estimada
    idade_ingresso = ano_primeira_competencia - ano_nascimento_estimado

    if idade_ingresso < IDADE_MINIMA_INGRESSO_SERVICO:
        return "incompativel"
    return "compativel"
