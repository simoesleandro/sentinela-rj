"""Páginas institucionais — transparência de dados (LGPD) e precisão medida.

- /dados        : base legal do tratamento, fontes, retenção, contestação (roadmap 6.1)
- /precisao     : taxa de acerto por detector, calculada da triagem real (roadmap 1.1)
- /backtesting  : "o Sentinela teria detectado?" contra casos conhecidos (roadmap 1.2)
- /benchmark    : comparativo entre municípios vs mediana regional (roadmap 4.2)
"""
from flask import Blueprint, jsonify, render_template

import web_app as core

bp = Blueprint("institucional", __name__)


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


@bp.route("/benchmark")
def benchmark_page():
    return render_template("benchmark.html")


@bp.route("/api/benchmark")
def api_benchmark():
    """Comparativo entre municípios vs mediana regional (roadmap 4.2)."""
    from analise.benchmark import calcular_benchmark

    db = core.get_db()
    try:
        return jsonify(calcular_benchmark(db))
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
    from analise.precisao import calcular_precisao

    db = core.get_db()
    try:
        return jsonify(calcular_precisao(db))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()
