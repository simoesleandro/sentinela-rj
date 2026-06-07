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

@app.route('/fornecedor/<fornecedor_ni>')
def fornecedor_page(fornecedor_ni: str):
    return render_template('fornecedor.html', ni=fornecedor_ni)

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
                   c.fornecedor_ni,
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
    return min(round(raw, 1), 10.0)


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
                   COUNT(DISTINCT a.id) AS alertas,
                   COALESCE(f.tem_sancao, 0) AS tem_sancao
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
            item["tem_sancao"] = bool(item.get("tem_sancao"))
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
# Fornecedor — dossier
# ---------------------------------------------------------------------------

@app.route("/api/fornecedores/<fornecedor_ni>")
def fornecedor_dossie(fornecedor_ni: str):
    db = get_db()
    try:
        forn = db.execute(
            "SELECT ni, razao_social, tipo_pessoa, tem_sancao, ultima_consulta_sancao FROM fornecedores WHERE ni = ?",
            (fornecedor_ni,),
        ).fetchone()
        if forn is None:
            return jsonify({"error": "not found"}), 404

        contratos_rows = db.execute(
            """
            SELECT c.numero_controle_pncp, c.objeto, c.valor_global,
                   c.data_assinatura, c.data_vigencia_fim,
                   c.categoria_processo_nome AS categoria,
                   o.razao_social AS orgao,
                   EXISTS(
                     SELECT 1 FROM alertas a
                     WHERE a.numero_controle_pncp = c.numero_controle_pncp
                   ) AS tem_alerta
            FROM contratos c
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            WHERE c.fornecedor_ni = ? AND c.valor_global > 0
            ORDER BY c.data_assinatura DESC
            """,
            (fornecedor_ni,),
        ).fetchall()
        contratos = [dict(r) for r in contratos_rows]
        for c in contratos:
            c["tem_alerta"] = bool(c["tem_alerta"])

        total_contratos = len(contratos)
        valor_total = sum(c["valor_global"] or 0 for c in contratos)
        valor_medio = valor_total / total_contratos if total_contratos else 0
        datas = [c["data_assinatura"] for c in contratos if c["data_assinatura"]]

        anomalias_rows = db.execute(
            """
            SELECT a.id, a.tipo, a.severidade, a.descricao,
                   a.valor_referencia AS valor_grupo,
                   c.valor_global AS valor_contrato,
                   a.narrativa_ia, a.numero_controle_pncp,
                   c.objeto, c.data_assinatura
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            WHERE c.fornecedor_ni = ?
            ORDER BY a.severidade DESC, c.valor_global DESC
            """,
            (fornecedor_ni,),
        ).fetchall()
        anomalias = [dict(r) for r in anomalias_rows]

        severidades = [a["severidade"] for a in anomalias]
        tipos_a = [a["tipo"] for a in anomalias]
        risk_score = _calcular_score(len(anomalias), valor_total, severidades, tipos_a)
        risk_label = (
            "CRÍTICO" if risk_score >= 8 else
            "ALTO"    if risk_score >= 6 else
            "MÉDIO"   if risk_score >= 4 else
            "BAIXO"
        )
        risk_color = (
            "#ef4444" if risk_score >= 8 else
            "#f97316" if risk_score >= 6 else
            "#eab308" if risk_score >= 4 else
            "#22c55e"
        )

        orgaos_rows = db.execute(
            """
            SELECT o.razao_social AS orgao, c.orgao_cnpj AS cnpj,
                   COUNT(*) AS total_contratos,
                   SUM(c.valor_global) AS valor_total
            FROM contratos c
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            WHERE c.fornecedor_ni = ? AND c.valor_global > 0
            GROUP BY c.orgao_cnpj
            ORDER BY valor_total DESC
            """,
            (fornecedor_ni,),
        ).fetchall()

        relacionados_rows = db.execute(
            """
            SELECT f2.razao_social AS fornecedor, f2.ni,
                   COUNT(*) AS contratos_comuns,
                   SUM(c2.valor_global) AS valor_total,
                   MAX(c2.objeto) AS objeto_comum
            FROM alertas a1
            JOIN alertas a2 ON a2.tipo = 'fracionamento_ap'
              AND a2.numero_controle_pncp != a1.numero_controle_pncp
              AND a2.descricao LIKE '%' || (
                SELECT SUBSTR(a1.descricao, INSTR(a1.descricao, '—')+2, 60)
              ) || '%'
            JOIN contratos c2 ON c2.numero_controle_pncp = a2.numero_controle_pncp
            JOIN fornecedores f2 ON f2.ni = c2.fornecedor_ni
            WHERE a1.numero_controle_pncp IN (
              SELECT numero_controle_pncp FROM contratos WHERE fornecedor_ni = ?
            )
            AND f2.ni != ?
            GROUP BY f2.ni
            LIMIT 10
            """,
            (fornecedor_ni, fornecedor_ni),
        ).fetchall()

        timeline_rows = db.execute(
            """
            SELECT strftime('%Y-%m', data_assinatura) AS periodo,
                   COUNT(*) AS contratos,
                   SUM(valor_global) AS valor
            FROM contratos
            WHERE fornecedor_ni = ? AND valor_global > 0 AND data_assinatura IS NOT NULL
            GROUP BY periodo
            ORDER BY periodo
            """,
            (fornecedor_ni,),
        ).fetchall()

        cadastro_row = db.execute(
            """
            SELECT situacao_cadastral, descricao_situacao,
                   data_inicio_atividade, cnae_fiscal, cnae_fiscal_descricao,
                   capital_social, porte, natureza_juridica,
                   socios, cnaes_secundarios, municipio, uf, atualizado_em
            FROM fornecedor_cadastro
            WHERE fornecedor_ni = ?
            """,
            (fornecedor_ni,),
        ).fetchone()

        cadastro = dict(cadastro_row) if cadastro_row else None
        if cadastro:
            for campo in ("socios", "cnaes_secundarios"):
                raw = cadastro.get(campo)
                if raw:
                    try:
                        cadastro[campo] = json.loads(raw)
                    except Exception:
                        cadastro[campo] = []

        return jsonify({
            "identidade": dict(forn),
            "cadastro": cadastro,
            "resumo": {
                "total_contratos": total_contratos,
                "valor_total": valor_total,
                "valor_medio": valor_medio,
                "primeiro_contrato": min(datas) if datas else None,
                "ultimo_contrato": max(datas) if datas else None,
                "risk_score": risk_score,
                "risk_label": risk_label,
                "risk_color": risk_color,
            },
            "contratos": contratos,
            "anomalias": anomalias,
            "orgaos_contratantes": [dict(r) for r in orgaos_rows],
            "fornecedores_relacionados": [dict(r) for r in relacionados_rows],
            "timeline": {
                "labels": [r["periodo"] for r in timeline_rows],
                "contratos": [r["contratos"] for r in timeline_rows],
                "valor": [r["valor"] for r in timeline_rows],
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Órgãos ranking
# ---------------------------------------------------------------------------

@app.route("/api/orgaos/ranking")
def orgaos_ranking():
    db = get_db()
    try:
        rows = db.execute("""
            SELECT o.razao_social AS orgao,
                   o.cnpj,
                   COUNT(DISTINCT c.numero_controle_pncp) AS total_contratos,
                   COALESCE(SUM(c.valor_global), 0) AS valor_total,
                   COUNT(DISTINCT a.id) AS total_alertas,
                   COUNT(DISTINCT CASE WHEN a.severidade='alta' THEN a.id END) AS alertas_alta,
                   COUNT(DISTINCT CASE WHEN a.tipo='outlier_valor' THEN a.id END) AS outliers,
                   COUNT(DISTINCT CASE WHEN a.tipo LIKE 'sem_licitacao%' THEN a.id END) AS sem_licitacao,
                   COUNT(DISTINCT CASE WHEN a.tipo='concentracao_fornecedor' THEN a.id END) AS concentracao,
                   COUNT(DISTINCT CASE WHEN a.tipo='fracionamento_ap' THEN a.id END) AS fracionamento
            FROM orgaos o
            LEFT JOIN contratos c ON c.orgao_cnpj = o.cnpj
            LEFT JOIN alertas a ON a.numero_controle_pncp = c.numero_controle_pncp
            GROUP BY o.cnpj
            ORDER BY total_alertas DESC
        """).fetchall()
        return jsonify({"items": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/orgaos/<cnpj>/contratos")
def orgaos_contratos(cnpj: str):
    db = get_db()
    try:
        rows = db.execute("""
            SELECT c.numero_controle_pncp, c.objeto, c.valor_global,
                   c.data_assinatura, f.razao_social AS fornecedor,
                   COUNT(a.id) AS alertas
            FROM contratos c
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN alertas a ON a.numero_controle_pncp = c.numero_controle_pncp
            WHERE c.orgao_cnpj = ?
            GROUP BY c.numero_controle_pncp
            ORDER BY alertas DESC, c.valor_global DESC
            LIMIT 50
        """, (cnpj,)).fetchall()
        return jsonify({"items": [dict(r) for r in rows]})
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
# Rede — sócios compartilhados
# ---------------------------------------------------------------------------

@app.route("/api/socios/compartilhados")
def socios_compartilhados():
    import json as _json
    import re as _re
    db = get_db()
    try:
        rows = db.execute("""
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
        """).fetchall()

        re_cnpj = _re.compile(r"^\d{14}$")
        por_socio: dict[str, list[dict]] = {}

        for r in rows:
            try:
                socios = _json.loads(r["socios"])
            except (TypeError, _json.JSONDecodeError):
                continue
            for s in socios:
                nome = (s.get("nome_socio") or "").strip()
                if not nome or nome.lower() == "none" or len(nome) < 5:
                    continue
                doc = _re.sub(r"\D", "", s.get("cnpj_cpf_do_socio") or "")
                if re_cnpj.match(doc):
                    continue
                por_socio.setdefault(nome, []).append({
                    "ni": r["fornecedor_ni"],
                    "razao_social": r["razao_social"] or r["fornecedor_ni"],
                    "valor_total": r["valor_total"] or 0.0,
                    "total_contratos": r["total_contratos"] or 0,
                })

        items = []
        for nome_socio, fornecedores in por_socio.items():
            vistos: set[str] = set()
            forn_unicos = []
            for f in fornecedores:
                if f["ni"] not in vistos:
                    vistos.add(f["ni"])
                    forn_unicos.append(f)

            if len(forn_unicos) < 2:
                continue

            valor_total = sum(f["valor_total"] for f in forn_unicos)
            if valor_total < 1_000_000:
                continue

            total_contratos = sum(f["total_contratos"] for f in forn_unicos)
            items.append({
                "nome_socio": nome_socio,
                "fornecedores": sorted(forn_unicos, key=lambda x: x["valor_total"], reverse=True),
                "total_fornecedores": len(forn_unicos),
                "total_contratos": total_contratos,
                "valor_total": round(valor_total, 2),
                "severidade": "alta" if valor_total >= 10_000_000 else "media",
            })

        items.sort(key=lambda x: x["valor_total"], reverse=True)
        return jsonify({"items": items})
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
