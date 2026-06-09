"""Sentinela RJ — Painel Web Interativo."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

_ROOT = Path(__file__).resolve().parent
_DB_PATH = _ROOT / "data" / "sentinela_rj.db"
_MENU = ("Visão Geral", "Investigação", "Logs")
_PALETA = ["#4f46e5", "#06b6d4", "#334155"]

_LABEL_TIPO: dict[str, str] = {
    "outlier_valor": "Valor Muito Acima do Padrão",
    "concentracao_fornecedor": "Monopólio de Fornecedor",
    "sem_licitacao_inexigibilidade": "Dispensa por Inexigibilidade",
    "sem_licitacao_emergencia": "Contratação de Emergência",
    "sem_licitacao_dispensa": "Dispensa de Licitação",
    "fracionamento_ap": "Fracionamento de Despesa",
}

_LABEL_RISCO: dict[str, str] = {
    "alta": "Crítico",
    "media": "Elevado",
    "baixa": "Moderado",
}

_SQL_ANOMALIAS = """
SELECT a.id,
       a.tipo,
       a.severidade,
       a.descricao,
       a.valor_referencia,
       a.status,
       a.narrativa_ia,
       a.numero_controle_pncp,
       a.metodologia,
       COALESCE(o.razao_social, c.unidade_nome, 'Não informado') AS orgao,
       COALESCE(f.razao_social, 'Não informado') AS fornecedor,
       COALESCE(c.objeto, '') AS objeto,
       COALESCE(c.valor_global, 0) AS valor_global
FROM alertas a
LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
ORDER BY a.valor_referencia DESC, a.id DESC
"""

_SQL_FUNIL = """
SELECT
    (SELECT COALESCE(SUM(registros_brutos), 0) FROM coletas_log) AS extraidos,
    (SELECT COUNT(*) FROM contratos WHERE valor_global > 0) AS analisados,
    (SELECT COUNT(*) FROM alertas
     WHERE narrativa_ia IS NOT NULL AND TRIM(narrativa_ia) != '') AS laudos_ia
