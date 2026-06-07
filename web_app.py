"""Flask REST API — Sentinela RJ (read-only dashboard)."""
import csv
import io
import json
import math
import os
import sqlite3
from flask import Flask, jsonify, request, render_template, Response

from db.conexao import DB_PATH

app = Flask(__name__, static_folder='static', template_folder='templates')


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/dashboard')
def dashboard():
    return render_template('index.html')

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return "Sentinela RJ API - OK", 200


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@app.route("/api/stats")
def stats():
    db = get_db()
    try:
        contratos_total = db.execute(
            "SELECT COUNT(*) FROM contratos WHERE valor_global > 0"
        ).fetchone()[0]
        valor_total = db.execute(
            "SELECT SUM(valor_global) FROM contratos WHERE valor_global > 0"
        ).fetchone()[0]
        alertas_total = db.execute(
            "SELECT COUNT(*) FROM alertas"
        ).fetchone()[0]
        alertas_alta = db.execute(
            "SELECT COUNT(*) FROM alertas WHERE severidade = 'alta'"
        ).fetchone()[0]
        fornecedores_distintos = db.execute(
            "SELECT COUNT(DISTINCT fornecedor_ni) FROM contratos"
        ).fetchone()[0]
        ultima_coleta = db.execute(
            "SELECT MAX(finalizado_em) FROM coletas_log"
        ).fetchone()[0]
        periodo_inicio = db.execute(
            "SELECT MIN(data_assinatura) FROM contratos"
        ).fetchone()[0]
        periodo_fim = db.execute(
            "SELECT MAX(data_assinatura) FROM contratos"
        ).fetchone()[0]
        return jsonify(
            {
                "contratos_total": contratos_total,
                "valor_total": valor_total,
                "alertas_total": alertas_total,
                "alertas_alta": alertas_alta,
                "fornecedores_distintos": fornecedores_distintos,
                "ultima_coleta": ultima_coleta,
                "periodo_inicio": periodo_inicio,
                "periodo_fim": periodo_fim,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Alertas — list
# ---------------------------------------------------------------------------

@app.route("/api/alertas")
def alertas_list():
    db = get_db()
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        tipo = request.args.get("tipo")
        severidade = request.args.get("severidade")
        ano = request.args.get("ano")
        fornecedor = request.args.get("fornecedor")

        base = """
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
        """
        conditions: list[str] = []
        params: list = []

        if tipo:
            conditions.append("a.tipo = ?")
            params.append(tipo)
        if severidade:
            conditions.append("a.severidade = ?")
            params.append(severidade)
        if ano:
            conditions.append("strftime('%Y', c.data_assinatura) = ?")
            params.append(ano)
        if fornecedor:
            conditions.append("f.razao_social LIKE ?")
            params.append(f"%{fornecedor}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = db.execute(
            f"SELECT COUNT(*) {base} {where}", params
        ).fetchone()[0]

        pages = math.ceil(total / per_page) if total else 0
        offset = (page - 1) * per_page

        rows = db.execute(
            f"""
            SELECT a.id, a.tipo, a.severidade, a.descricao, a.valor_referencia,
                   a.narrativa_ia, a.numero_controle_pncp,
                   f.razao_social AS fornecedor,
                   c.objeto, c.data_assinatura, c.orgao_cnpj,
                   o.razao_social AS orgao
            {base} {where}
            ORDER BY a.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

        return jsonify(
            {
                "items": [dict(r) for r in rows],
                "total": total,
                "page": page,
                "pages": pages,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Alertas — grouped
# ---------------------------------------------------------------------------

_SEV_PRIORITY = {'alta': 3, 'media': 2, 'baixa': 1}


@app.route("/api/alertas/agrupados")
def alertas_agrupados():
    db = get_db()
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        tipo = request.args.get("tipo")
        severidade = request.args.get("severidade")
        ano = request.args.get("ano")
        fornecedor = request.args.get("fornecedor")
        valor_min = request.args.get("valor_min", type=float)

        joins = """
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        """
        conditions: list[str] = []
        params: list = []

        if tipo:
            conditions.append("a.tipo = ?")
            params.append(tipo)
        if severidade:
            conditions.append("a.severidade = ?")
            params.append(severidade)
        if ano:
            conditions.append("strftime('%Y', c.data_assinatura) = ?")
            params.append(ano)
        if fornecedor:
            cnpj = fornecedor.replace(".", "").replace("/", "").replace("-", "")
            conditions.append("(f.razao_social LIKE ? OR f.ni LIKE ?)")
            params.extend([f"%{fornecedor}%", f"%{cnpj}%"])
        if valor_min is not None:
            conditions.append("a.valor_referencia >= ?")
            params.append(valor_min)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = db.execute(
            f"SELECT COUNT(*) FROM (SELECT DISTINCT c.fornecedor_ni, a.tipo {joins} {where})",
            params,
        ).fetchone()[0]

        pages = math.ceil(total / per_page) if total else 0
        offset = (page - 1) * per_page

        group_rows = db.execute(
            f"""
            SELECT DISTINCT c.fornecedor_ni, a.tipo, f.razao_social AS fornecedor_nome
            {joins} {where}
            ORDER BY c.fornecedor_ni, a.tipo
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

        items = []
        for gr in group_rows:
            fni = gr["fornecedor_ni"]
            tp = gr["tipo"]

            detail_cond = ["c.fornecedor_ni = ?", "a.tipo = ?"]
            detail_params: list = [fni, tp]
            if ano:
                detail_cond.append("strftime('%Y', c.data_assinatura) = ?")
                detail_params.append(ano)

            alerts = db.execute(
                f"""
                SELECT a.id, a.severidade, a.descricao, a.valor_referencia, a.narrativa_ia,
                       a.numero_controle_pncp, c.objeto, c.data_assinatura,
                       o.razao_social AS orgao
                FROM alertas a
                LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
                LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
                WHERE {' AND '.join(detail_cond)}
                ORDER BY a.id DESC
                """,
                detail_params,
            ).fetchall()

            severidades = [a["severidade"] for a in alerts]
            max_sev = max(severidades, key=lambda s: _SEV_PRIORITY.get(s, 0), default="baixa")
            valor_total = sum(a["valor_referencia"] or 0 for a in alerts)
            valor_max = max((a["valor_referencia"] or 0 for a in alerts), default=0)
            datas = [a["data_assinatura"] for a in alerts if a["data_assinatura"]]
            narrativa = next((a["narrativa_ia"] for a in alerts if a["narrativa_ia"]), None)

            items.append({
                "grupo_id": f"{fni}__{tp}",
                "fornecedor": gr["fornecedor_nome"] or fni,
                "tipo": tp,
                "severidade": max_sev,
                "ocorrencias": len(alerts),
                "valor_total": valor_total,
                "valor_max": valor_max,
                "data_mais_recente": max(datas) if datas else None,
                "narrativa_ia": narrativa,
                "alertas": [
                    {
                        "id": a["id"],
                        "descricao": a["descricao"],
                        "valor_referencia": a["valor_referencia"],
                        "objeto": a["objeto"],
                        "data_assinatura": a["data_assinatura"],
                        "numero_controle_pncp": a["numero_controle_pncp"],
                        "orgao": a["orgao"],
                    }
                    for a in alerts
                ],
            })

        return jsonify({"items": items, "total": total, "page": page, "pages": pages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Alertas — detail
# ---------------------------------------------------------------------------

@app.route("/api/alertas/<int:alert_id>")
def alertas_detail(alert_id: int):
    db = get_db()
    try:
        row = db.execute(
            """
            SELECT a.*,
                   c.objeto, c.data_assinatura, c.data_vigencia_inicio,
                   c.data_vigencia_fim, c.valor_inicial, c.valor_global,
                   c.informacao_complementar, c.numero_contrato_empenho,
                   f.razao_social AS fornecedor, f.tipo_pessoa,
                   o.razao_social AS orgao
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            WHERE a.id = ?
            """,
            (alert_id,),
        ).fetchone()
        if row is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(dict(row))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

@app.route("/api/timeline")
def timeline():
    db = get_db()
    try:
        granularity = request.args.get("granularity", "month")
        strftime_expr = (
            "strftime('%Y-%m', data_assinatura)"
            if granularity == "month"
            else "strftime('%Y', data_assinatura)"
        )
        rows = db.execute(
            f"""
            SELECT {strftime_expr} AS periodo,
                   COUNT(*) AS contratos,
                   SUM(valor_global) AS valor
            FROM contratos
            WHERE valor_global > 0 AND data_assinatura IS NOT NULL
            GROUP BY periodo
            ORDER BY periodo
            """
        ).fetchall()
        return jsonify(
            {
                "labels": [r["periodo"] for r in rows],
                "contratos": [r["contratos"] for r in rows],
                "valor": [r["valor"] for r in rows],
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fornecedores ranking
# ---------------------------------------------------------------------------

def _calcular_score(
    alertas_count: int,
    valor_total: float,
    severidades: list[str],
    tipos: list[str],
) -> float:
    if alertas_count == 0:
        return 0.0
    severity_sum = sum(3 if s == "alta" else 2 if s == "media" else 1 for s in severidades)
    type_diversity = len(set(tipos))
    valor_factor = min(valor_total / 100_000_000, 3.0)
    raw = severity_sum + type_diversity + valor_factor
    score = min(round(raw / (alertas_count + 1) * alertas_count, 1), 10.0)
    return score


@app.route("/api/fornecedores/ranking")
def fornecedores_ranking():
    db = get_db()
    try:
        limit = min(100, max(1, int(request.args.get("limit", 10))))
        orderby = request.args.get("orderby", "valor")
        order_col = "total_contratos" if orderby == "contratos" else "valor_total"
        q = request.args.get("q", "").strip()

        ranking_conditions = ["c.valor_global > 0"]
        ranking_params: list = []
        if q:
            cnpj_q = q.replace(".", "").replace("/", "").replace("-", "")
            ranking_conditions.append("(f.razao_social LIKE ? OR f.ni LIKE ?)")
            ranking_params.extend([f"%{q}%", f"%{cnpj_q}%"])

        ranking_where = "WHERE " + " AND ".join(ranking_conditions)

        rows = db.execute(
            f"""
            SELECT c.fornecedor_ni,
                   f.razao_social AS fornecedor,
                   COUNT(*) AS total_contratos,
                   SUM(c.valor_global) AS valor_total,
                   COUNT(DISTINCT a.id) AS alertas
            FROM contratos c
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN alertas a ON a.numero_controle_pncp = c.numero_controle_pncp
            {ranking_where}
            GROUP BY c.fornecedor_ni
            ORDER BY {order_col} DESC
            LIMIT ?
            """,
            ranking_params + [limit],
        ).fetchall()

        items = []
        for r in rows:
            item = dict(r)
            alert_rows = db.execute(
                """
                SELECT a.severidade, a.tipo
                FROM alertas a
                LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
                WHERE c.fornecedor_ni = ?
                """,
                (item["fornecedor_ni"],),
            ).fetchall()
            severidades = [ar["severidade"] for ar in alert_rows]
            tipos = [ar["tipo"] for ar in alert_rows]
            score = _calcular_score(item["alertas"], item["valor_total"] or 0, severidades, tipos)
            item["risk_score"] = score
            item["risk_label"] = (
                "CRÍTICO" if score >= 8 else
                "ALTO"    if score >= 6 else
                "MÉDIO"   if score >= 4 else
                "BAIXO"
            )
            item["risk_color"] = (
                "#ef4444" if score >= 8 else
                "#f97316" if score >= 6 else
                "#eab308" if score >= 4 else
                "#22c55e"
            )
            items.append(item)

        items.sort(key=lambda x: x["risk_score"], reverse=True)
        return jsonify({"items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Anomalias por tipo
# ---------------------------------------------------------------------------

@app.route("/api/anomalias/por-tipo")
def anomalias_por_tipo():
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT tipo, severidade, COUNT(*) AS quantidade
            FROM alertas
            GROUP BY tipo, severidade
            ORDER BY tipo, severidade
            """
        ).fetchall()
        return jsonify({"items": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Export — CSV downloads
# ---------------------------------------------------------------------------

@app.route("/api/export/contratos")
def export_contratos():
    db = get_db()
    try:
        rows = db.execute("""
            SELECT c.numero_controle_pncp, c.objeto, c.categoria_processo_nome,
                   c.valor_global, c.data_assinatura, c.data_vigencia_inicio,
                   c.data_vigencia_fim, f.razao_social AS fornecedor,
                   f.ni AS fornecedor_cnpj, o.razao_social AS orgao,
                   c.orgao_cnpj, c.unidade_nome
            FROM contratos c
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            WHERE c.valor_global > 0
            ORDER BY c.data_assinatura DESC
        """).fetchall()

        fieldnames = [
            "numero_controle_pncp", "objeto", "categoria_processo_nome",
            "valor_global", "data_assinatura", "data_vigencia_inicio",
            "data_vigencia_fim", "fornecedor", "fornecedor_cnpj",
            "orgao", "orgao_cnpj", "unidade_nome",
        ]
        output = io.StringIO()
        output.write('﻿')  # UTF-8 BOM for Excel
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", delimiter=';')
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])

        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=sentinela_rj_contratos.csv"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/export/alertas")
def export_alertas():
    db = get_db()
    try:
        rows = db.execute("""
            SELECT a.id, a.tipo, a.severidade, a.descricao, a.valor_referencia,
                   a.metodologia, a.narrativa_ia, a.criado_em,
                   f.razao_social AS fornecedor, f.ni AS fornecedor_cnpj,
                   c.objeto, c.data_assinatura, c.valor_global,
                   o.razao_social AS orgao
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            ORDER BY a.severidade DESC, a.valor_referencia DESC
        """).fetchall()

        fieldnames = [
            "id", "tipo", "severidade", "descricao", "valor_referencia",
            "metodologia", "narrativa_ia", "criado_em",
            "fornecedor", "fornecedor_cnpj", "objeto",
            "data_assinatura", "valor_global", "orgao",
        ]
        output = io.StringIO()
        output.write('﻿')  # UTF-8 BOM for Excel
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", delimiter=';')
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])

        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=sentinela_rj_alertas.csv"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from waitress import serve

    serve(app, host="0.0.0.0", port=5055)
