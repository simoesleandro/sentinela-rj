"""Páginas institucionais — transparência de dados (LGPD) e precisão medida.

- /dados        : base legal do tratamento, fontes, retenção, contestação (roadmap 6.1)
- /precisao     : taxa de acerto por detector, calculada da triagem real (roadmap 1.1)
- /backtesting  : "o Sentinela teria detectado?" contra casos conhecidos (roadmap 1.2)
"""
from flask import Blueprint, jsonify, render_template

import web_app as core

bp = Blueprint("institucional", __name__)

# Mínimo de alertas rotulados (confirmado + descartado) para exibir uma taxa —
# abaixo disso o número não é confiável e mostramos "amostra insuficiente".
_MIN_AMOSTRA_PRECISAO = 10


@bp.route("/dados")
def dados_page():
    return render_template("dados.html")


@bp.route("/precisao")
def precisao_page():
    return render_template("precisao.html")


@bp.route("/backtesting")
def backtesting_page():
    return render_template("backtesting.html")


@bp.route("/api/backtesting")
def api_backtesting():
    """"O Sentinela teria detectado?" — detectores × casos conhecidos (roadmap 1.2)."""
    from analise.backtesting import executar_backtest

    db = core.get_db()
    try:
        return jsonify(executar_backtest(db))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


@bp.route("/api/precisao")
def api_precisao():
    """Precisão por detector = confirmados / (confirmados + descartados).

    Lê a triagem real (coluna alertas.status). Só reporta a taxa quando há
    amostra rotulada suficiente; senão devolve status='amostra_insuficiente'.
    """
    db = core.get_db()
    try:
        rows = db.execute(
            """
            SELECT tipo,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status = 'confirmado' THEN 1 ELSE 0 END) AS confirmados,
                   SUM(CASE WHEN status = 'descartado' THEN 1 ELSE 0 END) AS descartados,
                   SUM(CASE WHEN COALESCE(status, 'aberto') IN ('aberto', 'investigando')
                            THEN 1 ELSE 0 END) AS pendentes
            FROM alertas
            GROUP BY tipo
            ORDER BY total DESC
            """
        ).fetchall()

        itens = []
        rotulados_total = 0
        for r in rows:
            d = dict(r)
            rotulados = (d["confirmados"] or 0) + (d["descartados"] or 0)
            rotulados_total += rotulados
            if rotulados >= _MIN_AMOSTRA_PRECISAO:
                d["precisao"] = round(d["confirmados"] / rotulados, 3)
                d["amostra_status"] = "medida"
            else:
                d["precisao"] = None
                d["amostra_status"] = "amostra_insuficiente"
            d["rotulados"] = rotulados
            itens.append(d)

        return jsonify({
            "itens": itens,
            "min_amostra": _MIN_AMOSTRA_PRECISAO,
            "rotulados_total": rotulados_total,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()
