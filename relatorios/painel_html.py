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

_COR_TIPO: dict[str, str] = {
    "outlier_valor": "#ef4444",
    "concentracao_fornecedor": "#f97316",
    "sem_licitacao_inexigibilidade": "#a855f7",
    "sem_licitacao_emergencia": "#eab308",
    "sem_licitacao_dispensa": "#3b82f6",
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
        SELECT
            a.tipo,
            MAX(a.valor_referencia) AS valor_referencia,
            COUNT(*) AS ocorrencias,
            f.razao_social AS fornecedor,
            MAX(a.descricao) AS descricao,
            MAX(a.narrativa_ia) AS narrativa_ia
        FROM alertas a
        LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
        LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        WHERE a.severidade = 'alta'
        GROUP BY f.razao_social, a.tipo
        ORDER BY valor_referencia DESC
        LIMIT ?
        """,
        (limite,),
    )
    return [
        {
            "tipo": row[0],
            "label": _label_tipo(row[0]),
            "valor_referencia": float(row[1]),
            "ocorrencias": int(row[2]),
            "fornecedor": row[3],
            "descricao": row[4],
            "narrativa_ia": row[5],
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


def _resumo_cidadao(item: dict) -> str:
    """Generates citizen-friendly summary from alert data."""
    tipo = item["tipo"]
    valor = item["valor_referencia"]
    fornecedor = item["fornecedor"] or "Fornecedor não identificado"
    ocorrencias = item.get("ocorrencias", 1)

    valor_fmt = f"R$ {valor/1_000_000:.1f} mi" if valor >= 1_000_000 else f"R$ {valor:,.0f}"

    if tipo == "concentracao_fornecedor":
        return f"{fornecedor} recebeu {valor_fmt} em {ocorrencias} contratos em 90 dias"
    elif tipo == "outlier_valor":
        return f"Contrato de {valor_fmt} — valor muito acima do esperado para a categoria"
    elif tipo == "sem_licitacao_inexigibilidade":
        return f"Contrato de {valor_fmt} sem licitação (inexigibilidade)"
    elif tipo == "sem_licitacao_emergencia":
        return f"Contrato emergencial de {valor_fmt} sem licitação"
    elif tipo == "sem_licitacao_dispensa":
        return f"Contrato de {valor_fmt} com dispensa de licitação"
    else:
        return f"Anomalia de {valor_fmt} detectada"


def _linhas_tabela_top(top: list[dict[str, Any]]) -> str:
    if not top:
        return (
            '<tr><td colspan="6" class="vazio">'
            "Nenhuma anomalia de risco ALTO registrada.</td></tr>"
        )
    linhas: list[str] = []
    for i, item in enumerate(top, 1):
        valor = _formatar_moeda(item["valor_referencia"])
        cor = _COR_TIPO.get(item["tipo"], "#6b7280")
        badge = (
            f'<span class="badge" style="background:{cor}20;color:{cor};'
            f'border:1px solid {cor}40">{item["label"]}</span>'
        )
        resumo = _resumo_cidadao(item)
        desc_tecnica = str(item["descricao"] or "")[:160]
        fornecedor = item["fornecedor"] or "—"

        narrativa = item.get("narrativa_ia")
        if narrativa:
            narr_id = f"narr-{i}"
            onclick = f"toggleNarr('{narr_id}')"
            narrativa_col = (
                f'<button class="btn-narr" onclick="{onclick}">Ver análise</button>'
                f'<div id="{narr_id}" class="narr-text" style="display:none">{narrativa}</div>'
            )
        else:
            narrativa_col = "—"

        linhas.append(
            f"<tr>"
            f"<td class='num'>{i}</td>"
            f"<td>{badge}</td>"
            f"<td class='valor'>{valor}</td>"
            f"<td>{fornecedor}</td>"
            f"<td><strong>{resumo}</strong>"
            f"<small class='desc-tec'>{desc_tecnica}</small></td>"
            f"<td>{narrativa_col}</td>"
            f"</tr>"
        )
    return "\n".join(linhas)


def _montar_cards(metricas: dict[str, Any]) -> str:
    cards = [
        ("Contratos brutos", metricas["brutos_extraidos"], "Extraídos pelo módulo Extrator", False),
        ("Contratos analisados", metricas["contratos_analisados"], "Persistidos no banco", False),
        ("Anomalias detectadas", metricas["total_anomalias"], "Identificadas pelo Analisador", True),
        ("Tipos distintos", len(metricas["anomalias_por_tipo"]), "Categorias de alerta", False),
    ]
    html_cards = []
    for titulo, valor, hint, destaque in cards:
        borda = "border-left:4px solid #ef4444" if destaque else "border-left:4px solid #262626"
        html_cards.append(
            f'<article class="card" style="{borda}">'
            f'<p class="card-value">{valor:,}</p>'
            f'<p class="card-label">{titulo}</p>'
            f'<p class="card-hint">{hint}</p>'
            f"</article>"
        )
    return "\n".join(html_cards)


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
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    *, *::before, *::after {{box-sizing:border-box;margin:0;padding:0}}
    body {{
      font-family:'Inter',system-ui,sans-serif;
      background:#0f0f0f;
      color:#fafafa;
      line-height:1.6;
    }}
    .container {{
      max-width:1200px;
      margin:0 auto;
      padding:2.5rem 1.5rem;
    }}
    header {{
      margin-bottom:3rem;
      border-bottom:1px solid #1f1f1f;
      padding-bottom:2rem;
    }}
    header h1 {{
      font-size:2.5rem;
      font-weight:700;
      letter-spacing:-0.03em;
      line-height:1.1;
    }}
    .subtitle {{
      color:#a3a3a3;
      font-size:1rem;
      margin-top:0.4rem;
    }}
    .meta {{
      color:#525252;
      font-size:0.8rem;
      margin-top:0.75rem;
    }}
    .cards {{
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
      gap:1rem;
      margin-bottom:2.5rem;
    }}
    .card {{
      background:#171717;
      border:1px solid #262626;
      border-radius:10px;
      padding:1.5rem;
    }}
    .card-value {{
      font-size:3rem;
      font-weight:700;
      line-height:1;
      letter-spacing:-0.04em;
      margin-bottom:0.5rem;
    }}
    .card-label {{
      font-size:0.7rem;
      font-weight:600;
      text-transform:uppercase;
      letter-spacing:0.1em;
      color:#737373;
    }}
    .card-hint {{
      color:#525252;
      font-size:0.75rem;
      margin-top:0.25rem;
    }}
    .charts {{
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
      gap:1rem;
      margin-bottom:2.5rem;
    }}
    .chart-box {{
      background:#171717;
      border:1px solid #262626;
      border-radius:10px;
      padding:1.5rem;
    }}
    .chart-box h2 {{
      font-size:0.75rem;
      font-weight:600;
      color:#737373;
      text-transform:uppercase;
      letter-spacing:0.08em;
      margin-bottom:1.25rem;
    }}
    .table-section h2 {{
      font-size:0.75rem;
      font-weight:600;
      color:#737373;
      text-transform:uppercase;
      letter-spacing:0.08em;
      margin-bottom:1rem;
    }}
    .table-wrap {{
      overflow-x:auto;
      border-radius:10px;
      border:1px solid #262626;
    }}
    table {{
      width:100%;
      border-collapse:collapse;
      background:#171717;
      font-size:0.875rem;
    }}
    th {{
      padding:0.75rem 1rem;
      text-align:left;
      border-bottom:1px solid #262626;
      font-size:0.7rem;
      font-weight:600;
      color:#737373;
      text-transform:uppercase;
      letter-spacing:0.07em;
      white-space:nowrap;
    }}
    td {{
      padding:0.875rem 1rem;
      text-align:left;
      border-bottom:1px solid #1a1a1a;
      vertical-align:top;
    }}
    tr:last-child td {{border-bottom:none}}
    tr:hover td {{background:#1c1c1c}}
    .num {{color:#525252;font-size:0.8rem;width:2rem}}
    .valor {{white-space:nowrap;font-variant-numeric:tabular-nums;font-weight:500}}
    .badge {{
      display:inline-block;
      padding:0.2rem 0.6rem;
      border-radius:6px;
      font-size:0.7rem;
      font-weight:600;
      white-space:nowrap;
    }}
    .desc-tec {{
      color:#737373;
      font-size:0.78rem;
      display:block;
      margin-top:0.3rem;
    }}
    .btn-narr {{
      background:#262626;
      border:1px solid #404040;
      color:#a3a3a3;
      padding:0.25rem 0.65rem;
      border-radius:6px;
      font-size:0.75rem;
      cursor:pointer;
      white-space:nowrap;
      transition:background 0.15s,color 0.15s;
    }}
    .btn-narr:hover {{background:#333;color:#fafafa}}
    .narr-text {{
      margin-top:0.5rem;
      padding:0.75rem;
      background:#1a1a1a;
      border-radius:6px;
      font-size:0.8rem;
      color:#d4d4d4;
      line-height:1.6;
      max-width:320px;
    }}
    .vazio {{text-align:center;color:#525252;padding:2rem}}
    footer {{
      margin-top:3rem;
      padding-top:1.5rem;
      border-top:1px solid #1f1f1f;
      color:#525252;
      font-size:0.8rem;
      text-align:center;
    }}
    @media (max-width:640px) {{
      .cards {{grid-template-columns:1fr 1fr}}
      .card-value {{font-size:2rem}}
      header h1 {{font-size:1.75rem}}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Sentinela RJ</h1>
      <p class="subtitle">Monitoramento independente de contratos públicos municipais</p>
      <p class="meta">Gerado em {metricas["gerado_em"]}</p>
    </header>

    <section class="cards">{cards}</section>

    <section class="charts">
      <div class="chart-box"><h2>Anomalias por tipo</h2><canvas id="chartTipo"></canvas></div>
      <div class="chart-box"><h2>Distribuição por tipo</h2><canvas id="chartDonut"></canvas></div>
    </section>

    <section class="table-section">
      <h2>Top 10 anomalias — risco alto</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>Tipo</th><th>Valor</th><th>Fornecedor</th>
              <th>Descrição</th><th>Narrativa IA</th>
            </tr>
          </thead>
          <tbody>{linhas_top}</tbody>
        </table>
      </div>
    </section>

    <footer>
      <p>Dados: Portal Nacional de Contratações Públicas (PNCP) · Análise: Sentinela RJ</p>
    </footer>
  </div>

  <script>
    const dados = {dados_json};
    const tipos = dados.anomalias_por_tipo.map(i => i.label);
    const qtds  = dados.anomalias_por_tipo.map(i => i.quantidade);

    function toggleNarr(id) {{
      const el = document.getElementById(id);
      if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
    }}

    new Chart(document.getElementById('chartTipo'), {{
      type: 'bar',
      data: {{
        labels: tipos,
        datasets: [{{ data: qtds, backgroundColor: '#ef4444', borderRadius: 4 }}]
      }},
      options: {{
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          x: {{ ticks: {{ color: '#737373', font: {{ size: 11 }} }}, grid: {{ color: '#1f1f1f' }} }},
          y: {{ ticks: {{ color: '#737373', font: {{ size: 11 }} }}, grid: {{ color: '#1f1f1f' }} }}
        }}
      }}
    }});

    new Chart(document.getElementById('chartDonut'), {{
      type: 'doughnut',
      data: {{
        labels: tipos,
        datasets: [{{
          data: qtds,
          backgroundColor: ['#ef4444','#f97316','#a855f7','#eab308','#3b82f6','#6366f1'],
          borderWidth: 0
        }}]
      }},
      options: {{
        plugins: {{
          legend: {{ labels: {{ color: '#a3a3a3', font: {{ size: 11 }} }} }}
        }}
      }}
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
