"""Gerador de painel de controle HTML estático — Sentinela RJ."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from db.conexao import DB_PATH, get_conn

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_SAIDA_PADRAO = _ROOT / "data" / "painel_controle.html"

_LABEL_TIPO: dict[str, str] = {
    "outlier_valor": "Outlier de valor",
    "concentracao_fornecedor": "Concentração de fornecedor",
    "sem_licitacao_inexigibilidade": "Inexigibilidade",
    "sem_licitacao_emergencia": "Emergência",
    "sem_licitacao_dispensa": "Dispensa",
    "fracionamento_ap": "Fracionamento",
}


def _label_tipo(tipo: str) -> str:
    return _LABEL_TIPO.get(tipo, tipo.replace("_", " ").title())


def _consultar_brutos_extraidos(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "SELECT COALESCE(SUM(registros_brutos), 0) AS total FROM coletas_log"
    )
    return int(cur.fetchone()[0])


def _consultar_contratos_analisados(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "SELECT COUNT(*) FROM contratos WHERE valor_global > 0"
    )
    return int(cur.fetchone()[0])


def _consultar_anomalias_por_tipo(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT tipo, COUNT(*) AS quantidade
        FROM alertas
        GROUP BY tipo
        ORDER BY quantidade DESC
        """
    )
    return [
        {"tipo": row[0], "label": _label_tipo(row[0]), "quantidade": int(row[1])}
        for row in cur.fetchall()
    ]


