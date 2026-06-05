"""Dashboard interativo de despesas — Sentinela."""
from __future__ import annotations

import logging
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from db.database import GerenciadorBanco

load_dotenv()

logger = logging.getLogger(__name__)

_COLUNAS_VALOR = ("valor", "valor_total", "valor_global", "valor_despesa")


def _nome_tabela() -> str:
    nome = os.getenv("DASHBOARD_TABELA_DESPESAS", "").strip()
    if not nome:
        raise ValueError("DASHBOARD_TABELA_DESPESAS não definida.")
    return nome


def _tema_dashboard() -> str:
    tema = os.getenv("DASHBOARD_TEMA", "dark").strip().lower()
    return tema if tema in {"dark", "light"} else "dark"


def _injetar_css(tema: str) -> None:
    escuro = tema == "dark"
    fundo = "#0a0a0a" if escuro else "#ffffff"
    texto = "#fafafa" if escuro else "#171717"
    borda = "#262626" if escuro else "#e5e5e5"
    css = (
        f"<style>.stApp{{background:{fundo};color:{texto};"
        f'font-family:"Geist","Inter",system-ui,sans-serif;font-weight:300;}}'
        f"[data-testid='stMetric']{{border:1px solid {borda};border-radius:6px;"
        f"padding:1rem;background:{fundo};}}"
        f"[data-testid='stDataFrame']{{border:1px solid {borda};border-radius:6px;}}"
        f"h1,h2,h3{{font-weight:300;letter-spacing:-0.02em;}}</style>"
    )
    st.markdown(css, unsafe_allow_html=True)


def _consultar_despesas(gerenciador: GerenciadorBanco, tabela: str) -> pd.DataFrame:
    try:
        return pd.read_sql(f'SELECT * FROM "{tabela}"', gerenciador._engine)
    except SQLAlchemyError as exc:
        st.error(f"Falha ao consultar o banco: {exc}")
        return pd.DataFrame()


def _detectar_coluna_valor(df: pd.DataFrame) -> str | None:
    for coluna in _COLUNAS_VALOR:
        if coluna in df.columns:
            return coluna
    return None


def _renderizar_metricas(df: pd.DataFrame) -> None:
    col_valor = _detectar_coluna_valor(df)
    col_orgao = next((c for c in ("orgao_id", "orgao", "orgao_nome") if c in df.columns), None)
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", f"{len(df):,}".replace(",", "."))
    if col_valor:
        total = pd.to_numeric(df[col_valor], errors="coerce").sum()
        c2.metric("Valor total", f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    if col_orgao:
        c3.metric("Órgãos", f"{df[col_orgao].nunique():,}".replace(",", "."))


def _renderizar_tabela(df: pd.DataFrame) -> None:
    st.subheader("Dados brutos")
    st.dataframe(df, use_container_width=True, hide_index=True)


def renderizar_dashboard() -> None:
    logger.info("Dashboard inicializado com sucesso")
    st.set_page_config(page_title="Sentinela — Despesas", layout="wide")
    _injetar_css(_tema_dashboard())
    st.title("Dashboard de Despesas")

    gerenciador = GerenciadorBanco()
    df = _consultar_despesas(gerenciador, _nome_tabela())
    if df.empty:
        st.error("Nenhum dado de despesas disponível para exibição.")
        return

    _renderizar_metricas(df)
    _renderizar_tabela(df)


if __name__ == "__main__":
    renderizar_dashboard()
