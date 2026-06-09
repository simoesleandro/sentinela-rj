"""Grafo investigativo fornecedor ↔ órgão ↔ contratos ↔ sócios."""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

_RE_NOME = re.compile(r"\W+", re.UNICODE)
_LIMITE_CONTRATOS = 25
_LIMITE_SOCIOS = 20


class GrafoNaoEncontradoError(LookupError):
    """Entidade central ausente no banco."""


def _slug_socio(nome: str) -> str:
    base = _RE_NOME.sub("-", nome.strip().lower()).strip("-")
    return base[:60] or "desconhecido"


def _no(no_id: str, label: str, tipo: str, **meta: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"id": no_id, "label": label, "tipo": tipo}
    if meta:
        item["meta"] = meta
    return item


def _aresta(origem: str, destino: str, rotulo: str = "") -> dict[str, str]:
    edge: dict[str, str] = {"from": origem, "to": destino}
    if rotulo:
        edge["label"] = rotulo
    return edge


def _parse_socios(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        dados = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return dados if isinstance(dados, list) else []


def _adicionar_socios(
    nos: dict[str, dict[str, Any]],
    arestas: list[dict[str, str]],
    fornecedor_ni: str,
    socios_raw: str | None,
) -> None:
    for socio in _parse_socios(socios_raw)[:_LIMITE_SOCIOS]:
        nome = (socio.get("nome_socio") or "").strip()
        if len(nome) < 3:
            continue
        sid = f"socio:{_slug_socio(nome)}"
        if sid not in nos:
            nos[sid] = _no(sid, nome, "socio")
        arestas.append(_aresta(sid, f"fornecedor:{fornecedor_ni}", "sócio de"))


def montar_grafo_fornecedor(
    conn: sqlite3.Connection,
    fornecedor_ni: str,
) -> dict[str, list[dict[str, Any]]]:
    forn = conn.execute(
        "SELECT ni, razao_social FROM fornecedores WHERE ni = ?",
        (fornecedor_ni,),
    ).fetchone()
    if forn is None:
        raise GrafoNaoEncontradoError(f"Fornecedor não encontrado: {fornecedor_ni}")

    nos: dict[str, dict[str, Any]] = {}
    arestas: list[dict[str, str]] = []
    fid = f"fornecedor:{fornecedor_ni}"
    nos[fid] = _no(fid, forn["razao_social"] or fornecedor_ni, "fornecedor", ni=fornecedor_ni)

    contratos = conn.execute(
        """
        SELECT c.numero_controle_pncp, c.objeto, c.valor_global,
               c.orgao_cnpj, o.razao_social AS orgao_nome
        FROM contratos c
        LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
        WHERE c.fornecedor_ni = ? AND c.valor_global > 0
        ORDER BY c.valor_global DESC
        LIMIT ?
        """,
        (fornecedor_ni, _LIMITE_CONTRATOS),
    ).fetchall()

    for ct in contratos:
        pncp = ct["numero_controle_pncp"]
        cid = f"contrato:{pncp}"
        titulo = (ct["objeto"] or pncp)[:48]
        nos[cid] = _no(
            cid,
            titulo,
            "contrato",
            pncp=pncp,
            valor=ct["valor_global"],
        )
        arestas.append(_aresta(fid, cid, "executa"))

        orgao_cnpj = ct["orgao_cnpj"]
        if orgao_cnpj:
            oid = f"orgao:{orgao_cnpj}"
            if oid not in nos:
                nos[oid] = _no(
                    oid,
                    ct["orgao_nome"] or orgao_cnpj,
                    "orgao",
                    cnpj=orgao_cnpj,
                )
            arestas.append(_aresta(oid, cid, "publica"))

    cadastro = conn.execute(
        "SELECT socios FROM fornecedor_cadastro WHERE fornecedor_ni = ?",
        (fornecedor_ni,),
    ).fetchone()
    if cadastro:
        _adicionar_socios(nos, arestas, fornecedor_ni, cadastro["socios"])

    return {"nodes": list(nos.values()), "edges": arestas}


def montar_grafo_alerta(
    conn: sqlite3.Connection,
    alerta_id: int,
) -> dict[str, list[dict[str, Any]]]:
    row = conn.execute(
        """
        SELECT a.id, c.fornecedor_ni
        FROM alertas a
        LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
        WHERE a.id = ?
        """,
        (alerta_id,),
    ).fetchone()
    if row is None:
        raise GrafoNaoEncontradoError(f"Alerta não encontrado: id={alerta_id}")
    fornecedor_ni = row["fornecedor_ni"]
    if not fornecedor_ni:
        raise GrafoNaoEncontradoError(
            f"Alerta {alerta_id} sem fornecedor vinculado ao contrato."
        )
    dados = montar_grafo_fornecedor(conn, fornecedor_ni)
    dados["meta"] = {"alerta_id": alerta_id, "fornecedor_ni": fornecedor_ni}
    return dados
