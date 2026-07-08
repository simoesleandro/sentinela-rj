"""Painel — municípios, stats, timeline, status do pipeline, anomalias e empenhos."""
import os
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

import web_app as core

bp = Blueprint("painel", __name__)


@bp.route("/api/municipios")
def municipios_list():
    from extrator.config_municipio import (
        municipio_esfera,
        municipio_ibge,
        municipio_nome,
        municipios_monitorados,
        rotulo_filtro,
    )
    from db.filtro_municipio import listar_municipios

    db = core.get_db()
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
@bp.route("/api/stats")
def stats():
    db = core.get_db()
    try:
        ibge = core._municipio_ibge_request()
        join_o = "JOIN orgaos o ON o.cnpj = c.orgao_cnpj" if ibge else ""
        where_mun: list[str] = []
        params_mun: list = []
        core._aplicar_filtro_municipio(where_mun, params_mun, ibge)
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


@bp.route("/api/pipeline/status")
def pipeline_status():
    from automacoes.pipeline import PipelineConfig

    db = core.get_db()
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
        log_dir = Path(core.__file__).resolve().parent / "logs"
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
@bp.route("/api/timeline")
def timeline():
    db = core.get_db()
    try:
        granularity = request.args.get("granularity", "month")
        ibge = core._municipio_ibge_request()
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
            core._aplicar_filtro_municipio(conditions, params, ibge)
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
# Anomalias por tipo
# ---------------------------------------------------------------------------
@bp.route("/api/anomalias/por-tipo")
def anomalias_por_tipo():
    db = core.get_db()
    try:
        ibge = core._municipio_ibge_request()
        conditions: list[str] = []
        params: list = []
        core._aplicar_filtro_municipio(conditions, params, ibge)
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
# Empenhos — lançamentos diários PNCP
# ---------------------------------------------------------------------------
@bp.route("/api/empenhos")
def empenhos_list():
    db = core.get_db()
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
