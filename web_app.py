"""Flask REST API — Sentinela RJ dashboard + triagem de alertas."""
import csv
import io
import json
import math
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, render_template, Response, redirect
from dotenv import load_dotenv

load_dotenv()

from analise.motivos_descarte import MOTIVOS_FALSO_POSITIVO, extrair_motivo_descarte
from analise.score_composto import calcular_score_composto
from db.conexao import DB_PATH, aplicar_migracoes

app = Flask(__name__, static_folder='static', template_folder='templates')

from web_auth import checar_cota_ia, registrar_consumo_ia, requer_admin, init_auth

init_auth(app)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "app": "sentinela-rj"}), 200


_SCORE_SQL = """(
    COALESCE(a.score, 0) * 0.35
    + CASE COALESCE(a.severidade, 'baixa')
      WHEN 'alta' THEN 0.4 WHEN 'media' THEN 0.25 ELSE 0.1 END
    + MIN(COALESCE(a.valor_referencia, 0) / 50000000.0, 1.0) * 0.25
)"""
_migracoes_aplicadas = False


def get_db() -> sqlite3.Connection:
    global _migracoes_aplicadas
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if not _migracoes_aplicadas and DB_PATH.exists():
        aplicar_migracoes(conn)
        _migracoes_aplicadas = True
    return conn

@app.route('/dashboard')
def dashboard():
    return render_template('index.html')

@app.route('/fornecedor/<path:fornecedor_ni>')
def fornecedor_page(fornecedor_ni: str):
    # aceita CNPJ formatado (42.498.733/0001-90) e redireciona para forma canônica
    ni = fornecedor_ni.replace('.', '').replace('/', '').replace('-', '')
    if ni != fornecedor_ni:
        return redirect(f'/fornecedor/{ni}', 301)
    return render_template('fornecedor.html', ni=ni)

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return "Sentinela RJ API - OK", 200


# ---------------------------------------------------------------------------
# Município — filtro do dashboard
# ---------------------------------------------------------------------------

def _municipio_ibge_request() -> str | None:
    raw = (request.args.get("municipio_ibge") or "").strip()
    return raw if raw else None


def _aplicar_filtro_municipio(
    conditions: list[str],
    params: list,
    ibge: str | None,
    alias: str = "o",
) -> None:
    from db.filtro_municipio import filtro_municipio_sql

    clause, filtro_params = filtro_municipio_sql(ibge, alias=alias)
    if clause:
        conditions.append(clause)
        params.extend(filtro_params)


