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


def _conectar() -> sqlite3.Connection | None:
    if not _DB_PATH.is_file():
        return None
    return sqlite3.connect(_DB_PATH)


def _injetar_design_system() -> None:
    st.markdown(
        """
        <style>
        .stApp { background-color: #09090b; color: #fafafa; }
        #MainMenu, footer, header { visibility: hidden; height: 0; }
        .stDeployButton, [data-testid="stToolbar"] { display: none; }
        .block-container { padding-top: 1.5rem; max-width: 1200px; }
        h1, h2, h3, p, label, span,
        [data-testid="stSidebar"], [data-testid="stSidebar"] *,
        [data-testid="stSelectbox"] label, [data-testid="stMarkdownContainer"] {
            color: #fafafa !important;
        }
        [data-testid="stSidebar"] {
            background-color: #09090b !important;
            border-right: 1px solid #27272a !important;
        }
        [data-testid="metric-container"] {
            background: #18181b; border: 1px solid #27272a;
            border-radius: 8px; padding: 1rem;
        }
        [data-testid="stMetricValue"] { color: #fafafa !important; }
        .stButton > button {
            background: #18181b !important; color: #fafafa !important;
            border: 1px solid #27272a !important; border-radius: 8px !important;
            transition: all 0.2s ease !important;
        }
        .stButton > button:hover {
            border-color: #6366f1 !important;
            box-shadow: 0 0 12px rgba(99, 102, 241, 0.35) !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: #18181b; border-color: #27272a !important;
            border-radius: 8px; padding: 0.5rem;
        }
        div[data-baseweb="tab-list"] button { color: #fafafa !important; }
        div[data-baseweb="tab-list"] button[aria-selected="true"] {
            color: #fafafa !important; border-color: #6366f1 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


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


def _render_sidebar(df: pd.DataFrame) -> tuple[str, str]:
    st.sidebar.markdown("## Painel de Controle")
    st.sidebar.caption("Sistema Fechado — Acesso Restrito")
    st.sidebar.divider()
    st.sidebar.subheader("Filtros de Investigação")
    if df.empty:
        st.sidebar.info("Sem anomalias para filtrar.")
        return "Todos", "Todos"
    orgaos = ["Todos"] + sorted(df["orgao"].dropna().unique().tolist())
    indices = ["Todos"] + sorted(df["indice_suspeita"].dropna().unique().tolist())
    orgao = st.sidebar.selectbox("Órgão", orgaos)
    indice = st.sidebar.selectbox("Índice de Suspeita", indices)
    return orgao, indice


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
    c2.metric("Laudos de IA", f"{laudos:,}", delta=f"{pendentes} pendentes" if pendentes else "Completo")
    c3.metric("Volume em Risco", _formatar_moeda(volume))
    c4.metric("Base Analisada", f"{funil['analisados']:,}", delta=f"{funil['extraidos']:,} extraídos")


def _grafico_pizza(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Sem dados para o gráfico de tipos de suspeita.")
        return
    agg = df.groupby("tipo_suspeita", as_index=False).size().rename(columns={"size": "qtd"})
    fig = px.pie(agg, names="tipo_suspeita", values="qtd", hole=0.45)
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#09090b", plot_bgcolor="#18181b",
        margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(fig, width="stretch")


def _grafico_barras(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Sem dados para o gráfico de volume financeiro.")
        return
    agg = (
        df.groupby("tipo_suspeita", as_index=False)["valor_referencia"]
        .sum()
        .rename(columns={"valor_referencia": "volume"})
    )
    fig = px.bar(agg, x="tipo_suspeita", y="volume", color="volume", color_continuous_scale="Redor")
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#09090b", plot_bgcolor="#18181b",
        showlegend=False, margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(fig, width="stretch")


def _render_card_anomalia(linha: pd.Series) -> None:
    id_anomalia = int(linha["id"])
    with st.container(border=True):
        topo1, topo2 = st.columns([2, 1])
        topo1.markdown(f"### Alerta #{id_anomalia}")
        topo2.markdown(f"**Índice:** {linha['indice_suspeita']}")
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"**Órgão**\n\n{linha['orgao']}")
        c2.markdown(f"**Valor**\n\n{_formatar_moeda(float(linha['valor_referencia']))}")
        c3.markdown(f"**Fornecedor**\n\n{linha['fornecedor']}")
        c4.markdown(f"**Tipo de Suspeita**\n\n{linha['tipo_suspeita']}")
        st.caption(str(linha["descricao"])[:200])
        if _tem_narrativa(linha["narrativa_ia"]):
            st.markdown("**Veredito do Investigador de Inteligência Artificial**")
            st.info(str(linha["narrativa_ia"]))
        elif st.button("🧠 Investigar com IA", key=f"btn_{id_anomalia}"):
            if not os.environ.get("GEMINI_API_KEY", "").strip():
                st.error("GEMINI_API_KEY não definida. Configure no arquivo .env.")
            else:
                _executar_investigacao_ia(id_anomalia, linha)


def _aba_executiva(df: pd.DataFrame) -> None:
    st.markdown("### Panorama de Ameaças")
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Tipos de Suspeita**")
        _grafico_pizza(df)
    with g2:
        st.markdown("**Volume Financeiro Anômalo**")
        _grafico_barras(df)


def _aba_investigacao(df: pd.DataFrame) -> None:
    st.markdown("### Evidências e Rastreamento")
    if df.empty:
        st.warning("Nenhuma anomalia encontrada com os filtros aplicados.")
        return
    for _, linha in df.iterrows():
        _render_card_anomalia(linha)


def _aba_percurso(funil: dict[str, int]) -> None:
    st.markdown("### Linha do Tempo da Operação")
    st.caption("Funil completo: da extração bruta ao laudo investigativo automatizado.")
    extraidos, analisados, laudos = funil["extraidos"], funil["analisados"], funil["laudos_ia"]
    taxa_analise = (analisados / extraidos * 100) if extraidos else 0
    taxa_laudo = (laudos / analisados * 100) if analisados else 0
    st.success(
        f"**Etapa 1 — Extração do Portal**\n\n"
        f"{extraidos:,} contratos brutos coletados do PNCP e registrados no sistema."
    )
    st.info(
        f"**Etapa 2 — Análise Estatística**\n\n"
        f"{analisados:,} contratos passaram pelos detectores de anomalia "
        f"({taxa_analise:.1f}% da base extraída)."
    )
    st.success(
        f"**Etapa 3 — Laudos de Inteligência Artificial**\n\n"
        f"{laudos:,} vereditos investigativos gerados pelo Gemini "
        f"({taxa_laudo:.1f}% dos contratos analisados)."
    )


def main() -> None:
    _carregar_env()
    st.set_page_config(page_title="Sentinela RJ", layout="wide")
    _injetar_design_system()
    st.title("Sentinela RJ — Inteligência de Ameaças")
    st.caption("Sistema Fechado de Monitoramento de Contratos Públicos")

    if _conectar() is None:
        st.error(f"Banco não encontrado: {_DB_PATH}")
        st.stop()

    anomalias = _carregar_anomalias()
    funil = _carregar_funil()
    if anomalias.empty:
        st.warning("Nenhuma anomalia no banco. Execute `analisar` na CLI.")
        st.stop()

    orgao, indice = _render_sidebar(anomalias)
    filtrado = _aplicar_filtros(anomalias, orgao, indice)

    _render_metricas_topo(filtrado, funil)
    st.divider()
    tab_exec, tab_inv, tab_per = st.tabs(
        ["📊 Visão Executiva", "🔎 Investigação Detalhada", "⚙️ Percurso da Operação"]
    )
    with tab_exec:
        _aba_executiva(filtrado)
    with tab_inv:
        _aba_investigacao(filtrado)
    with tab_per:
        _aba_percurso(funil)


if __name__ == "__main__":
    main()
