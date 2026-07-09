"""Detector de sócio-doador de campanha — Sentinela RJ.

Cruza os sócios (QSA/BrasilAPI) dos fornecedores com as doações de campanha do
TSE (extrator/tse.py). Confirma identidade por nome + os 6 dígitos do meio do
CPF: o QSA traz o CPF do sócio mascarado (``***MMMMMM**``) e a prestação de
contas do TSE traz o CPF COMPLETO do doador — quando o nome bate e os 6 dígitos
conferem, é a mesma pessoa com falso-positivo desprezível.

Natureza do sinal (importante para o enquadramento): doação de pessoa física é
LEGAL — isto não é indício de ilegalidade, e sim de ALINHAMENTO POLÍTICO entre
quem controla o fornecedor e quem exerce (ou disputou) mandato no município que
o contrata. É contexto para o dossiê, não acusação. O sinal ganha força quando
a doação foi para candidato do MESMO município que contrata a empresa,
sobretudo cargo do Executivo (que controla a contratação).

Efeito colateral valioso: cada match confirma o CPF completo do sócio e é
gravado em socios_cpf_confirmado — fechando a lacuna "sem CPF" que limitava o
conflito de interesse (conflito_interesse/).

Limitação de cobertura: só fornecedores com QSA enriquecido (fornecedor_cadastro)
entram no cruzamento. Enriquecer mais fornecedores aumenta os achados.
"""
from __future__ import annotations

import json
import re
import sqlite3

from analisador.engine import AnomaliaResult
from extrator.tse import normalizar_nome

_RE_MASCARA = re.compile(r"^\*{3}(\d{6})\*{2}$")   # ***981227** -> 981227
_CARGOS_EXECUTIVO = {"PREFEITO", "VICE-PREFEITO"}

_VALOR_CONTRATO_ALTA = 10_000_000


def _cpf_meio_da_mascara(mask: str | None) -> str | None:
    m = _RE_MASCARA.match((mask or "").strip())
    return m.group(1) if m else None


def _mascarar_cpf(cpf: str) -> str:
    """11 dígitos -> ***MMMMMM** (mesmo formato do QSA; não expõe início/fim)."""
    return f"***{cpf[3:9]}**" if len(cpf) == 11 else "***"


