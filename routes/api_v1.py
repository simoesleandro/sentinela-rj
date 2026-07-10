"""API pública versionada (v1) — somente leitura.

Expõe alertas, contratos e a precisão medida sob /api/v1/*, com um contrato
estável documentado em OpenAPI (/api/v1/openapi.json) e Swagger UI em /api/docs.
Reusa os recursos compartilhados de web_app (get_db, filtros, score SQL). Escrita,
IA e admin continuam FORA da API pública.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

import web_app as core
from routes.openapi_spec import build_spec

bp = Blueprint("api_v1", __name__, url_prefix="/api")

_PER_PAGE_MAX = 100
_PER_PAGE_DEFAULT = 20


def _paginacao() -> tuple[int, int]:
    """Lê e sanitiza page/per_page da query string."""
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", _PER_PAGE_DEFAULT))
    except (TypeError, ValueError):
        per_page = _PER_PAGE_DEFAULT
    per_page = min(_PER_PAGE_MAX, max(1, per_page))
    return page, per_page


def _envelope(items: list, total: int, page: int, per_page: int) -> dict:
    import math

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": math.ceil(total / per_page) if total else 0,
    }


@bp.route("/docs")
def api_docs():
    """Documentação interativa (Swagger UI) da API pública."""
    return render_template("api_docs.html")


def _server_url() -> str:
    """URL base honrando o proxy TLS do Fly (evita http:// em página https)."""
    # Fly termina o TLS no proxy; a app vê http. X-Forwarded-Proto traz o
    # esquema original (pode vir como lista "https,http" — usa o primeiro).
    proto = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip()
    return f"{proto}://{request.host}"


@bp.route("/v1/openapi.json")
def openapi_json():
    """Especificação OpenAPI 3.0 servida como JSON."""
    return jsonify(build_spec(server_url=_server_url()))


@bp.route("/v1/alertas")
def v1_alertas():
    """Lista alertas de anomalia com o contrato associado (paginado)."""
    db = core.get_db()
    try:
        page, per_page = _paginacao()
        tipo = request.args.get("tipo")
        severidade = request.args.get("severidade")

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
        core._aplicar_filtro_municipio(conditions, params, core._municipio_ibge_request())
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = db.execute(f"SELECT COUNT(*) {base} {where}", params).fetchone()[0]
        offset = (page - 1) * per_page
        rows = db.execute(
            f"""
            SELECT a.id, a.tipo, a.severidade, {core._SCORE_SQL} AS score,
                   a.descricao, a.valor_referencia, a.status,
                   a.numero_controle_pncp AS pncp,
                   c.objeto, c.valor_global, c.data_assinatura, c.fornecedor_ni,
                   c.municipio_nome, c.municipio_ibge,
                   f.razao_social AS fornecedor, o.razao_social AS orgao
            {base} {where}
            ORDER BY score DESC, a.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

        items = []
        for r in rows:
            d = dict(r)
            items.append(
                {
                    "id": d["id"],
                    "tipo": d["tipo"],
                    "severidade": d["severidade"],
                    "score": d["score"],
                    "descricao": d["descricao"],
                    "valor_referencia": d["valor_referencia"],
                    "status": d["status"] or "aberto",
                    "contrato": {
                        "pncp": d["pncp"],
                        "objeto": d["objeto"],
                        "valor_global": d["valor_global"],
                        "data_assinatura": d["data_assinatura"],
                        "fornecedor_ni": d["fornecedor_ni"],
                        "fornecedor": d["fornecedor"],
                        "orgao": d["orgao"],
                        "municipio_nome": d["municipio_nome"],
                        "municipio_ibge": d["municipio_ibge"],
                    },
                }
            )
        return jsonify(_envelope(items, total, page, per_page))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


@bp.route("/v1/contratos")
def v1_contratos():
    """Lista contratos monitorados (paginado)."""
    db = core.get_db()
    try:
        page, per_page = _paginacao()
        ibge = core._municipio_ibge_request()
        fornecedor_ni = (request.args.get("fornecedor_ni") or "").strip() or None

        base = """
            FROM contratos c
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
        """
        conditions: list[str] = []
        params: list = []
        if ibge:
            conditions.append("c.municipio_ibge = ?")
            params.append(ibge)
        if fornecedor_ni:
            conditions.append("c.fornecedor_ni = ?")
            params.append(fornecedor_ni)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = db.execute(f"SELECT COUNT(*) {base} {where}", params).fetchone()[0]
        offset = (page - 1) * per_page
        rows = db.execute(
            f"""
            SELECT c.numero_controle_pncp AS pncp, c.objeto, c.valor_global,
                   c.data_assinatura, c.fornecedor_ni, c.municipio_nome, c.municipio_ibge,
                   f.razao_social AS fornecedor, o.razao_social AS orgao
            {base} {where}
            ORDER BY c.valor_global DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()
        items = [dict(r) for r in rows]
        return jsonify(_envelope(items, total, page, per_page))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


@bp.route("/v1/precisao")
def v1_precisao():
    """Precisão medida por detector (mesma fonte de /api/precisao)."""
    from analise.precisao import calcular_precisao

    db = core.get_db()
    try:
        return jsonify(calcular_precisao(db))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()