@app.route("/api/municipios")
def municipios_list():
    from extrator.config_municipio import (
        municipio_esfera,
        municipio_ibge,
        municipio_nome,
        municipios_monitorados,
        rotulo_filtro,
    )
    from db.filtro_municipio import listar_municipios

    db = get_db()
    try:
        monitorados = municipios_monitorados()
        return jsonify({
            "coleta_ibge": municipio_ibge(),
            "coleta_nome": municipio_nome(),
            "coleta_esfera": municipio_esfera(),
            "coleta_rotulo": rotulo_filtro(),
            "monitorados": [
                {"ibge": m.ibge, "nome": m.nome, "prioridade": m.prioridade}
                for m in monitorados
            ],
            "items": listar_municipios(db),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@app.route("/api/stats")
def stats():
    db = get_db()
    try:
        ibge = _municipio_ibge_request()
        join_o = "JOIN orgaos o ON o.cnpj = c.orgao_cnpj" if ibge else ""
        where_mun: list[str] = []
        params_mun: list = []
        _aplicar_filtro_municipio(where_mun, params_mun, ibge)
        extra = (" AND " + " AND ".join(where_mun)) if where_mun else ""

        contratos_total = db.execute(
            f"SELECT COUNT(*) FROM contratos c {join_o} WHERE c.valor_global > 0{extra}",
            params_mun,
        ).fetchone()[0]
        valor_total = db.execute(
            f"SELECT SUM(c.valor_global) FROM contratos c {join_o} WHERE c.valor_global > 0{extra}",
            params_mun,
        ).fetchone()[0]

        if ibge:
            alertas_sql = f"""
                SELECT COUNT(*) FROM alertas a
                JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
                JOIN orgaos o ON o.cnpj = c.orgao_cnpj
                WHERE o.municipio_ibge = ?
            """
            alertas_total = db.execute(alertas_sql, (ibge,)).fetchone()[0]
            alertas_alta = db.execute(
                alertas_sql + " AND a.severidade = 'alta'", (ibge,)
            ).fetchone()[0]
            fornecedores_distintos = db.execute(
                f"""
                SELECT COUNT(DISTINCT c.fornecedor_ni) FROM contratos c
                {join_o} WHERE c.valor_global > 0{extra}
                """,
                params_mun,
            ).fetchone()[0]
            periodo_inicio = db.execute(
                f"""
                SELECT MIN(c.data_assinatura) FROM contratos c {join_o}
                WHERE c.valor_global > 0{extra}
                """,
                params_mun,
            ).fetchone()[0]
            periodo_fim = db.execute(
                f"""
                SELECT MAX(c.data_assinatura) FROM contratos c {join_o}
                WHERE c.valor_global > 0{extra}
                """,
                params_mun,
            ).fetchone()[0]
            from db.filtro_municipio import resumo_triagem_municipio

            triagem = resumo_triagem_municipio(db, ibge)
        else:
            alertas_total = db.execute("SELECT COUNT(*) FROM alertas").fetchone()[0]
            alertas_alta = db.execute(
                "SELECT COUNT(*) FROM alertas WHERE severidade = 'alta'"
            ).fetchone()[0]
            fornecedores_distintos = db.execute(
                "SELECT COUNT(DISTINCT fornecedor_ni) FROM contratos"
            ).fetchone()[0]
            periodo_inicio = db.execute(
                "SELECT MIN(data_assinatura) FROM contratos"
            ).fetchone()[0]
            periodo_fim = db.execute(
                "SELECT MAX(data_assinatura) FROM contratos"
            ).fetchone()[0]
            from db.triagem import resumo_status

            triagem = resumo_status(db)

        ultima_coleta = db.execute(
            "SELECT MAX(finalizado_em) FROM coletas_log"
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
                "triagem": triagem,
                "municipio_ibge": ibge,
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
        _aplicar_filtro_municipio(conditions, params, _municipio_ibge_request())

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
# Alertas — triagem (helpers + fila)
# ---------------------------------------------------------------------------

_SEV_PRIORITY = {"alta": 3, "media": 2, "baixa": 1}
_STATUS_PRIORITY = {"aberto": 4, "investigando": 3, "confirmado": 2, "descartado": 1}


def _aplicar_filtro_status(
    conditions: list[str],
    params: list,
    status_param: str | None,
) -> None:
    from db.triagem import filtro_status_sql

    if not status_param:
        return
    clause, filtro_params = filtro_status_sql(status_param)
    if clause:
        conditions.append(clause)
        params.extend(filtro_params)


@app.route("/api/alertas/triagem")
def alertas_triagem():
    from db.filtro_municipio import resumo_triagem_municipio
    from db.triagem import resumo_status

    db = get_db()
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        status = request.args.get("status", "fila")
        ibge = _municipio_ibge_request()

        base = """
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
        """
        conditions: list[str] = []
        params: list = []
        _aplicar_filtro_status(conditions, params, status)
        _aplicar_filtro_municipio(conditions, params, ibge)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = db.execute(f"SELECT COUNT(*) {base} {where}", params).fetchone()[0]
        pages = math.ceil(total / per_page) if total else 0
        offset = (page - 1) * per_page

        rows = db.execute(
            f"""
            SELECT a.id, a.tipo, a.severidade, a.score, a.status,
                   a.descricao, a.valor_referencia, a.notas_triagem,
                   a.status_atualizado_em, a.narrativa_ia, a.numero_controle_pncp,
                   f.razao_social AS fornecedor,
                   c.objeto, c.data_assinatura,
                   o.razao_social AS orgao
            {base} {where}
            ORDER BY {_SCORE_SQL} DESC, a.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

        items = []
        for row in rows:
            item = dict(row)
            item["score_composto"] = calcular_score_composto(
                item.get("score"), item.get("severidade"), item.get("valor_referencia"),
            )
            items.append(item)

        resumo = resumo_triagem_municipio(db, ibge) if ibge else resumo_status(db)
        return jsonify({
            "resumo": resumo,
            "items": items,
            "total": total,
            "page": page,
            "pages": pages,
            "municipio_ibge": ibge,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/alertas/feedback/descartes")
def alertas_feedback_descartes():
    """Resumo de descartes por tipo de alerta e motivo de falso positivo."""
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT a.tipo, h.nota
            FROM alertas_historico h
            JOIN alertas a ON a.id = h.alerta_id
            WHERE h.status_novo = 'descartado'
            """
        ).fetchall()
        por_tipo: dict[str, int] = {}
        por_motivo: dict[str, int] = {}
        sem_motivo = 0
        for row in rows:
            tipo = row["tipo"] or "desconhecido"
            por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
            motivo = extrair_motivo_descarte(row["nota"])
            if motivo:
                por_motivo[motivo] = por_motivo.get(motivo, 0) + 1
            else:
                sem_motivo += 1
        return jsonify({
            "motivos_disponiveis": MOTIVOS_FALSO_POSITIVO,
            "por_tipo": por_tipo,
            "por_motivo": por_motivo,
            "sem_motivo_estruturado": sem_motivo,
            "total_descartes": len(rows),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Alertas — grouped
# ---------------------------------------------------------------------------

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
        status = request.args.get("status")

        joins = """
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
        """
        conditions: list[str] = []
        params: list = []

        _aplicar_filtro_status(conditions, params, status)
        _aplicar_filtro_municipio(conditions, params, _municipio_ibge_request())

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
            SELECT c.fornecedor_ni, a.tipo, f.razao_social AS fornecedor_nome,
                   MAX({_SCORE_SQL}) AS score_composto
            {joins} {where}
            GROUP BY c.fornecedor_ni, a.tipo, f.razao_social
            ORDER BY score_composto DESC, c.fornecedor_ni, a.tipo
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
                SELECT a.id, a.severidade, a.status, a.descricao, a.valor_referencia,
                       a.narrativa_ia, a.numero_controle_pncp, c.objeto,
                       c.data_assinatura, o.razao_social AS orgao
                FROM alertas a
                LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
                LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
                WHERE {' AND '.join(detail_cond)}
                ORDER BY a.id DESC
                """,
                detail_params,
            ).fetchall()

            severidades = [a["severidade"] for a in alerts]
            statuses = [a["status"] or "aberto" for a in alerts]
            max_sev = max(severidades, key=lambda s: _SEV_PRIORITY.get(s, 0), default="baixa")
            max_status = max(
                statuses,
                key=lambda s: _STATUS_PRIORITY.get(s, 0),
                default="aberto",
            )
            valor_total = sum(a["valor_referencia"] or 0 for a in alerts)
            valor_max = max((a["valor_referencia"] or 0 for a in alerts), default=0)
            datas = [a["data_assinatura"] for a in alerts if a["data_assinatura"]]
            narrativa = next((a["narrativa_ia"] for a in alerts if a["narrativa_ia"]), None)

            items.append({
                "grupo_id": f"{fni}__{tp}",
                "fornecedor": gr["fornecedor_nome"] or fni,
                "tipo": tp,
                "severidade": max_sev,
                "status": max_status,
                "score_composto": round(float(gr["score_composto"] or 0), 4),
                "ocorrencias": len(alerts),
                "valor_total": valor_total,
                "valor_max": valor_max,
                "data_mais_recente": max(datas) if datas else None,
                "narrativa_ia": narrativa,
                "alertas": [
                    {
                        "id": a["id"],
                        "status": a["status"] or "aberto",
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

        return jsonify({
            "items": items,
            "total": total,
            "page": page,
            "pages": pages,
            "municipio_ibge": _municipio_ibge_request(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Alertas — detail
# ---------------------------------------------------------------------------

@app.route("/api/alertas/<int:alert_id>", methods=["GET", "PATCH", "OPTIONS"])
def alertas_detail(alert_id: int):
    if request.method == "OPTIONS":
        return "", 204

    if request.method == "PATCH":
        from db.triagem import (
            AlertaNaoEncontradoError,
            TriagemError,
            atualizar_status_alerta,
        )

        body = request.get_json(silent=True) or {}
        status = body.get("status")
        if not status:
            return jsonify({"error": "Campo 'status' é obrigatório."}), 400

        db = get_db()
        try:
            resultado = atualizar_status_alerta(
                db,
                alert_id,
                status=str(status),
                nota=body.get("nota"),
                motivo_descarte=body.get("motivo_descarte"),
            )
            return jsonify(resultado)
        except AlertaNaoEncontradoError:
            return jsonify({"error": "not found"}), 404
        except TriagemError as exc:
            return jsonify({"error": str(exc)}), 422
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        finally:
            db.close()

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
        from db.transparencia_cruzamentos import listar_empenhos_vinculados
        from db.triagem import listar_historico, normalizar_status, status_permitidos

        payload = dict(row)
        payload["status"] = normalizar_status(payload.get("status"))
        payload["historico"] = listar_historico(db, alert_id)
        payload["transicoes_permitidas"] = status_permitidos(payload["status"])
        payload["transparencia_rj"] = listar_empenhos_vinculados(
            db, payload.get("numero_controle_pncp")
        )
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/alertas/<int:alert_id>/investigar", methods=["POST", "OPTIONS"])
def alertas_investigar(alert_id: int):
    if request.method == "OPTIONS":
        return "", 204

    usuario, erro = checar_cota_ia()
    if erro:
        return erro

    from analise.motor_ia import InvestigadorIA, _revisao_gemini_disponivel
    from db.conexao import DB_PATH
    from db.database import GerenciadorBanco

    db = get_db()
    try:
        row = db.execute(
            """
            SELECT a.id, a.tipo, a.severidade, a.descricao, a.metodologia,
                   a.valor_referencia, a.numero_controle_pncp, a.status,
                   COALESCE(c.objeto, '') AS objeto,
                   COALESCE(c.valor_global, 0) AS valor_global,
                   COALESCE(f.razao_social, '') AS fornecedor
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            WHERE a.id = ?
            """,
            (alert_id,),
        ).fetchone()
        if row is None:
            return jsonify({"error": "not found"}), 404

        try:
            investigador = InvestigadorIA()
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 503

        payload = dict(row)
        resultado = investigador.investigar_anomalia(payload)
        GerenciadorBanco(db_path=DB_PATH).atualizar_narrativa_anomalia(
            alert_id,
            resultado.narrativa_ia,
            narrativa_gemma=resultado.narrativa_gemma,
            gemma_utilizado=1 if resultado.narrativa_gemma else 0,
        )
        registrar_consumo_ia(usuario, "investigar")
        from analise.motor_ia import NOMES_PROVEDOR

        return jsonify({
            "id": alert_id,
            "narrativa_ia": resultado.narrativa_ia,
            "narrativa_gemma": resultado.narrativa_gemma,
            "corpo": resultado.corpo,
            "veredito_gemini": resultado.veredito_gemini,
            "veredito_gemma": resultado.veredito_gemma,
            "gemini_utilizado": resultado.gemini_utilizado,
            "gemma4_utilizado": resultado.gemma4_utilizado,
            "chars": len(resultado.narrativa_ia),
            "revisao_gemini": _revisao_gemini_disponivel(),
            "revisao_gemma4": resultado.gemma4_utilizado,
            "provedor_primario": resultado.provedor_primario,
            "provedor_secundario": resultado.provedor_secundario,
            "provedor_primario_nome": NOMES_PROVEDOR.get(
                resultado.provedor_primario, resultado.provedor_primario
            ),
            "provedor_secundario_nome": NOMES_PROVEDOR.get(
                resultado.provedor_secundario, resultado.provedor_secundario
            ),
        })
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Investigação Profunda — Agente ReAct
# ---------------------------------------------------------------------------

@app.route("/api/alertas/<int:alert_id>/investigar_profundo", methods=["POST", "OPTIONS"])
def alertas_investigar_profundo(alert_id: int):
    if request.method == "OPTIONS":
        return "", 204

    usuario, erro = checar_cota_ia()
    if erro:
        return erro

    db = get_db()
    try:
        row = db.execute(
            """
            SELECT a.id, a.tipo, a.severidade, a.descricao, a.metodologia,
                   a.valor_referencia, a.numero_controle_pncp, a.status,
                   COALESCE(c.objeto, '') AS objeto,
                   COALESCE(c.valor_global, 0) AS valor_global,
                   COALESCE(f.razao_social, '') AS fornecedor_nome,
                   COALESCE(f.ni, '') AS fornecedor_ni,
                   COALESCE(o.cnpj, '') AS orgao_cnpj,
                   COALESCE(o.razao_social, '') AS orgao_nome
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

        dados_alerta = dict(row)
    finally:
        db.close()

    db2 = get_db()
    try:
        inv_existente = db2.execute(
            """
            SELECT id, status FROM investigacoes
            WHERE alerta_id = ? AND status = 'rodando'
            ORDER BY id DESC LIMIT 1
            """,
            (alert_id,),
        ).fetchone()
        if inv_existente:
            return jsonify({"status": "ja_rodando", "alerta_id": alert_id}), 202
    finally:
        db2.close()

    db3 = get_db()
    try:
        cur = db3.execute(
            """
            INSERT INTO investigacoes (alerta_id, status, iniciado_em)
            VALUES (?, 'rodando', ?)
            """,
            (alert_id, datetime.now(timezone.utc).isoformat()),
        )
        inv_id = cur.lastrowid
        db3.commit()
    finally:
        db3.close()

    registrar_consumo_ia(usuario, "investigar_profundo")

    def _rodar_agente(alerta_id: int, inv_id: int, dados: dict) -> None:
        from investigacao import AgenteInvestigador

        resultado = AgenteInvestigador().investigar(alerta_id, dados)

        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                """
                UPDATE investigacoes SET
                    status = ?,
                    concluido_em = ?,
                    evidencias = ?,
                    sintese = ?,
                    conclusao = ?,
                    grau_confianca = ?,
                    recomendacao = ?,
                    erro = ?
                WHERE id = ?
                """,
                (
                    resultado.status,
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(resultado.evidencias, ensure_ascii=False, default=str),
                    resultado.sintese,
                    resultado.conclusao,
                    resultado.grau_confianca,
                    resultado.recomendacao,
                    resultado.erro,
                    inv_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    thread = threading.Thread(
        target=_rodar_agente,
        args=(alert_id, inv_id, dados_alerta),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "status": "iniciado",
        "alerta_id": alert_id,
        "inv_id": inv_id,
        "mensagem": "Investigação profunda iniciada em background.",
    }), 202


@app.route("/api/investigacoes/<int:alert_id>/status", methods=["GET"])
def investigacao_status(alert_id: int):
    """Retorna o status atual da investigação profunda do alerta."""
    db = get_db()
    try:
        row = db.execute(
            """
            SELECT id, status, iniciado_em, concluido_em,
                   sintese, conclusao, grau_confianca, recomendacao, erro,
                   evidencias
            FROM investigacoes
            WHERE alerta_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (alert_id,),
        ).fetchone()

        if row is None:
            return jsonify({"status": "nenhuma"}), 200

        dados = dict(row)

        ev: dict = {}
        try:
            ev = json.loads(dados.get("evidencias") or "{}")
        except Exception:
            pass

        return jsonify({
            "id": dados["id"],
            "alerta_id": alert_id,
            "status": dados["status"],
            "iniciado_em": dados["iniciado_em"],
            "concluido_em": dados["concluido_em"],
            "sintese": dados["sintese"],
            "conclusao": dados["conclusao"],
            "grau_confianca": dados["grau_confianca"],
            "recomendacao": dados["recomendacao"],
            "erro": dados["erro"],
            "resumos": {
                "cadastro": (ev.get("cadastro") or {}).get("resumo"),
                "historico_fornecedor": (ev.get("historico_fornecedor") or {}).get("resumo"),
                "historico_orgao": (ev.get("historico_orgao") or {}).get("resumo"),
                "processos_tjrj": (ev.get("processos_tjrj") or {}).get("resumo"),
                "decisoes_tcm": (ev.get("decisoes_tcm") or {}).get("resumo"),
            },
        })
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Dossiê investigativo
# ---------------------------------------------------------------------------

@app.route("/api/dossie/<int:alerta_id>")
def dossie_api(alerta_id: int):
    from relatorios.dossie import (
        DossieNaoEncontradoError,
        obter_dossie,
        renderizar_markdown,
        renderizar_pdf,
        serializar_json,
    )

    formato = request.args.get("formato", "json").strip().lower()
    gerar_ia = request.args.get("gerar_ia", "false").strip().lower() in (
        "true",
        "1",
        "yes",
    )
    usuario = None
    if gerar_ia:
        usuario, erro = checar_cota_ia()
        if erro:
            return erro
    db = get_db()
    try:
        dados = obter_dossie(db, alerta_id, gerar_ia=gerar_ia, db_path=DB_PATH)
        if gerar_ia:
            registrar_consumo_ia(usuario, "dossie_ia")
    except DossieNaoEncontradoError:
        return jsonify({"error": "not found"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()

    if formato == "md":
        return Response(
            renderizar_markdown(dados),
            mimetype="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="dossie-alerta-{alerta_id}.md"'
                ),
            },
        )
    if formato == "pdf":
        return Response(
            renderizar_pdf(dados),
            mimetype="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="dossie-alerta-{alerta_id}.pdf"'
                ),
            },
        )
    return jsonify(serializar_json(dados))


# ---------------------------------------------------------------------------
# Pipeline — status operacional
# ---------------------------------------------------------------------------

def _saude_pipeline(ultima_coleta: dict | None, janela_dias: int) -> str:
    if not ultima_coleta or not ultima_coleta.get("finalizado_em"):
        return "desconhecido"
    obs = (ultima_coleta.get("observacao") or "").lower()
    if any(termo in obs for termo in ("erro", "falha", "exception", "traceback")):
        return "falha"
    try:
        bruto = str(ultima_coleta["finalizado_em"]).replace("Z", "")
        fim = datetime.fromisoformat(bruto.split(".")[0])
        limite = max(int(janela_dias) + 2, 3)
        if (datetime.now() - fim).days > limite:
            return "atencao"
    except (ValueError, TypeError):
        return "atencao"
    return "ok"


@app.route("/api/pipeline/status")
def pipeline_status():
    from automacoes.pipeline import PipelineConfig

    db = get_db()
    try:
        row = db.execute(
            """
            SELECT fonte, data_inicial, data_final, paginas_lidas,
                   registros_brutos, registros_municipio,
                   iniciado_em, finalizado_em, observacao
            FROM coletas_log
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        ultima_coleta = dict(row) if row else None

        cfg = PipelineConfig.from_env()
        log_dir = Path(__file__).resolve().parent / "logs"
        log_hoje = log_dir / f"pipeline_{datetime.now().strftime('%Y%m%d')}.txt"
        ultimas_linhas: list[str] = []
        if log_hoje.is_file():
            linhas = log_hoje.read_text(encoding="utf-8", errors="replace").splitlines()
            ultimas_linhas = [ln for ln in linhas if ln.strip()][-8:]

        return jsonify({
            "ultima_coleta": ultima_coleta,
            "saude": _saude_pipeline(ultima_coleta, cfg.janela_dias),
            "pipeline": {
                "cron": cfg.cron,
                "timezone": cfg.timezone,
                "janela_dias": cfg.janela_dias,
                "investigar_limite": cfg.investigar_limite,
                "skip_investigar": cfg.skip_investigar,
                "discord_configurado": bool(os.getenv("DISCORD_WEBHOOK_URL", "").strip()),
            },
            "log_hoje": str(log_hoje) if log_hoje.is_file() else None,
            "log_ultimas_linhas": ultimas_linhas,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
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
        ibge = _municipio_ibge_request()
        strftime_expr = (
            "strftime('%Y-%m', c.data_assinatura)"
            if granularity == "month"
            else "strftime('%Y', c.data_assinatura)"
        )
        conditions = ["c.valor_global > 0", "c.data_assinatura IS NOT NULL"]
        params: list = []
        join_o = ""
        if ibge:
            join_o = "JOIN orgaos o ON o.cnpj = c.orgao_cnpj"
            _aplicar_filtro_municipio(conditions, params, ibge)
        where = "WHERE " + " AND ".join(conditions)
        rows = db.execute(
            f"""
            SELECT {strftime_expr} AS periodo,
                   COUNT(*) AS contratos,
                   SUM(c.valor_global) AS valor
            FROM contratos c
            {join_o}
            {where}
            GROUP BY periodo
            ORDER BY periodo
            """,
            params,
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
        ibge = _municipio_ibge_request()
        join_o = ""
        if ibge:
            join_o = "JOIN orgaos o ON o.cnpj = c.orgao_cnpj"
            _aplicar_filtro_municipio(ranking_conditions, ranking_params, ibge)
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
            {join_o}
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

@app.route("/api/fornecedores/investigados")
def fornecedores_investigados():
    """Fornecedores com alertas no Sentinela — catálogo para o comparador."""
    db = get_db()
    try:
        q = request.args.get("q", "").strip()
        ibge = _municipio_ibge_request()
        params: list = []
        filtro_forn = ""
        filtro_mun_c = ""
        filtro_mun_a = ""
        if ibge:
            filtro_mun_c = "AND o.municipio_ibge = ?"
            filtro_mun_a = "AND o.municipio_ibge = ?"
            params.extend([ibge, ibge])
        if q:
            cnpj_q = q.replace(".", "").replace("/", "").replace("-", "")
            filtro_forn = "AND (f.razao_social LIKE ? OR f.ni LIKE ?)"
            params.extend([f"%{q}%", f"%{cnpj_q}%"])
        rows = db.execute(
            f"""
            WITH contratos_agg AS (
                SELECT c.fornecedor_ni,
                       COUNT(*) AS total_contratos,
                       COALESCE(SUM(c.valor_global), 0) AS valor_total
                FROM contratos c
                JOIN orgaos o ON o.cnpj = c.orgao_cnpj
                WHERE c.valor_global > 0 {filtro_mun_c}
                GROUP BY c.fornecedor_ni
            ),
            alertas_agg AS (
                SELECT c.fornecedor_ni,
                       COUNT(DISTINCT a.id) AS total_alertas,
                       COUNT(DISTINCT CASE WHEN a.severidade = 'alta' THEN a.id END) AS alertas_alta
                FROM alertas a
                JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
                JOIN orgaos o ON o.cnpj = c.orgao_cnpj
                WHERE c.valor_global > 0
                  AND COALESCE(a.status, 'aberto') != 'descartado'
                  {filtro_mun_a}
                GROUP BY c.fornecedor_ni
            )
            SELECT f.ni AS fornecedor_ni,
                   f.razao_social AS fornecedor,
                   aa.total_alertas,
                   aa.alertas_alta,
                   ca.total_contratos,
                   ca.valor_total,
                   COALESCE(f.tem_sancao, 0) AS tem_sancao
            FROM fornecedores f
            JOIN alertas_agg aa ON aa.fornecedor_ni = f.ni
            JOIN contratos_agg ca ON ca.fornecedor_ni = f.ni
            WHERE 1=1 {filtro_forn}
            ORDER BY aa.alertas_alta DESC, aa.total_alertas DESC, ca.valor_total DESC, f.razao_social
            """,
            params,
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["tem_sancao"] = bool(item.get("tem_sancao"))
            items.append(item)
        return jsonify({"items": items, "total": len(items)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


@app.route("/api/fornecedores/comparar")
def fornecedores_comparar():
    from analise.comparador import ComparadorError, montar_comparacao

    nis = request.args.getlist("ni")
    if not nis:
        bruto = request.args.get("nis", "").strip()
        if bruto:
            nis = [p.strip() for p in bruto.replace(";", ",").split(",") if p.strip()]
    if not nis:
        return jsonify({"error": "Informe ao menos dois CNPJs via ?ni= ou ?nis=."}), 400

    db = get_db()
    try:
        return jsonify(montar_comparacao(db, nis))
    except ComparadorError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


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

        alertas_abertos = db.execute(
            """SELECT COUNT(*) FROM alertas a
               JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
               WHERE c.fornecedor_ni = ?
                 AND COALESCE(a.status, 'aberto') IN ('aberto', 'investigando')""",
            (fornecedor_ni,),
        ).fetchone()[0]

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

        empenho_agg = db.execute(
            """SELECT COUNT(*) AS total, COALESCE(SUM(valor), 0) AS valor_total
               FROM transparencia_rj_lancamentos
               WHERE fornecedor_ni = ?""",
            (fornecedor_ni,),
        ).fetchone()
        empenhos_recentes = db.execute(
            """SELECT valor, data_lancamento, descricao, orgao, documento
               FROM transparencia_rj_lancamentos
               WHERE fornecedor_ni = ?
               ORDER BY data_lancamento DESC
               LIMIT 10""",
            (fornecedor_ni,),
        ).fetchall()

        return jsonify({
            "identidade": dict(forn),
            "cadastro": cadastro,
            "resumo": {
                "total_contratos": total_contratos,
                "valor_total": valor_total,
                "valor_medio": valor_medio,
                "alertas_abertos": alertas_abertos,
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
            "empenhos": {
                "total": empenho_agg["total"],
                "valor_total": empenho_agg["valor_total"],
                "recentes": [dict(r) for r in empenhos_recentes],
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
        ibge = _municipio_ibge_request()
        conditions: list[str] = []
        params: list = []
        _aplicar_filtro_municipio(conditions, params, ibge)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = db.execute(
            f"""
            SELECT o.razao_social AS orgao,
                   o.cnpj,
                   o.municipio_nome,
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
            {where}
            GROUP BY o.cnpj
            ORDER BY total_alertas DESC
            """,
            params,
        ).fetchall()
        return jsonify({"items": [dict(r) for r in rows], "municipio_ibge": ibge})
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
        ibge = _municipio_ibge_request()
        conditions: list[str] = []
        params: list = []
        _aplicar_filtro_municipio(conditions, params, ibge)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = db.execute(
            f"""
            SELECT a.tipo, a.severidade, COUNT(*) AS quantidade
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            {where}
            GROUP BY a.tipo, a.severidade
            ORDER BY a.tipo, a.severidade
            """,
            params,
        ).fetchall()
        return jsonify({"items": [dict(r) for r in rows], "municipio_ibge": ibge})
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
        ibge = _municipio_ibge_request()
        conditions = ["c.valor_global > 0"]
        params: list = []
        _aplicar_filtro_municipio(conditions, params, ibge)
        where = "WHERE " + " AND ".join(conditions)
        rows = db.execute(
            f"""
            SELECT c.numero_controle_pncp, c.objeto, c.categoria_processo_nome,
                   c.valor_global, c.data_assinatura, c.data_vigencia_inicio,
                   c.data_vigencia_fim, f.razao_social AS fornecedor,
                   f.ni AS fornecedor_cnpj, o.razao_social AS orgao,
                   c.orgao_cnpj, c.unidade_nome, o.municipio_nome
            FROM contratos c
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            {where}
            ORDER BY c.data_assinatura DESC
            """,
            params,
        ).fetchall()

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
        ibge = _municipio_ibge_request()
        conditions: list[str] = []
        params: list = []
        _aplicar_filtro_municipio(conditions, params, ibge)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = db.execute(
            f"""
            SELECT a.id, a.tipo, a.severidade, a.descricao, a.valor_referencia,
                   a.metodologia, a.narrativa_ia, a.criado_em,
                   f.razao_social AS fornecedor, f.ni AS fornecedor_cnpj,
                   c.objeto, c.data_assinatura, c.valor_global,
                   o.razao_social AS orgao, o.municipio_nome
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            {where}
            ORDER BY a.severidade DESC, a.valor_referencia DESC
            """,
            params,
        ).fetchall()

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
# Grafo investigativo
# ---------------------------------------------------------------------------

@app.route("/api/grafo/fornecedor/<fornecedor_ni>")
def grafo_fornecedor(fornecedor_ni: str):
    from analise.grafo import GrafoNaoEncontradoError, montar_grafo_fornecedor

    db = get_db()
    try:
        return jsonify(montar_grafo_fornecedor(db, fornecedor_ni))
    except GrafoNaoEncontradoError:
        return jsonify({"error": "not found"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


@app.route("/api/grafo/alerta/<int:alerta_id>")
def grafo_alerta(alerta_id: int):
    from analise.grafo import GrafoNaoEncontradoError, montar_grafo_alerta

    db = get_db()
    try:
        return jsonify(montar_grafo_alerta(db, alerta_id))
    except GrafoNaoEncontradoError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
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
        ibge = _municipio_ibge_request()
        conditions = [
            "fc.socios IS NOT NULL",
            "fc.socios != '[]'",
            "ct.valor_global > 0",
        ]
        params: list = []
        if ibge:
            conditions.append("o.municipio_ibge = ?")
            params.append(ibge)
        where = "WHERE " + " AND ".join(conditions)
        rows = db.execute(
            f"""
            SELECT fc.fornecedor_ni,
                   fc.socios,
                   f.razao_social,
                   COUNT(ct.numero_controle_pncp) AS total_contratos,
                   SUM(ct.valor_global)            AS valor_total
            FROM fornecedor_cadastro fc
            JOIN fornecedores f  ON f.ni  = fc.fornecedor_ni
            JOIN contratos ct    ON ct.fornecedor_ni = fc.fornecedor_ni
            JOIN orgaos o ON o.cnpj = ct.orgao_cnpj
            {where}
            GROUP BY fc.fornecedor_ni
            """,
            params,
        ).fetchall()

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
# Empenhos — lançamentos diários PNCP
# ---------------------------------------------------------------------------

@app.route("/api/empenhos")
def empenhos_list():
    db = get_db()
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(200, max(1, int(request.args.get("per_page", 50))))
        fornecedor_ni = request.args.get("fornecedor_ni", "").strip()
        data_ini = request.args.get("data_ini", "").strip()
        data_fim = request.args.get("data_fim", "").strip()
        q = request.args.get("q", "").strip()

        base = """
            FROM transparencia_rj_lancamentos l
            LEFT JOIN fornecedores f ON f.ni = l.fornecedor_ni
        """
        conditions: list[str] = []
        params: list = []

        if fornecedor_ni:
            conditions.append("l.fornecedor_ni = ?")
            params.append(fornecedor_ni)
        if q:
            cnpj_q = q.replace(".", "").replace("/", "").replace("-", "")
            conditions.append("(f.razao_social LIKE ? OR l.fornecedor_ni LIKE ?)")
            params.extend([f"%{q}%", f"%{cnpj_q}%"])
        if data_ini:
            conditions.append("l.data_lancamento >= ?")
            params.append(data_ini)
        if data_fim:
            conditions.append("l.data_lancamento <= ?")
            params.append(data_fim)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = db.execute(
            f"SELECT COUNT(*) {base} {where}", params
        ).fetchone()[0]
        valor_total = db.execute(
            f"SELECT COALESCE(SUM(l.valor), 0) {base} {where}", params
        ).fetchone()[0]
        offset = (page - 1) * per_page

        rows = db.execute(
            f"""
            SELECT l.id, l.fornecedor_ni,
                   COALESCE(f.razao_social, l.fornecedor_ni) AS razao_social,
                   l.valor, l.data_lancamento, l.descricao,
                   l.orgao, l.documento, l.coletado_em
            {base} {where}
            ORDER BY l.data_lancamento DESC, l.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

        return jsonify({
            "total": total,
            "valor_total": valor_total,
            "page": page,
            "per_page": per_page,
            "items": [dict(r) for r in rows],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Watchlists — CRUD
# ---------------------------------------------------------------------------

@app.route("/api/watchlists", methods=["GET", "POST", "OPTIONS"])
def watchlists_collection():
    if request.method == "OPTIONS":
        return "", 204

    from db.watchlists import WatchlistError, criar_watchlist, listar_watchlists

    db = get_db()
    try:
        if request.method == "GET":
            apenas_ativas = request.args.get("ativo", "").strip() == "1"
            return jsonify({"items": listar_watchlists(db, apenas_ativas=apenas_ativas)})

        body = request.get_json(silent=True) or {}
        if not body.get("rotulo"):
            return jsonify({"error": "Campo 'rotulo' é obrigatório."}), 400
        item = criar_watchlist(
            db,
            rotulo=str(body["rotulo"]),
            fornecedor_ni=body.get("fornecedor_ni"),
            orgao_cnpj=body.get("orgao_cnpj"),
            palavra_chave_objeto=body.get("palavra_chave_objeto"),
            ativo=int(body.get("ativo", 1)),
        )
        return jsonify(item), 201
    except WatchlistError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


@app.route("/api/watchlists/<int:watchlist_id>", methods=["GET", "PATCH", "DELETE", "OPTIONS"])
def watchlists_detail(watchlist_id: int):
    if request.method == "OPTIONS":
        return "", 204

    from db.watchlists import WatchlistError, atualizar_watchlist, desativar_watchlist, obter_watchlist

    db = get_db()
    try:
        if request.method == "GET":
            item = obter_watchlist(db, watchlist_id)
            if item is None:
                return jsonify({"error": "not found"}), 404
            return jsonify(item)

        if request.method == "DELETE":
            desativar_watchlist(db, watchlist_id)
            return jsonify({"ok": True, "id": watchlist_id, "ativo": 0})

        body = request.get_json(silent=True) or {}
        item = atualizar_watchlist(db, watchlist_id, body)
        return jsonify(item)
    except WatchlistError as exc:
        status = 404 if "não encontrada" in str(exc) else 422
        return jsonify({"error": str(exc)}), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Regras de alerta — CRUD
# ---------------------------------------------------------------------------

@app.route("/api/regras-alerta", methods=["GET", "POST", "OPTIONS"])
def regras_alerta_collection():
    if request.method == "OPTIONS":
        return "", 204

    from db.regras_alerta import RegraAlertaError, criar_regra, listar_regras

    db = get_db()
    try:
        if request.method == "GET":
            apenas_ativas = request.args.get("ativo", "").strip() == "1"
            return jsonify({"items": listar_regras(db, apenas_ativas=apenas_ativas)})

        body = request.get_json(silent=True) or {}
        if not body.get("severidade_min"):
            return jsonify({"error": "Campo 'severidade_min' é obrigatório."}), 400
        item = criar_regra(
            db,
            tipo=body.get("tipo"),
            severidade_min=str(body["severidade_min"]),
            valor_min=float(body.get("valor_min", 0)),
            ativo=int(body.get("ativo", 1)),
        )
        return jsonify(item), 201
    except RegraAlertaError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


@app.route("/api/regras-alerta/<int:regra_id>", methods=["GET", "PATCH", "DELETE", "OPTIONS"])
def regras_alerta_detail(regra_id: int):
    if request.method == "OPTIONS":
        return "", 204

    from db.regras_alerta import RegraAlertaError, atualizar_regra, desativar_regra, obter_regra

    db = get_db()
    try:
        if request.method == "GET":
            item = obter_regra(db, regra_id)
            if item is None:
                return jsonify({"error": "not found"}), 404
            return jsonify(item)

        if request.method == "DELETE":
            desativar_regra(db, regra_id)
            return jsonify({"ok": True, "id": regra_id, "ativo": 0})

        body = request.get_json(silent=True) or {}
        kwargs: dict = {}
        if "tipo" in body:
            kwargs["tipo"] = body["tipo"]
        if "severidade_min" in body:
            kwargs["severidade_min"] = body["severidade_min"]
        if "valor_min" in body:
            kwargs["valor_min"] = float(body["valor_min"])
        if "ativo" in body:
            kwargs["ativo"] = int(body["ativo"])
        item = atualizar_regra(db, regra_id, **kwargs)
        return jsonify(item)
    except RegraAlertaError as exc:
        status = 404 if "não encontrada" in str(exc) else 422
        return jsonify({"error": str(exc)}), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Casos investigados — página pública + admin CRUD
# ---------------------------------------------------------------------------

_CASOS_SEED = [
    {
        "titulo": "MJRE Construtora — Suspensão Judicial",
        "fornecedor_nome": "MJRE Construtora Ltda",
        "fornecedor_cnpj": "05851921000181",
        "valor": 315_980_953.18,
        "tipo_anomalia": "outlier_valor",
        "status": "suspenso",
        "resumo": (
            "Contrato de R$ 315.980.953,18 assinado em 23/03/2026 para Fresagem, Recapeamento "
            "Asfáltico e Sinalização Horizontal nas AP1 e AP2 — Programa Asfalto Liso Fase 3. "
            "Onze dias após a assinatura, a 3ª Vara da Fazenda Pública do TJRJ (juíza Mirela "
            "Erbisti) suspendeu o contrato por liminar, após ação apontando que a proposta "
            "vencedora era R$ 25 milhões mais cara do que a concorrente desclassificada. "
            "O Sentinela identificou o valor como outlier severo: 11,4× acima do limite IQR "
            "para a categoria Serviços de Engenharia (Z-score 8,7). Capital social da MJRE "
            "(R$ 16,5 mi) corresponde a apenas 4,6% do volume total contratado pela empresa."
        ),
        "ordem": 1,
    },
    {
        "titulo": "Bonus Track — Inexigibilidade Shows Copacabana",
        "fornecedor_nome": "Bonus Track Produções Ltda",
        "fornecedor_cnpj": "07072702000120",
        "valor": 70_000_000.0,
        "tipo_anomalia": "sem_licitacao_inexigibilidade",
        "status": "investigando",
        "resumo": (
            "Três contratos consecutivos por inexigibilidade (Art. 74, Lei 14.133/2021) "
            "somam R$ 70 milhões: Madonna em Copacabana (R$ 10 mi, abr/2024), Lady Gaga "
            "(R$ 15 mi, abr/2025) e pacote 'Todo Mundo no Rio 2026–2028' (R$ 45 mi, abr/2026) "
            "— três shows anuais a R$ 15 mi cada. O valor exato R$ 45.000.000,00 e a escalada "
            "sistemática de cachês suscitam questionamento sobre a adequação da exclusividade "
            "invocada: a Bonus Track não é produtora das artistas, apenas intermediária. "
            "O conjunto representa padrão de captura de mercado via contratação direta."
        ),
        "ordem": 2,
    },
    {
        "titulo": "Construtora Entre os Rios — Concentração Atípica",
        "fornecedor_nome": "Construtora Entre os Rios Ltda",
        "fornecedor_cnpj": "30307631000119",
        "valor": 86_480_775.04,
        "tipo_anomalia": "concentracao_fornecedor",
        "status": "investigando",
        "resumo": (
            "Quatro contratos com a Prefeitura do Rio em menos de 30 dias (09/03 a 08/04/2026), "
            "todos pelo mesmo órgão contratante, totalizando R$ 86,5 milhões: grama sintética "
            "e alambrados nas AP4/AP5 (R$ 45,9 mi), parque linear na Maré/AP3 (R$ 8,5 mi), "
            "urbanização em Vargem Pequena/AP4 (R$ 14,9 mi) e calçadão de Campo Grande "
            "(R$ 17,3 mi). O detector identificou concentração de 5 contratos em 90 dias "
            "(R$ 86,7 mi). Capital social de R$ 5,5 mi cobre apenas 4,3% do volume contratado "
            "(R$ 126,5 mi acumulados). Evolução de 1 para 4 contratos em 90 dias (×4,0)."
        ),
        "ordem": 3,
    },
    {
        "titulo": "Padrão Asfalto Fatiado — R$ 584mi em Pavimentação",
        "fornecedor_nome": "MJRE, Hydra, Metropolitana, Santa Luzia, Matos Costa",
        "fornecedor_cnpj": None,
        "valor": 584_271_894.23,
        "tipo_anomalia": "fracionamento_ap",
        "status": "investigando",
        "resumo": (
            "Cinco empresas dividiram R$ 584 milhões em contratos de pavimentação asfáltica "
            "distribuídos pelas cinco APs do Rio, firmados entre fev/2026 e mar/2026. "
            "Programa Conservação Fase 2 (R$ 268 mi, 4 empresas): Hydra/AP3 R$ 84,5 mi, "
            "Metropolitana/AP5 R$ 76,6 mi, Santa Luzia/AP4 R$ 60,5 mi, Matos Costa/AP1-2 "
            "R$ 46,7 mi. Programa Asfalto Liso Fase 3 (R$ 316 mi): MJRE/AP1-2 — contrato "
            "suspenso judicialmente. O fracionamento geográfico por AP distribui o objeto "
            "entre concorrências separadas, evitando a modalidade de grande vulto que exigiria "
            "concorrência pública unificada e maior escrutínio."
        ),
        "ordem": 4,
    },
]


def _seed_casos(db: sqlite3.Connection) -> None:
    """Insere os casos iniciais se a tabela estiver vazia."""
    n = db.execute("SELECT COUNT(*) FROM casos").fetchone()[0]
    if n > 0:
        return
    for c in _CASOS_SEED:
        db.execute(
            """INSERT INTO casos (titulo, fornecedor_nome, fornecedor_cnpj, valor,
               tipo_anomalia, status, resumo, ordem)
               VALUES (?,?,?,?,?,?,?,?)""",
            (c["titulo"], c["fornecedor_nome"], c["fornecedor_cnpj"], c["valor"],
             c["tipo_anomalia"], c["status"], c["resumo"], c["ordem"]),
        )
    db.commit()


@app.route("/casos")
def casos_page():
    db = get_db()
    try:
        _seed_casos(db)
        stats_row = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(valor_global),0) FROM contratos WHERE valor_global > 0"
        ).fetchone()
        return render_template(
            "casos.html",
            total_contratos=stats_row[0],
            valor_total=stats_row[1],
        )
    finally:
        db.close()


@app.route("/admin/casos")
def admin_casos_page():
    return render_template("admin_casos.html")


@app.route("/api/casos", methods=["GET"])
def api_casos_list():
    db = get_db()
    try:
        _seed_casos(db)
        rows = db.execute(
            "SELECT * FROM casos ORDER BY ordem ASC, id ASC"
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route("/api/casos", methods=["POST"])
@requer_admin
def api_casos_create():
    data = request.get_json(force=True)
    required = ("titulo", "status")
    for field_name in required:
        if not data.get(field_name):
            return jsonify({"error": f"Campo obrigatório: {field_name}"}), 422
    db = get_db()
    try:
        cur = db.execute(
            """INSERT INTO casos (titulo, fornecedor_nome, fornecedor_cnpj, valor,
               tipo_anomalia, status, resumo, ordem)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                data["titulo"],
                data.get("fornecedor_nome"),
                data.get("fornecedor_cnpj", "").replace(".", "").replace("/", "").replace("-", "") or None,
                data.get("valor"),
                data.get("tipo_anomalia"),
                data["status"],
                data.get("resumo"),
                int(data.get("ordem", 0)),
            ),
        )
        db.commit()
        row = db.execute("SELECT * FROM casos WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201
    except sqlite3.IntegrityError as e:
        return jsonify({"error": str(e)}), 422
    finally:
        db.close()


@app.route("/api/casos/<int:caso_id>", methods=["PATCH"])
@requer_admin
def api_casos_update(caso_id: int):
    data = request.get_json(force=True)
    db = get_db()
    try:
        row = db.execute("SELECT id FROM casos WHERE id = ?", (caso_id,)).fetchone()
        if not row:
            return jsonify({"error": "Caso não encontrado"}), 404
        fields = ["titulo", "fornecedor_nome", "fornecedor_cnpj", "valor",
                  "tipo_anomalia", "status", "resumo", "ordem"]
        sets, vals = [], []
        for f in fields:
            if f in data:
                v = data[f]
                if f == "fornecedor_cnpj" and v:
                    v = str(v).replace(".", "").replace("/", "").replace("-", "") or None
                sets.append(f"{f} = ?")
                vals.append(v)
        if not sets:
            return jsonify({"error": "Nenhum campo para atualizar"}), 422
        sets.append("atualizado_em = datetime('now')")
        vals.append(caso_id)
        db.execute(f"UPDATE casos SET {', '.join(sets)} WHERE id = ?", vals)
        db.commit()
        updated = db.execute("SELECT * FROM casos WHERE id = ?", (caso_id,)).fetchone()
        return jsonify(dict(updated))
    finally:
        db.close()


@app.route("/api/casos/<int:caso_id>", methods=["DELETE"])
@requer_admin
def api_casos_delete(caso_id: int):
    db = get_db()
    try:
        row = db.execute("SELECT id FROM casos WHERE id = ?", (caso_id,)).fetchone()
        if not row:
            return jsonify({"error": "Caso não encontrado"}), 404
        db.execute("DELETE FROM casos WHERE id = ?", (caso_id,))
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Relatório PDF
# ---------------------------------------------------------------------------

@app.route("/relatorio/pdf")
def relatorio_pdf():
    from relatorios.pdf_export import gerar_pdf_bytes
    db = get_db()
    try:
        pdf_bytes = gerar_pdf_bytes(db)
    finally:
        db.close()
    hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="sentinela-rj-{hoje}.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from waitress import serve

    port = int(os.environ.get("PORT", 5055))
    serve(app, host="0.0.0.0", port=port)