def _consultar_total_anomalias(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM alertas")
    return int(cur.fetchone()[0])


def _consultar_top_anomalias_alta(
    conn: sqlite3.Connection,
    limite: int = 10,
) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT a.tipo,
               a.descricao,
               COALESCE(a.valor_referencia, 0) AS valor_referencia,
               a.numero_controle_pncp,
               COALESCE(c.objeto, '') AS objeto,
               COALESCE(f.razao_social, '') AS fornecedor
        FROM alertas a
        LEFT JOIN contratos c
               ON c.numero_controle_pncp = a.numero_controle_pncp
        LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        WHERE a.severidade = 'alta'
        ORDER BY a.valor_referencia DESC, a.id DESC
        LIMIT ?
        """,
        (limite,),
    )
    return [
        {
            "tipo": row[0],
            "label": _label_tipo(row[0]),
            "descricao": row[1],
            "valor_referencia": float(row[2]),
            "numero_controle_pncp": row[3] or "—",
            "objeto": row[4],
            "fornecedor": row[5],
        }
        for row in cur.fetchall()
    ]


def _coletar_metricas(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "gerado_em": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
        "brutos_extraidos": _consultar_brutos_extraidos(conn),
        "contratos_analisados": _consultar_contratos_analisados(conn),
        "total_anomalias": _consultar_total_anomalias(conn),
        "anomalias_por_tipo": _consultar_anomalias_por_tipo(conn),
        "top_alta": _consultar_top_anomalias_alta(conn),
    }


def _formatar_moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _linhas_tabela_top(top: list[dict[str, Any]]) -> str:
    if not top:
        return (
            '<tr><td colspan="5" class="vazio">'
            "Nenhuma anomalia de risco ALTO registrada.</td></tr>"
        )
    linhas: list[str] = []
    for i, item in enumerate(top, 1):
        valor = _formatar_moeda(item["valor_referencia"])
        desc = str(item["descricao"])[:120]
        linhas.append(
            f"<tr><td>{i}</td><td><span class='tag'>{item['label']}</span></td>"
            f"<td>{valor}</td><td>{item['fornecedor'] or '—'}</td>"
            f"<td>{desc}</td></tr>"
        )
    return "\n".join(linhas)


def _montar_cards(metricas: dict[str, Any]) -> str:
    cards = [
        ("Contratos brutos", metricas["brutos_extraidos"], "Extraídos pelo módulo Extrator"),
        ("Contratos analisados", metricas["contratos_analisados"], "Persistidos no banco"),
        ("Anomalias detectadas", metricas["total_anomalias"], "Identificadas pelo Analisador"),
        ("Tipos distintos", len(metricas["anomalias_por_tipo"]), "Categorias de alerta"),
    ]
    return "\n".join(
        f'<article class="card"><p class="card-label">{titulo}</p>'
        f'<p class="card-value">{valor:,}</p><p class="card-hint">{hint}</p></article>'
        for titulo, valor, hint in cards
    )


def _template_html(metricas: dict[str, Any]) -> str:
    dados_json = json.dumps(metricas, ensure_ascii=False)
    linhas_top = _linhas_tabela_top(metricas["top_alta"])
    cards = _montar_cards(metricas)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sentinela RJ — Painel de Controle</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:Inter,system-ui,sans-serif;background:#0a0a0a;color:#fafafa;
      line-height:1.5;padding:2rem}}
    header{{margin-bottom:2rem}}
    h1{{font-weight:300;font-size:1.75rem;letter-spacing:-0.02em}}
    .meta{{color:#a3a3a3;font-size:.875rem;margin-top:.25rem}}
    .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem;
      margin-bottom:2rem}}
    .card{{background:#171717;border:1px solid #262626;border-radius:8px;padding:1.25rem}}
    .card-label{{color:#a3a3a3;font-size:.75rem;text-transform:uppercase;letter-spacing:.05em}}
    .card-value{{font-size:2rem;font-weight:300;margin:.5rem 0}}
    .card-hint{{color:#737373;font-size:.75rem}}
    .charts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem;
      margin-bottom:2rem}}
    .chart-box{{background:#171717;border:1px solid #262626;border-radius:8px;padding:1rem}}
    .chart-box h2{{font-size:.875rem;font-weight:400;color:#a3a3a3;margin-bottom:1rem}}
    table{{width:100%;border-collapse:collapse;background:#171717;border:1px solid #262626;
      border-radius:8px;overflow:hidden}}
    th,td{{padding:.75rem 1rem;text-align:left;border-bottom:1px solid #262626;font-size:.875rem}}
    th{{color:#a3a3a3;font-weight:500;font-size:.75rem;text-transform:uppercase}}
    tr:last-child td{{border-bottom:none}}
    .tag{{background:#262626;padding:.15rem .5rem;border-radius:4px;font-size:.75rem}}
    .vazio{{text-align:center;color:#737373}}
    section h2{{font-size:1rem;font-weight:400;margin-bottom:1rem;color:#d4d4d4}}
  </style>
</head>
<body>
  <header>
    <h1>Sentinela RJ — Painel de Controle</h1>
    <p class="meta">Gerado em {metricas["gerado_em"]}</p>
  </header>
  <section class="cards">{cards}</section>
  <section class="charts">
    <div class="chart-box"><h2>Anomalias por tipo</h2><canvas id="chartTipo"></canvas></div>
    <div class="chart-box"><h2>Distribuição por tipo</h2><canvas id="chartDonut"></canvas></div>
  </section>
  <section>
    <h2>Top 10 anomalias — risco ALTO</h2>
    <table>
      <thead><tr><th>#</th><th>Tipo</th><th>Valor</th><th>Fornecedor</th><th>Descrição</th></tr></thead>
      <tbody>{linhas_top}</tbody>
    </table>
  </section>
  <script>
    const dados = {dados_json};
    const tipos = dados.anomalias_por_tipo.map((i) => i.label);
    const qtds = dados.anomalias_por_tipo.map((i) => i.quantidade);
    const cor = '#3b82f6';
    new Chart(document.getElementById('chartTipo'), {{
      type: 'bar',
      data: {{ labels: tipos, datasets: [{{ data: qtds, backgroundColor: cor }}] }},
      options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{
        x: {{ ticks: {{ color: '#a3a3a3' }}, grid: {{ color: '#262626' }} }},
        y: {{ ticks: {{ color: '#a3a3a3' }}, grid: {{ color: '#262626' }} }}
      }} }}
    }});
    new Chart(document.getElementById('chartDonut'), {{
      type: 'doughnut',
      data: {{ labels: tipos, datasets: [{{ data: qtds,
        backgroundColor: ['#3b82f6','#8b5cf6','#ec4899','#f59e0b','#10b981','#6366f1'] }}] }},
      options: {{ plugins: {{ legend: {{ labels: {{ color: '#a3a3a3' }} }} }} }}
    }});
  </script>
</body>
</html>"""


class GeradorPainelHTML:
    """Gera painel HTML estático a partir das estatísticas do banco SQLite."""

    def __init__(self, caminho_saida: Path | None = None) -> None:
        self._caminho_saida = caminho_saida or _SAIDA_PADRAO

    def _validar_banco(self) -> None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Banco não encontrado: {DB_PATH}")

    def gerar(self) -> Path:
        self._validar_banco()
        conn = get_conn()
        try:
            metricas = _coletar_metricas(conn)
        finally:
            conn.close()

        html = _template_html(metricas)
        self._caminho_saida.parent.mkdir(parents=True, exist_ok=True)
        self._caminho_saida.write_text(html, encoding="utf-8")
        logger.info("Painel HTML salvo em: %s", self._caminho_saida.resolve())
        return self._caminho_saida.resolve()
