"""
Sentinela RJ — Motor de análise de anomalias.

Interface pública:
    anomalias = analisar(conn)            -> list[AnomaliaResult]
    n = persistir_alertas(conn, anomalias) -> int  (rows inseridas)

Cada detector (outliers, concentracao, licitacao) devolve uma lista de
AnomaliaResult. O engine orquestra, ordena por score e expõe o resultado.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Literal


Severidade = Literal["baixa", "media", "alta"]


@dataclass
class AnomaliaResult:
    tipo: str
    """Categoria da anomalia: 'outlier_valor', 'concentracao_fornecedor',
    'sem_licitacao', 'fracionamento_ap'."""

    severidade: Severidade
    """Grau de urgência: 'baixa' / 'media' / 'alta'."""

    score: float
    """Risco normalizado 0.0–1.0. Usado para ordenar o relatório."""

    titulo: str
    """Título curto para o cabeçalho do relatório (≤ 80 chars)."""

    descricao: str
    """Explicação em linguagem clara, pronta para o relatório."""

    metodologia: str
    """Como chegamos nessa hipótese — necessário para auditoria e rigor."""

    contratos: list[str] = field(default_factory=list)
    """Lista de numero_controle_pncp envolvidos."""

    metricas: dict = field(default_factory=dict)
    """Números de suporte (ex: {'zscore': 13.2, 'media_categoria': 800000})."""

    valor_referencia: float | None = None
    """Valor monetário central da anomalia (para gravar em alertas.valor_referencia)."""


def analisar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    """
    Executa todos os detectores e devolve anomalias ordenadas por score desc.

    Os detectores ficam em módulos separados (outliers, concentracao, licitacao)
    para facilitar testes e adição de novos sem mexer aqui.
    """
    from analisador import outliers, concentracao, licitacao, sancoes, socios

    resultados: list[AnomaliaResult] = []
    resultados.extend(outliers.detectar(conn))
    resultados.extend(concentracao.detectar(conn))
    resultados.extend(licitacao.detectar(conn))
    resultados.extend(sancoes.detectar(conn))
    resultados.extend(socios.detectar(conn))

    resultados.sort(key=lambda a: a.score, reverse=True)
    return resultados


def persistir_alertas(conn: sqlite3.Connection, anomalias: list[AnomaliaResult]) -> int:
    """
    Grava anomalias na tabela `alertas`. Um row por contrato por anomalia.
    Retorna o número de rows inseridas.

    Não faz upsert intencional — cada chamada é um snapshot da análise.
    Limpar alertas antigos é responsabilidade do chamador se necessário.
    """
    salvos = 0
    for a in anomalias:
        for pncp_id in (a.contratos or [None]):
            conn.execute(
                """INSERT INTO alertas
                       (numero_controle_pncp, tipo, severidade,
                        descricao, metodologia, valor_referencia)
                   VALUES (?,?,?,?,?,?)""",
                (pncp_id, a.tipo, a.severidade,
                 a.descricao, a.metodologia, a.valor_referencia),
            )
            salvos += 1
    conn.commit()
    return salvos
