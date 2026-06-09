"""
Sentinela RJ — Gerador de relatórios Markdown.

Uso:
    python -m relatorios.builder              # salva em relatorios/
    python -m relatorios.builder /outro/dir   # salva em diretório especificado
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from db.conexao import get_conn
from analisador.engine import AnomaliaResult, analisar
from analise.labels import icon_severidade, label_tipo

DIR_RELATORIOS = Path(__file__).resolve().parent

_PLACEHOLDER_NARRATIVA = (
    "> **{NARRATIVA}** — *Substituir pela análise contextual:*  ",
    "> *histórico da empresa/fornecedor, decisões judiciais relacionadas,*  ",
    "> *comparativos de mercado, contexto político/administrativo,*  ",
    "> *documentação adicional identificada nas fontes secundárias.*",
)


def _label(tipo: str) -> str:
    return label_tipo(tipo)


# ── Consultas ao banco ────────────────────────────────────────────────────────

def _sumario_db(conn) -> dict:
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*)                         AS n,
               COALESCE(SUM(valor_global), 0)   AS total,
               COUNT(DISTINCT fornecedor_ni)    AS n_forn,
               COUNT(DISTINCT orgao_cnpj)       AS n_orgaos,
               MIN(data_assinatura)             AS d_min,
               MAX(data_assinatura)             AS d_max
        FROM contratos WHERE valor_global > 0
    """)
    row = dict(c.fetchone())

    c.execute("""
        SELECT categoria_processo_nome,
               COUNT(*)                       AS n,
               COALESCE(SUM(valor_global), 0) AS total
        FROM contratos WHERE valor_global > 0
        GROUP BY categoria_processo_nome ORDER BY total DESC
    """)
    row["categorias"] = [dict(r) for r in c.fetchall()]

    c.execute("""
        SELECT finalizado_em, data_inicial, data_final, registros_municipio
        FROM coletas_log ORDER BY id DESC LIMIT 1
    """)
    ultima = c.fetchone()
    row["ultima_coleta"] = dict(ultima) if (ultima and ultima["finalizado_em"]) else None

    return row


def _carregar_narrativas(conn) -> dict[tuple[str, str | None], str]:
    rows = conn.execute(
        """
        SELECT tipo, numero_controle_pncp, narrativa_ia
        FROM alertas
        WHERE narrativa_ia IS NOT NULL AND TRIM(narrativa_ia) != ''
        """
    ).fetchall()
    return {
        (str(r["tipo"]), r["numero_controle_pncp"]): str(r["narrativa_ia"]).strip()
        for r in rows
    }


def _buscar_narrativa(
    anomalia: AnomaliaResult,
    indice: dict[tuple[str, str | None], str],
) -> str | None:
    for pncp in anomalia.contratos or [None]:
        texto = indice.get((anomalia.tipo, pncp))
        if texto:
            return texto
    return None


def _bloco_narrativa(texto: str | None) -> str:
    if not texto:
        return "\n".join(_PLACEHOLDER_NARRATIVA)
    linhas = ["> **Análise IA:**", ">"]
    for paragrafo in texto.splitlines():
        linhas.append(f"> {paragrafo}" if paragrafo else ">")
    return "\n".join(linhas)


# ── Helpers de formatação ─────────────────────────────────────────────────────

def _barra_score(score: float, largura: int = 20) -> str:
    filled = round(score * largura)
    return "█" * filled + "░" * (largura - filled) + f" {score * 100:.0f}%"


def _metricas_md(metricas: dict) -> str:
    if not metricas:
        return "*Sem métricas disponíveis.*"
    linhas = ["| Métrica | Valor |", "|---------|-------|"]
    for k, v in metricas.items():
        if isinstance(v, float):
            v_str = f"{v:,.2f}" if abs(v) >= 1 else f"{v:.4f}"
        elif isinstance(v, list):
            v_str = ", ".join(str(x) for x in v[:5]) or "—"
        else:
            v_str = str(v) if v is not None else "—"
        linhas.append(f"| `{k}` | {v_str} |")
    return "\n".join(linhas)


