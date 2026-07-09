"""Extrator de licitações (contratações) do PNCP — Sentinela RJ.

Complementa o extrator de contratos: enquanto `extrator/pncp.py` coleta o que
foi ASSINADO, este coleta os CERTAMES — valor estimado vs. homologado, situação
e itens (inclusive desertos/fracassados). É a matéria-prima do detector de
competição fraca (analisador/competicao.py).

Diferenças importantes em relação ao endpoint de contratos:
- /contratacoes/publicacao aceita filtro por município (codigoMunicipioIbge) e
  UF direto na API — sem varrer o Brasil inteiro;
- exige codigoModalidadeContratacao (uma modalidade por request) — iteramos as
  modalidades competitivas;
- a API de consulta NÃO expõe a quantidade de propostas recebidas (a lista de
  licitantes fica no sistema de origem) — por isso o detector usa proxies:
  desconto estimado→homologado e itens desertos.

Uso:
    python __main__.py licitacoes                      # últimos 6 meses
    python __main__.py licitacoes --inicio 20260101 --fim 20260630
"""
from __future__ import annotations

import sqlite3
import time
from datetime import date, timedelta

from extrator.config_municipio import municipios_monitorados
from extrator.pncp import _get

# Modalidades com disputa (Lei 14.133/2021, art. 28). Dispensa/inexigibilidade
# ficam de fora: competição fraca só faz sentido onde competição era esperada.
MODALIDADES_COMPETITIVAS: dict[int, str] = {
    4: "Concorrência - Eletrônica",
    5: "Concorrência - Presencial",
    6: "Pregão - Eletrônico",
    7: "Pregão - Presencial",
}

_ESFERA_MUNICIPAL = "M"
_TAM_PAGINA = 50  # máximo aceito pelo endpoint de contratações
_PAUSA_ITENS_S = 0.2


def _upsert_licitacao(conn: sqlite3.Connection, c: dict, ibge: str) -> None:
    orgao = c.get("orgaoEntidade") or {}
    conn.execute(
        """
        INSERT INTO licitacoes (
            numero_controle_pncp, orgao_cnpj, ano_compra, sequencial_compra,
            modalidade_id, modalidade_nome, situacao_nome, objeto,
            valor_estimado, valor_homologado, srp,
            data_publicacao, data_encerramento_proposta, municipio_ibge
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(numero_controle_pncp) DO UPDATE SET
            situacao_nome = excluded.situacao_nome,
            valor_homologado = excluded.valor_homologado,
            data_encerramento_proposta = excluded.data_encerramento_proposta
        """,
        (
            c.get("numeroControlePNCP"),
            orgao.get("cnpj"),
            c.get("anoCompra"),
            c.get("sequencialCompra"),
            c.get("modalidadeId"),
            c.get("modalidadeNome"),
            c.get("situacaoCompraNome"),
            c.get("objetoCompra"),
            c.get("valorTotalEstimado"),
            c.get("valorTotalHomologado"),
            1 if c.get("srp") else 0,
            (c.get("dataPublicacaoPncp") or "")[:10] or None,
            (c.get("dataEncerramentoProposta") or "")[:10] or None,
            ibge,
        ),
    )


def coletar(
    conn: sqlite3.Connection,
    data_inicial: str,
    data_final: str,
) -> dict:
    """Coleta licitações competitivas dos municípios monitorados (esfera M).

    data_inicial/data_final no formato AAAAMMDD. Retorna resumo por modalidade.
    """
    resumo: dict[str, int] = {"total": 0}
    for municipio in municipios_monitorados():
        for modalidade_id, modalidade_nome in MODALIDADES_COMPETITIVAS.items():
            pagina = 1
            while True:
                dados = _get(
                    "/contratacoes/publicacao",
                    {
                        "dataInicial": data_inicial,
                        "dataFinal": data_final,
                        "codigoModalidadeContratacao": modalidade_id,
                        # o código IBGE embute a UF — o filtro sozinho basta
                        "codigoMunicipioIbge": municipio.ibge,
                        "pagina": pagina,
                        "tamanhoPagina": _TAM_PAGINA,
                    },
                )
                registros = (dados or {}).get("data") or []
                for c in registros:
                    esfera = (c.get("orgaoEntidade") or {}).get("esferaId")
                    if esfera != _ESFERA_MUNICIPAL:
                        continue
                    _upsert_licitacao(conn, c, municipio.ibge)
                    resumo["total"] += 1
                    resumo[modalidade_nome] = resumo.get(modalidade_nome, 0) + 1
                if not dados or pagina >= dados.get("totalPaginas", 1):
                    break
                pagina += 1
    conn.commit()
    return resumo


def coletar_itens(conn: sqlite3.Connection, limite: int = 200) -> dict:
    """Coleta os itens das licitações ainda sem itens (1 request por compra).

    Necessário para o sinal de itens desertos/fracassados. `limite` controla o
    volume por execução — a coleta é incremental e idempotente.
    """
    pendentes = conn.execute(
        """
        SELECT numero_controle_pncp, orgao_cnpj, ano_compra, sequencial_compra
        FROM licitacoes
        WHERE itens_coletados_em IS NULL
        ORDER BY data_publicacao DESC
        LIMIT ?
        """,
        (limite,),
    ).fetchall()

    coletadas, itens_total = 0, 0
    for pncp_id, cnpj, ano, seq in pendentes:
        # Endpoint de itens vive na API "pncp" (não na "consulta")
        url = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens"
        try:
            dados = _get_absoluto(url, {"pagina": 1, "tamanhoPagina": 500})
        except RuntimeError:
            continue  # tenta na próxima execução
        itens = dados if isinstance(dados, list) else (dados or {}).get("data") or []
        for it in itens:
            conn.execute(
                """
                INSERT INTO licitacao_itens (
                    numero_controle_pncp, numero_item, descricao,
                    situacao_nome, quantidade, tem_resultado
                ) VALUES (?,?,?,?,?,?)
                ON CONFLICT(numero_controle_pncp, numero_item) DO UPDATE SET
                    situacao_nome = excluded.situacao_nome,
                    tem_resultado = excluded.tem_resultado
                """,
                (
                    pncp_id,
                    it.get("numeroItem"),
                    (it.get("descricao") or "")[:200],
                    it.get("situacaoCompraItemNome"),
                    it.get("quantidade"),
                    1 if it.get("temResultado") else 0,
                ),
            )
            itens_total += 1
        conn.execute(
            "UPDATE licitacoes SET itens_coletados_em = datetime('now') WHERE numero_controle_pncp = ?",
            (pncp_id,),
        )
        coletadas += 1
        conn.commit()
        time.sleep(_PAUSA_ITENS_S)

    return {"licitacoes_processadas": coletadas, "itens": itens_total, "pendentes_restantes": max(0, len(pendentes) - coletadas)}


def _get_absoluto(url: str, params: dict):
    """Mesma resiliência de extrator.pncp._get, mas para URL completa (a API de
    itens usa outro prefixo de path)."""
    import requests

    ultimo = None
    for i in range(5):
        try:
            r = requests.get(url, params=params, timeout=60)
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.json()
            if r.status_code in (204, 404):
                return None
            ultimo = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            ultimo = str(exc)
        time.sleep(min(2 * (i + 1), 10))
    raise RuntimeError(f"Falhou: {ultimo}")


def janela_padrao(meses: int = 6) -> tuple[str, str]:
    fim = date.today()
    inicio = fim - timedelta(days=30 * meses)
    return inicio.strftime("%Y%m%d"), fim.strftime("%Y%m%d")