"""


def _carregar_env() -> None:
    env_path = _ROOT / ".env"
    try:
        with env_path.open(encoding="utf-8") as handle:
            for linha in handle:
                linha = linha.strip()
                if not linha or linha.startswith("#"):
                    continue
                chave, sep, valor = linha.partition("=")
                if sep and chave.strip():
                    os.environ[chave.strip()] = valor.strip()
    except FileNotFoundError:
        pass


def _injetar_tema() -> None:
    st.markdown(
        """
        <style>
        .stApp, [data-testid="stHeader"] {
            background-color: #0b0e14 !important;
            color: #e2e8f0 !important;
        }
        .block-container { padding-top: 2rem !important; max-width: 1280px; }
        h1, h2, h3, h4, p, label, span, [data-testid="stMarkdownContainer"] {
            color: #e2e8f0 !important;
        }
        [data-testid="stSidebar"] {
            background-color: #12161f !important;
            border-right: none !important;
        }
        [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
        [data-testid="stSidebar"] .stButton > button {
            background-color: transparent !important;
            border: none !important;
            color: #e2e8f0 !important;
            text-align: left !important;
            box-shadow: none !important;
            width: 100% !important;
            padding: 0.6rem 0.75rem !important;
            border-radius: 6px !important;
            font-weight: 500 !important;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background-color: #27272a !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background-color: #27272a !important;
            border: none !important;
        }
        [data-testid="metric-container"] {
            background-color: #18181b !important;
            border: 1px solid #27272a !important;
            border-radius: 8px !important;
            padding: 1rem !important;
        }
        [data-testid="stMetricLabel"] {
            text-transform: uppercase !important;
            font-size: 0.8rem !important;
            color: #a1a1aa !important;
        }
        [data-testid="stMetricValue"] {
            font-family: Consolas, "Courier New", monospace !important;
            font-size: 2rem !important;
            font-weight: 700 !important;
            white-space: nowrap !important;
            color: #e2e8f0 !important;
        }
        .stButton > button[kind="primary"] {
            background: #4f46e5 !important;
            color: #fafafa !important;
            border: 1px solid #4f46e5 !important;
            border-radius: 6px !important;
        }
        [data-testid="stDataFrame"] {
            background-color: #18181b !important;
            border: 1px solid #27272a !important;
            border-radius: 8px !important;
        }
        [data-testid="stDataFrame"] div,
        [data-testid="stDataFrame"] table,
        [data-testid="stDataFrame"] th,
        [data-testid="stDataFrame"] td {
            background-color: #18181b !important;
            color: #e2e8f0 !important;
            border-color: #27272a !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #18181b !important;
            border-color: #27272a !important;
            border-radius: 8px !important;
        }
        #MainMenu, footer { visibility: hidden; height: 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _conectar() -> sqlite3.Connection | None:
    if not _DB_PATH.is_file():
        return None
    return sqlite3.connect(_DB_PATH)


@st.cache_data(show_spinner=False)
def _carregar_anomalias() -> pd.DataFrame:
    conn = _conectar()
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query(_SQL_ANOMALIAS, conn)
    finally:
        conn.close()
    if df.empty:
        return df
    df["tipo_suspeita"] = df["tipo"].map(
        lambda t: _LABEL_TIPO.get(str(t), str(t).replace("_", " ").title())
    )
    df["indice_suspeita"] = df["severidade"].map(
        lambda s: _LABEL_RISCO.get(str(s), str(s).title())
    )
    df["valor_referencia"] = pd.to_numeric(df["valor_referencia"], errors="coerce").fillna(0)
    df["valor_global"] = pd.to_numeric(df["valor_global"], errors="coerce").fillna(0)
    return df


@st.cache_data(show_spinner=False)
def _carregar_funil() -> dict[str, int]:
    conn = _conectar()
    if conn is None:
        return {"extraidos": 0, "analisados": 0, "laudos_ia": 0}
    try:
        row = pd.read_sql_query(_SQL_FUNIL, conn).iloc[0]
        return {
            "extraidos": int(row["extraidos"]),
            "analisados": int(row["analisados"]),
            "laudos_ia": int(row["laudos_ia"]),
        }
    finally:
        conn.close()


def _limpar_cache() -> None:
    _carregar_anomalias.clear()
    _carregar_funil.clear()


def _formatar_moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _tem_narrativa(valor: Any) -> bool:
    return bool(str(valor or "").strip())


def _linha_para_dict(linha: pd.Series) -> dict[str, Any]:
    return {chave: (None if pd.isna(valor) else valor) for chave, valor in linha.items()}


def _layout_plotly(fig: Any) -> Any:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e2e8f0",
        showlegend=False,
        margin=dict(l=10, r=10, t=30, b=10),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig


def _executar_investigacao_ia(id_anomalia: int, linha: pd.Series) -> None:
    from analise.motor_ia import InvestigadorIA
    from db.database import GerenciadorBanco

    with st.spinner("Consultando Gemini e redigindo veredito..."):
        try:
            narrativa = InvestigadorIA().investigar_anomalia(_linha_para_dict(linha))
            GerenciadorBanco(db_path=_DB_PATH).atualizar_narrativa_anomalia(
                id_anomalia, narrativa
            )
            _limpar_cache()
            st.rerun()
        except Exception as exc:
            st.error(f"Falha na investigação IA: {exc}")


def _aplicar_filtros(df: pd.DataFrame, orgao: str, indice: str) -> pd.DataFrame:
    filtrado = df.copy()
    if orgao != "Todos":
        filtrado = filtrado[filtrado["orgao"] == orgao]
    if indice != "Todos":
        filtrado = filtrado[filtrado["indice_suspeita"] == indice]
    return filtrado


def _render_sidebar(df: pd.DataFrame) -> tuple[str, str, str]:
    st.sidebar.markdown("## ◈ SENTINELA RJ")
    st.sidebar.caption("Threat Intelligence Console")
    st.sidebar.divider()
    if "pagina" not in st.session_state:
        st.session_state.pagina = "Visão Geral"
    st.sidebar.markdown("**Navegação**")
    with st.sidebar.container():
        for item in _MENU:
            ativo = st.session_state.pagina == item
            if st.button(
                item,
                key=f"nav_{item}",
                type="primary" if ativo else "secondary",
                use_container_width=True,
            ):
                st.session_state.pagina = item
                st.rerun()
    st.sidebar.divider()
    st.sidebar.subheader("Filtros Táticos")
    if df.empty:
        st.sidebar.info("Sem anomalias para filtrar.")
        return st.session_state.pagina, "Todos", "Todos"
    orgaos = ["Todos"] + sorted(df["orgao"].dropna().unique().tolist())
    indices = ["Todos"] + sorted(df["indice_suspeita"].dropna().unique().tolist())
    orgao = st.sidebar.selectbox("Órgão", orgaos)
    indice = st.sidebar.selectbox("Índice de Suspeita", indices)
    return st.session_state.pagina, orgao, indice


def _contar_laudos(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    return int(df["narrativa_ia"].apply(_tem_narrativa).sum())


def _render_metricas_topo(df: pd.DataFrame, funil: dict[str, int]) -> None:
    total = len(df)
    laudos = _contar_laudos(df)
    criticos = int((df["severidade"] == "alta").sum()) if not df.empty else 0
    pendentes = total - laudos
    volume = float(df["valor_referencia"].sum()) if not df.empty else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alertas Ativos", f"{total:,}", delta=f"{criticos} críticos", delta_color="inverse")
    c2.metric("Laudos IA", f"{laudos:,}", delta=f"{pendentes} pendentes" if pendentes else "OK")
    c3.metric("Volume em Risco", _formatar_moeda(volume))
    c4.metric("Base Analisada", f"{funil['analisados']:,}", delta=f"{funil['extraidos']:,} extraídos")


def _preparar_tabela(df: pd.DataFrame) -> pd.DataFrame:
    exibir = df[
        [
            "id",
            "tipo_suspeita",
            "indice_suspeita",
            "orgao",
            "fornecedor",
            "valor_referencia",
            "valor_global",
            "status",
        ]
    ].copy()
    exibir["valor_referencia"] = exibir["valor_referencia"].map(_formatar_moeda)
    exibir["valor_global"] = exibir["valor_global"].map(_formatar_moeda)
    return exibir.rename(
        columns={
            "tipo_suspeita": "Tipo de Suspeita",
            "indice_suspeita": "Índice de Suspeita",
            "valor_referencia": "Valor em Análise",
            "valor_global": "Valor do Contrato",
        }
    )


def _grafico_pizza(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Sem dados para o gráfico de tipos de suspeita.")
        return
    agg = df.groupby("tipo_suspeita", as_index=False).size().rename(columns={"size": "qtd"})
    fig = px.pie(
        agg,
        names="tipo_suspeita",
        values="qtd",
        hole=0.45,
        color_discrete_sequence=_PALETA,
    )
    st.plotly_chart(_layout_plotly(fig), width="stretch")


def _grafico_barras(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Sem dados para o gráfico de volume financeiro.")
        return
    agg = (
        df.groupby("tipo_suspeita", as_index=False)["valor_referencia"]
        .sum()
        .rename(columns={"valor_referencia": "volume"})
    )
    fig = px.bar(
        agg,
        x="tipo_suspeita",
        y="volume",
        color="tipo_suspeita",
        color_discrete_sequence=_PALETA,
    )
    fig.update_layout(coloraxis_showscale=False)
    st.plotly_chart(_layout_plotly(fig), width="stretch")


def _render_card_anomalia(linha: pd.Series) -> None:
    id_anomalia = int(linha["id"])
    with st.container(border=True):
        topo1, topo2 = st.columns([2, 1])
        topo1.markdown(f"### ◈ ALERTA #{id_anomalia}")
        topo2.markdown(f"**Índice:** `{linha['indice_suspeita']}`")
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"**Órgão**\n\n{linha['orgao']}")
        c2.markdown(f"**Valor**\n\n`{_formatar_moeda(float(linha['valor_referencia']))}`")
        c3.markdown(f"**Fornecedor**\n\n{linha['fornecedor']}")
        c4.markdown(f"**Tipo**\n\n{linha['tipo_suspeita']}")
        st.caption(str(linha["descricao"])[:200])
        if _tem_narrativa(linha["narrativa_ia"]):
            st.markdown("**▸ Veredito IA**")
            st.info(str(linha["narrativa_ia"]))
        elif st.button("🧠 Investigar com IA", key=f"btn_{id_anomalia}", type="primary"):
            _executar_investigacao_ia(id_anomalia, linha)


def _pagina_visao_geral(df: pd.DataFrame) -> None:
    st.markdown("### ◈ Panorama de Ameaças")
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Distribuição por Tipo**")
        _grafico_pizza(df)
    with g2:
        st.markdown("**Volume Financeiro Anômalo**")
        _grafico_barras(df)


def _pagina_investigacao(df: pd.DataFrame) -> None:
    st.markdown("### ◈ Matriz de Evidências")
    if df.empty:
        st.warning("Nenhuma anomalia encontrada com os filtros aplicados.")
        return
    st.dataframe(_preparar_tabela(df), width="stretch", hide_index=True)
    st.divider()
    st.markdown("### ◈ Dossiês Individuais")
    for _, linha in df.iterrows():
        _render_card_anomalia(linha)


def _pagina_logs(funil: dict[str, int]) -> None:
    st.markdown("### ◈ Percurso da Operação")
    st.caption("Pipeline de inteligência — extração → análise → laudo IA")
    extraidos, analisados, laudos = funil["extraidos"], funil["analisados"], funil["laudos_ia"]
    taxa_analise = (analisados / extraidos * 100) if extraidos else 0
    taxa_laudo = (laudos / analisados * 100) if analisados else 0
    st.success(
        f"**[01] Extração do Portal**\n\n"
        f"`{extraidos:,}` contratos brutos coletados do PNCP."
    )
    st.info(
        f"**[02] Análise Estatística**\n\n"
        f"`{analisados:,}` contratos processados pelos detectores "
        f"({taxa_analise:.1f}% da base)."
    )
    st.success(
        f"**[03] Laudos de IA**\n\n"
        f"`{laudos:,}` vereditos gerados pelo Gemini ({taxa_laudo:.1f}% da base)."
    )


def main() -> None:
    _carregar_env()
    st.set_page_config(page_title="Sentinela RJ", layout="wide")
    _injetar_tema()
    st.title("Sentinela RJ — Threat Intelligence")
    st.caption("Console de monitoramento de contratos públicos · classificação restrita")

    if _conectar() is None:
        st.error(f"Banco não encontrado: {_DB_PATH}")
        st.stop()

    anomalias = _carregar_anomalias()
    funil = _carregar_funil()
    if anomalias.empty:
        st.warning("Nenhuma anomalia no banco. Execute `analisar` na CLI.")
        st.stop()

    pagina, orgao, indice = _render_sidebar(anomalias)
    filtrado = _aplicar_filtros(anomalias, orgao, indice)

    _render_metricas_topo(filtrado, funil)
    st.divider()

    if pagina == "Visão Geral":
        _pagina_visao_geral(filtrado)
    elif pagina == "Investigação":
        _pagina_investigacao(filtrado)
    else:
        _pagina_logs(funil)


if __name__ == "__main__":
    main()
