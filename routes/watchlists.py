"""Watchlists e regras de alerta — CRUD de vigilância manual."""
from flask import Blueprint, jsonify, request

from web_auth import requer_login

import web_app as core

bp = Blueprint("watchlists", __name__)


# ---------------------------------------------------------------------------
# Watchlists — CRUD
# ---------------------------------------------------------------------------
@bp.route("/api/watchlists", methods=["GET", "POST", "OPTIONS"])
@requer_login
def watchlists_collection():
    if request.method == "OPTIONS":
        return "", 204

    from db.watchlists import WatchlistError, criar_watchlist, listar_watchlists

    db = core.get_db()
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


@bp.route("/api/watchlists/<int:watchlist_id>", methods=["GET", "PATCH", "DELETE", "OPTIONS"])
@requer_login
def watchlists_detail(watchlist_id: int):
    if request.method == "OPTIONS":
        return "", 204

    from db.watchlists import WatchlistError, atualizar_watchlist, desativar_watchlist, obter_watchlist

    db = core.get_db()
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
@bp.route("/api/regras-alerta", methods=["GET", "POST", "OPTIONS"])
@requer_login
def regras_alerta_collection():
    if request.method == "OPTIONS":
        return "", 204

    from db.regras_alerta import RegraAlertaError, criar_regra, listar_regras

    db = core.get_db()
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


@bp.route("/api/regras-alerta/<int:regra_id>", methods=["GET", "PATCH", "DELETE", "OPTIONS"])
@requer_login
def regras_alerta_detail(regra_id: int):
    if request.method == "OPTIONS":
        return "", 204

    from db.regras_alerta import RegraAlertaError, atualizar_regra, desativar_regra, obter_regra

    db = core.get_db()
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
