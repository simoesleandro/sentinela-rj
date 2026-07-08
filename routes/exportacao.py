"""Exportação — CSVs de dados abertos e relatório PDF."""
import csv
import io
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify

import web_app as core

bp = Blueprint("exportacao", __name__)


# ---------------------------------------------------------------------------
# Export — CSV downloads
# ---------------------------------------------------------------------------
@bp.route("/api/export/contratos")
def export_contratos():
    db = core.get_db()
    try:
        ibge = core._municipio_ibge_request()
        conditions = ["c.valor_global > 0"]
        params: list = []
        core._aplicar_filtro_municipio(conditions, params, ibge)
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


@bp.route("/api/export/alertas")
def export_alertas():
    db = core.get_db()
    try:
        ibge = core._municipio_ibge_request()
        conditions: list[str] = []
        params: list = []
        core._aplicar_filtro_municipio(conditions, params, ibge)
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
# Relatório PDF
# ---------------------------------------------------------------------------
@bp.route("/relatorio/pdf")
def relatorio_pdf():
    from relatorios.pdf_export import gerar_pdf_bytes
    db = core.get_db()
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
