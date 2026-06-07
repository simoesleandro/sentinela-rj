"""
Detector de sócios em comum — Sentinela RJ.

Cruza fornecedor_cadastro (campo socios/qsa) com contratos para detectar
pessoas físicas que figuram como sócias em 2 ou mais fornecedores que
receberam contratos da prefeitura.
"""
from __future__ import annotations

import json
import re
import sqlite3

from analisador.engine import AnomaliaResult

_MIN_VALOR = 1_000_000          # valor total mínimo para gerar alerta
_LIMITE_ALTA = 10_000_000       # acima disso, severidade = alta
_RE_CNPJ = re.compile(r"^\d{14}$")


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    c = conn.cursor()
    c.execute("""
        SELECT fc.fornecedor_ni,
               fc.socios,
               f.razao_social,
               COUNT(ct.numero_controle_pncp) AS total_contratos,
               SUM(ct.valor_global)            AS valor_total
        FROM fornecedor_cadastro fc
        JOIN fornecedores f  ON f.ni  = fc.fornecedor_ni
        JOIN contratos ct    ON ct.fornecedor_ni = fc.fornecedor_ni
        WHERE fc.socios IS NOT NULL
          AND fc.socios != '[]'
          AND ct.valor_global > 0
        GROUP BY fc.fornecedor_ni
    """)
    rows = c.fetchall()

    # nome_socio -> list[{ni, razao_social, valor_total, total_contratos}]
    por_socio: dict[str, list[dict]] = {}

    for r in rows:
        try:
            socios = json.loads(r["socios"])
        except (TypeError, json.JSONDecodeError):
            continue

        for s in socios:
            nome = (s.get("nome_socio") or "").strip()
            if not nome or nome.lower() == "none" or len(nome) < 5:
                continue

            # Ignorar sócios PJ (cpf/cnpj com 14 dígitos numéricos)
            doc = re.sub(r"\D", "", s.get("cnpj_cpf_do_socio") or "")
            if _RE_CNPJ.match(doc):
                continue

            por_socio.setdefault(nome, []).append({
                "ni": r["fornecedor_ni"],
                "razao_social": r["razao_social"] or r["fornecedor_ni"],
                "valor_total": r["valor_total"] or 0.0,
                "total_contratos": r["total_contratos"] or 0,
            })

    resultados: list[AnomaliaResult] = []

    for nome_socio, fornecedores in por_socio.items():
        # Deduplicar por ni (mesmo fornecedor pode ter sócio listado mais de uma vez)
        vistos: set[str] = set()
        forn_unicos = []
        for f in fornecedores:
            if f["ni"] not in vistos:
                vistos.add(f["ni"])
                forn_unicos.append(f)

        if len(forn_unicos) < 2:
            continue

        valor_total = sum(f["valor_total"] for f in forn_unicos)
        if valor_total < _MIN_VALOR:
            continue

        total_contratos = sum(f["total_contratos"] for f in forn_unicos)
        n = len(forn_unicos)
        severidade = "alta" if valor_total >= _LIMITE_ALTA else "media"

        empresas_txt = "; ".join(
            f"{f['razao_social']} (R$ {f['valor_total']:,.2f})"
            for f in sorted(forn_unicos, key=lambda x: x["valor_total"], reverse=True)
        )

        pncp_ids = c.execute(
            f"""
            SELECT numero_controle_pncp FROM contratos
            WHERE fornecedor_ni IN ({','.join('?' * n)})
              AND valor_global > 0
            """,
            [f["ni"] for f in forn_unicos],
        ).fetchall()
        pncp_list = [p["numero_controle_pncp"] for p in pncp_ids]

        score = round(min(valor_total / 50_000_000, 1.0), 3)

        resultados.append(AnomaliaResult(
            tipo="socio_compartilhado",
            severidade=severidade,
            score=score,
            titulo=f"Sócio em comum: {nome_socio} ({n} empresas)",
            descricao=(
                f"{nome_socio} figura como sócio(a) em {n} fornecedores contratados: "
                f"{empresas_txt}. "
                f"Total contratado: R$ {valor_total:,.2f} em {total_contratos} contrato(s)."
            ),
            metodologia=(
                "Cruzamento do campo 'qsa' (sócios) da BrasilAPI com fornecedores "
                "que possuem contratos na base. Filtra sócios PJ e nomes inválidos. "
                f"Limiar mínimo: R$ {_MIN_VALOR:,.0f}."
            ),
            contratos=pncp_list,
            metricas={
                "total_fornecedores": n,
                "total_contratos": total_contratos,
                "valor_total": round(valor_total, 2),
                "fornecedores": [
                    {"ni": f["ni"], "razao_social": f["razao_social"], "valor_total": round(f["valor_total"], 2)}
                    for f in forn_unicos
                ],
            },
            valor_referencia=valor_total,
        ))

    return resultados