def _carregar_doacoes(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """doador_nome_norm -> lista de doações (com CPF completo)."""
    por_nome: dict[str, list[dict]] = {}
    for row in conn.execute(
        """
        SELECT doador_nome_norm, doador_cpf, doador_nome, municipio_ue, cargo,
               candidato_nome, partido, valor, data_receita, ano_eleicao
        FROM doacoes_campanha
        """
    ):
        por_nome.setdefault(row[0], []).append({
            "cpf": row[1],
            "doador_nome": row[2],
            "municipio_ue": row[3],
            "cargo": row[4],
            "candidato_nome": row[5],
            "partido": row[6],
            "valor": row[7] or 0.0,
            "data": row[8],
            "ano": row[9],
        })
    return por_nome


def matches_confirmados(conn: sqlite3.Connection) -> list[dict]:
    """Sócios (QSA) cujo nome + 6 dígitos do CPF batem com um doador do TSE.

    Retorna um dict por (fornecedor, sócio, cpf confirmado) com as doações que
    o confirmaram.
    """
    doacoes = _carregar_doacoes(conn)
    if not doacoes:
        return []

    resultados: list[dict] = []
    for ni, socios_json in conn.execute(
        "SELECT fornecedor_ni, socios FROM fornecedor_cadastro "
        "WHERE socios IS NOT NULL AND socios != '[]'"
    ):
        try:
            socios = json.loads(socios_json)
        except (TypeError, json.JSONDecodeError):
            continue

        for s in socios:
            nome = (s.get("nome_socio") or "").strip()
            meio = _cpf_meio_da_mascara(s.get("cnpj_cpf_do_socio"))
            if not nome or not meio:
                continue
            nome_norm = normalizar_nome(nome)
            candidatas = doacoes.get(nome_norm)
            if not candidatas:
                continue

            # Confirma pelos 6 dígitos do meio do CPF (posições 3..8).
            por_cpf: dict[str, list[dict]] = {}
            for d in candidatas:
                if d["cpf"][3:9] == meio:
                    por_cpf.setdefault(d["cpf"], []).append(d)

            for cpf, doacoes_conf in por_cpf.items():
                resultados.append({
                    "fornecedor_ni": ni,
                    "nome_socio": nome,
                    "nome_socio_norm": nome_norm,
                    "qualificacao": s.get("qualificacao_socio"),
                    "cpf": cpf,
                    "doacoes": doacoes_conf,
                })
    return resultados


def resolver_cpf_confirmado(conn: sqlite3.Connection) -> int:
    """Grava os CPFs de sócio confirmados em socios_cpf_confirmado (idempotente).

    É o "fecha CPF": a identidade do sócio, antes só nome + CPF mascarado, passa
    a ter CPF completo com base documental pública (TSE). Retorna quantos.
    """
    matches = matches_confirmados(conn)
    for m in matches:
        detalhe = json.dumps(
            [
                {
                    "candidato": d["candidato_nome"],
                    "cargo": d["cargo"],
                    "municipio": d["municipio_ue"],
                    "valor": d["valor"],
                    "data": d["data"],
                }
                for d in m["doacoes"]
            ],
            ensure_ascii=False,
        )
        conn.execute(
            """
            INSERT INTO socios_cpf_confirmado (
                fornecedor_ni, nome_socio, nome_socio_norm, cpf, fonte, detalhe
            ) VALUES (?,?,?,?, 'TSE', ?)
            ON CONFLICT(fornecedor_ni, nome_socio, cpf) DO UPDATE SET
                detalhe = excluded.detalhe,
                confirmado_em = datetime('now')
            """,
            (m["fornecedor_ni"], m["nome_socio"], m["nome_socio_norm"], m["cpf"], detalhe),
        )
    conn.commit()
    return len(matches)


def _contexto_fornecedor(conn: sqlite3.Connection, ni: str) -> dict:
    row = conn.execute(
        """
        SELECT f.razao_social,
               COUNT(c.numero_controle_pncp) AS n_contratos,
               COALESCE(SUM(c.valor_global), 0) AS valor_contratos
        FROM fornecedores f
        JOIN contratos c ON c.fornecedor_ni = f.ni AND c.valor_global > 0
        WHERE f.ni = ?
        """,
        (ni,),
    ).fetchone()
    municipios = {
        normalizar_nome(m[0])
        for m in conn.execute(
            "SELECT DISTINCT municipio_nome FROM contratos "
            "WHERE fornecedor_ni = ? AND municipio_nome IS NOT NULL",
            (ni,),
        )
        if m[0]
    }
    pncp = [
        p[0]
        for p in conn.execute(
            "SELECT numero_controle_pncp FROM contratos "
            "WHERE fornecedor_ni = ? AND valor_global > 0",
            (ni,),
        )
    ]
    return {
        "razao_social": (row[0] if row else None) or ni,
        "n_contratos": row[1] if row else 0,
        "valor_contratos": row[2] if row else 0.0,
        "municipios": municipios,
        "pncp": pncp,
    }


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    matches = matches_confirmados(conn)
    if not matches:
        return []

    # Agrupa por fornecedor.
    por_fornecedor: dict[str, list[dict]] = {}
    for m in matches:
        por_fornecedor.setdefault(m["fornecedor_ni"], []).append(m)

    resultados: list[AnomaliaResult] = []
    for ni, socios in por_fornecedor.items():
        ctx = _contexto_fornecedor(conn, ni)
        if not ctx["pncp"]:
            continue  # sócio doador mas sem contrato com valor — fora de escopo

        total_doado = 0.0
        cargos: set[str] = set()
        municipios_doacao: set[str] = set()
        candidatos: set[str] = set()
        socios_meta: list[dict] = []
        for s in socios:
            valor_socio = sum(d["valor"] for d in s["doacoes"])
            total_doado += valor_socio
            for d in s["doacoes"]:
                if d["cargo"]:
                    cargos.add(d["cargo"].upper())
                if d["municipio_ue"]:
                    municipios_doacao.add(normalizar_nome(d["municipio_ue"]))
                if d["candidato_nome"]:
                    candidatos.add(d["candidato_nome"])
            socios_meta.append({
                "nome": s["nome_socio"],
                "qualificacao": s["qualificacao"],
                "cpf_confirmado": _mascarar_cpf(s["cpf"]),
                "valor_doado": round(valor_socio, 2),
                "candidatos": sorted({
                    f"{d['candidato_nome']} ({d['cargo']}/{d['municipio_ue']})"
                    for d in s["doacoes"] if d["candidato_nome"]
                }),
            })

        alinhado = bool(municipios_doacao & ctx["municipios"])
        executivo = bool(cargos & _CARGOS_EXECUTIVO)
        vc = ctx["valor_contratos"]

        if alinhado and (executivo or vc >= _VALOR_CONTRATO_ALTA):
            severidade = "alta"
        elif alinhado or vc >= _VALOR_CONTRATO_ALTA:
            severidade = "media"
        else:
            severidade = "baixa"

        score = min(vc / 50_000_000, 0.6)
        if alinhado:
            score += 0.25
        if executivo:
            score += 0.15
        score = round(min(score, 1.0), 3)

        n_socios = len(socios_meta)
        cargos_txt = ", ".join(sorted(c.title() for c in cargos)) or "candidato(s)"
        alinhado_txt = (
            " no MESMO município que a contrata" if alinhado
            else " em município(s) da base"
        )
        socios_txt = "; ".join(
            f"{sm['nome']} ({sm['qualificacao'] or 'sócio'})" for sm in socios_meta
        )

        resultados.append(AnomaliaResult(
            tipo="socio_doou_campanha",
            severidade=severidade,
            score=score,
            titulo=(
                f"Sócio de {ctx['razao_social'][:40]} doou a campanha municipal "
                f"({n_socios} sócio{'s' if n_socios > 1 else ''}, R$ {total_doado:,.0f})"
            ),
            descricao=(
                f"{n_socios} sócio(s) de {ctx['razao_social']} — {socios_txt} — "
                f"doaram R$ {total_doado:,.2f} a campanhas de {cargos_txt}"
                f"{alinhado_txt}. A empresa tem {ctx['n_contratos']} contrato(s) "
                f"somando R$ {vc:,.2f}. Doação de pessoa física é legal — o sinal "
                f"aponta ALINHAMENTO POLÍTICO entre quem controla o fornecedor e "
                f"quem exerce/disputou mandato no município contratante, não "
                f"ilegalidade. Identidade do(s) sócio(s) confirmada por nome + CPF "
                f"(dado público do TSE)."
            ),
            metodologia=(
                "Cruza sócios do QSA (BrasilAPI) com doações de campanha do TSE "
                "(prestação de contas de candidatos). Confirma identidade por nome "
                "normalizado + os 6 dígitos do meio do CPF (o QSA traz o CPF "
                "mascarado; o TSE, o completo) — falso-positivo desprezível. "
                "Doação de empresa é proibida desde 2015 (Lei 13.165 + ADI 4650), "
                "então só entra pessoa física. Severidade sobe com alinhamento de "
                "município e cargo do Executivo. Cobertura limitada aos "
                "fornecedores com QSA enriquecido."
            ),
            contratos=ctx["pncp"],
            metricas={
                "fornecedor_ni": ni,
                "valor_contratos": round(vc, 2),
                "total_doado": round(total_doado, 2),
                "n_socios_doadores": n_socios,
                "alinhado_municipio": alinhado,
                "cargo_executivo": executivo,
                "cargos": sorted(cargos),
                "socios": socios_meta,
            },
            valor_referencia=vc,
        ))

    return resultados