# ── Seções do relatório ───────────────────────────────────────────────────────

def _cabecalho(s: dict, anomalias: list[AnomaliaResult], hoje: date) -> str:
    n_alta  = sum(1 for a in anomalias if a.severidade == "alta")
    n_media = sum(1 for a in anomalias if a.severidade == "media")
    n_baixa = sum(1 for a in anomalias if a.severidade == "baixa")

    linhas = [
        "# SENTINELA RJ — Relatório de Anomalias",
        f"**Gerado em:** {hoje.strftime('%d/%m/%Y')}  ",
        "**Fonte:** Portal Nacional de Contratações Públicas (PNCP)  ",
        f"**Período da base:** {s['d_min']} → {s['d_max']}  ",
        "",
        "---",
        "",
        "## Visão Geral da Base",
        "",
        "| Indicador | Valor |",
        "|-----------|-------|",
        f"| Contratos analisados | {s['n']} |",
        f"| Valor total | R$ {s['total']:,.2f} |",
        f"| Fornecedores distintos | {s['n_forn']} |",
        f"| Órgãos distintos | {s['n_orgaos']} |",
        "",
        "**Distribuição por categoria:**",
        "",
        "| Categoria | Contratos | Valor | % |",
        "|-----------|-----------|-------|---|",
    ]

    for cat in s["categorias"]:
        nome = cat["categoria_processo_nome"] or "Não informado"
        pct  = (cat["total"] / s["total"] * 100) if s["total"] else 0
        linhas.append(
            f"| {nome} | {cat['n']} | R$ {cat['total']:,.0f} | {pct:.0f}% |"
        )

    linhas += [
        "",
        "---",
        "",
        "## Painel de Anomalias",
        "",
        f"🔴 **{n_alta}** alta prioridade  ",
        f"🟡 **{n_media}** prioridade média  ",
        f"🟢 **{n_baixa}** baixa prioridade  ",
        f"**Total:** {len(anomalias)} sinais detectados",
        "",
    ]

    return "\n".join(linhas)


def _tabela_geral(anomalias: list[AnomaliaResult]) -> str:
    linhas = [
        "| # | Score | Sev. | Tipo | Título |",
        "|---|------:|------|------|--------|",
    ]
    for i, a in enumerate(anomalias, 1):
        icon  = icon_severidade(a.severidade)
        label = _label(a.tipo)
        linhas.append(
            f"| {i} | {a.score:.3f} | {icon} | {label} | {a.titulo[:70]} |"
        )
    return "\n".join(linhas)


def _secao_anomalia(
    n: int,
    a: AnomaliaResult,
    narrativa: str | None = None,
) -> str:
    icon  = icon_severidade(a.severidade)
    label = _label(a.tipo)

    linhas = [
        f"### {n}. {a.titulo}",
        "",
        f"**Tipo:** {label}  ",
        f"**Severidade:** {icon} {a.severidade.upper()}  ",
        f"**Score:** `{_barra_score(a.score)}`  ",
        "",
        f"**Descrição:**  ",
        a.descricao,
        "",
        "**Métricas:**",
        "",
        _metricas_md(a.metricas),
        "",
    ]

    if a.contratos:
        linhas += ["**Contratos envolvidos:**", ""]
        for pncp_id in a.contratos:
            if pncp_id:
                linhas.append(f"- `{pncp_id}`")
        linhas.append("")

    linhas += [
        f"**Metodologia:** {a.metodologia}",
        "",
        _bloco_narrativa(narrativa),
        "",
        "---",
        "",
    ]

    return "\n".join(linhas)


def _rodape(anomalias: list[AnomaliaResult]) -> str:
    tipos_alta = {a.tipo for a in anomalias if a.severidade == "alta"}
    passos: list[str] = []

    if "concentracao_fornecedor" in tipos_alta:
        for a in [x for x in anomalias if x.tipo == "concentracao_fornecedor" and x.severidade == "alta"][:2]:
            qtd = a.metricas.get("qtd_contratos_janela", "?")
            passos.append(
                f"**{a.titulo[:60]}** — Verificar se os {qtd} contratos "
                f"vieram de licitações separadas ou de processo único. "
                f"Cruzar com Portal da Transparência da Prefeitura (empenhos realizados)."
            )

    if "sem_licitacao_inexigibilidade" in tipos_alta:
        passos.append(
            "**Inexigibilidades de alto valor** — Verificar justificativas publicadas "
            "no Diário Oficial do Município. Comparar com valores praticados "
            "em outros municípios para serviços equivalentes."
        )

    if "sem_licitacao_emergencia" in tipos_alta:
        passos.append(
            "**Contratos emergenciais** — Verificar se a situação emergencial foi "
            "formalmente declarada e publicada. Avaliar se o prazo de vigência é "
            "compatível com a natureza da emergência declarada."
        )

    if "outlier_valor" in tipos_alta:
        passos.append(
            "**Outliers de valor** — Cruzar com o orçamento estimado da licitação "
            "de referência. Verificar histórico do fornecedor no PNCP "
            "em outros municípios e no TCE/TCM-RJ."
        )

    passos += [
        "**Ampliar coleta** — Expandir base para 2019–2022 para construir série "
        "histórica e comparar padrões entre gestões municipais.",
        "**Cruzar fontes** — Portal da Transparência da Prefeitura do Rio "
        "(empenhos vs. contratos assinados) + TCM-RJ (julgamentos e irregularidades).",
        "**Monitoramento contínuo** — Configurar coleta semanal para detectar "
        "novos contratos nas categorias de risco já identificadas.",
    ]

    linhas = ["## Próximos Passos", ""]
    for i, p in enumerate(passos, 1):
        linhas.append(f"{i}. {p}")

    linhas += [
        "",
        "---",
        "",
        "*Relatório gerado pelo Sentinela RJ — monitoramento de contratos públicos municipais*  ",
        "*Dados: PNCP | Análise automática: Sentinela RJ v0.1*",
    ]

    return "\n".join(linhas)


# ── Ponto de entrada público ──────────────────────────────────────────────────

def gerar(conn, dir_saida: Path | None = None) -> Path:
    """
    Executa análise completa e salva relatório em relatorio_YYYY-MM-DD.md.
    Retorna o Path do arquivo gerado.
    """
    hoje = date.today()
    dir_saida = dir_saida or DIR_RELATORIOS
    dir_saida.mkdir(parents=True, exist_ok=True)

    print("Coletando estatísticas do banco...")
    sumario = _sumario_db(conn)

    print("Executando detectores de anomalias...")
    anomalias = analisar(conn)
    n_alta = sum(1 for a in anomalias if a.severidade == "alta")
    print(f"  {len(anomalias)} anomalias | {n_alta} alta prioridade")

    narrativas = _carregar_narrativas(conn)
    n_narrativas = sum(
        1 for a in anomalias if _buscar_narrativa(a, narrativas)
    )
    print(f"  {n_narrativas} anomalias com narrativa IA no banco")

    destacadas = [a for a in anomalias if a.score >= 0.70]
    print(f"Gerando relatorio ({len(destacadas)} com score >= 0.70)...")

    partes = [
        _cabecalho(sumario, anomalias, hoje),
        _tabela_geral(anomalias),
        "",
        "---",
        "",
        "## Detalhamento — Anomalias com Score ≥ 0,70",
        "",
    ]

    if destacadas:
        for i, a in enumerate(destacadas, 1):
            narrativa = _buscar_narrativa(a, narrativas)
            partes.append(_secao_anomalia(i, a, narrativa))
    else:
        partes.append("*Nenhuma anomalia com score ≥ 0,70 no período analisado.*\n")

    partes.append(_rodape(anomalias))

    conteudo = "\n".join(partes)

    nome = f"relatorio_{hoje.strftime('%Y-%m-%d')}.md"
    caminho = dir_saida / nome
    caminho.write_text(conteudo, encoding="utf-8")

    print(f"Relatório salvo: {caminho}")
    return caminho


if __name__ == "__main__":
    dir_saida = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    conn = get_conn(row_factory=True)
    caminho = gerar(conn, dir_saida)
    conn.close()
