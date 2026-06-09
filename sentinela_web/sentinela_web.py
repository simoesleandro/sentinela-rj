"""Sentinela RJ — Painel Threat Intelligence (Reflex)."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import plotly.express as px
import reflex as rx
from plotly.graph_objs import Figure

_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _ROOT / "data" / "sentinela_rj.db"
_MENU = ["Visão Geral", "Investigação", "Logs"]

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
SELECT a.id, a.tipo, a.severidade, a.descricao, a.valor_referencia,
       a.status, a.narrativa_ia, a.numero_controle_pncp, a.metodologia,
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

_CARD_STYLE = {
    "background": "#151a23",
    "border": "1px solid #1e2530",
    "border_radius": "4px",
    "padding": "1rem",
    "width": "100%",
}


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


def _formatar_moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _tem_narrativa(valor: Any) -> bool:
    return bool(str(valor or "").strip())


def _conectar() -> sqlite3.Connection | None:
    if not _DB_PATH.is_file():
        return None
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _rows_para_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    colunas = [desc[0] for desc in cursor.description or []]
    return [dict(zip(colunas, row)) for row in cursor.fetchall()]


def _enriquecer_anomalia(linha: dict[str, Any]) -> dict[str, Any]:
    tipo = str(linha.get("tipo", ""))
    severidade = str(linha.get("severidade", ""))
    valor_ref = float(linha.get("valor_referencia") or 0)
    valor_glob = float(linha.get("valor_global") or 0)
    narrativa = linha.get("narrativa_ia")
    return {
        "id": int(linha["id"]),
        "tipo": tipo,
        "severidade": severidade,
        "descricao": str(linha.get("descricao") or ""),
        "valor_referencia": valor_ref,
        "valor_global": valor_glob,
        "status": str(linha.get("status") or ""),
        "narrativa_ia": str(narrativa) if narrativa else "",
        "numero_controle_pncp": str(linha.get("numero_controle_pncp") or ""),
        "metodologia": str(linha.get("metodologia") or ""),
        "orgao": str(linha.get("orgao") or "Não informado"),
        "fornecedor": str(linha.get("fornecedor") or "Não informado"),
        "objeto": str(linha.get("objeto") or ""),
        "tipo_suspeita": _LABEL_TIPO.get(tipo, tipo.replace("_", " ").title()),
        "indice_suspeita": _LABEL_RISCO.get(severidade, severidade.title()),
        "valor_fmt": _formatar_moeda(valor_ref),
        "valor_global_fmt": _formatar_moeda(valor_glob),
        "tem_laudo": _tem_narrativa(narrativa),
    }


def _buscar_anomalias() -> list[dict[str, Any]]:
    conn = _conectar()
    if conn is None:
        return []
    try:
        cursor = conn.execute(_SQL_ANOMALIAS)
        return [_enriquecer_anomalia(linha) for linha in _rows_para_dicts(cursor)]
    finally:
        conn.close()


def _buscar_funil() -> dict[str, int]:
    conn = _conectar()
    if conn is None:
        return {"extraidos": 0, "analisados": 0, "laudos_ia": 0}
    try:
        cursor = conn.execute(_SQL_FUNIL)
        linhas = _rows_para_dicts(cursor)
        if not linhas:
            return {"extraidos": 0, "analisados": 0, "laudos_ia": 0}
        row = linhas[0]
        return {
            "extraidos": int(row["extraidos"]),
            "analisados": int(row["analisados"]),
            "laudos_ia": int(row["laudos_ia"]),
        }
    finally:
        conn.close()


def _figura_pizza(anomalias: list[dict[str, Any]]) -> Figure:
    contagem: dict[str, int] = {}
    for item in anomalias:
        chave = item["tipo_suspeita"]
        contagem[chave] = contagem.get(chave, 0) + 1
    fig = px.pie(
        names=list(contagem.keys()) or ["—"],
        values=list(contagem.values()) or [1],
        hole=0.45,
        color_discrete_sequence=["#00e5ff", "#ff2a55", "#6366f1", "#22d3ee"],
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0e14",
        plot_bgcolor="#151a23",
        font_color="#e2e8f0",
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig


def _figura_barras(anomalias: list[dict[str, Any]]) -> Figure:
    volumes: dict[str, float] = {}
    for item in anomalias:
        chave = item["tipo_suspeita"]
        volumes[chave] = volumes.get(chave, 0.0) + float(item["valor_referencia"])
    fig = px.bar(
        x=list(volumes.keys()) or ["—"],
        y=list(volumes.values()) or [0],
        color=list(volumes.values()) or [0],
        color_continuous_scale=["#151a23", "#00e5ff", "#ff2a55"],
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0e14",
        plot_bgcolor="#151a23",
        font_color="#e2e8f0",
        showlegend=False,
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig


class SentinelaState(rx.State):
    """Estado reativo — conexão sqlite3 e dados do painel."""

    pagina: str = "Visão Geral"
    filtro_orgao: str = "Todos"
    filtro_indice: str = "Todos"
    anomalias: list[dict[str, Any]] = []
    extraidos: int = 0
    analisados: int = 0
    laudos_ia: int = 0
    erro: str = ""
    aviso: str = ""
    carregando: bool = False
    investigando_id: int = 0
    mensagem_ia: str = ""

    @rx.var
    def orgaos(self) -> list[str]:
        unicos = sorted({str(a["orgao"]) for a in self.anomalias})
        return ["Todos", *unicos]

    @rx.var
    def indices(self) -> list[str]:
        unicos = sorted({str(a["indice_suspeita"]) for a in self.anomalias})
        return ["Todos", *unicos]

    @rx.var
    def anomalias_filtradas(self) -> list[dict[str, Any]]:
        resultado = self.anomalias
        if self.filtro_orgao != "Todos":
            resultado = [a for a in resultado if a["orgao"] == self.filtro_orgao]
        if self.filtro_indice != "Todos":
            resultado = [a for a in resultado if a["indice_suspeita"] == self.filtro_indice]
        return resultado

    @rx.var
    def total_alertas(self) -> int:
        return len(self.anomalias_filtradas)

    @rx.var
    def total_laudos(self) -> int:
        return sum(1 for a in self.anomalias_filtradas if a["tem_laudo"])

    @rx.var
    def total_criticos(self) -> int:
        return sum(1 for a in self.anomalias_filtradas if a["severidade"] == "alta")

    @rx.var
    def volume_risco(self) -> str:
        total = sum(float(a["valor_referencia"]) for a in self.anomalias_filtradas)
        return _formatar_moeda(total)

    @rx.var
    def pendentes_ia(self) -> int:
        return self.total_alertas - self.total_laudos

    @rx.var
    def taxa_analise(self) -> str:
        if not self.extraidos:
            return "0.0"
        return f"{self.analisados / self.extraidos * 100:.1f}"

    @rx.var
    def taxa_laudo(self) -> str:
        if not self.analisados:
            return "0.0"
        return f"{self.laudos_ia / self.analisados * 100:.1f}"

    @rx.var
    def banco_ok(self) -> bool:
        return _DB_PATH.is_file()

    @rx.var(cache=True)
    def fig_pizza(self) -> Figure:
        return _figura_pizza(self.anomalias_filtradas)

    @rx.var(cache=True)
    def fig_barras(self) -> Figure:
        return _figura_barras(self.anomalias_filtradas)

    def set_pagina(self, valor: str) -> None:
        self.pagina = valor

    def set_filtro_orgao(self, valor: str) -> None:
        self.filtro_orgao = valor

    def set_filtro_indice(self, valor: str) -> None:
        self.filtro_indice = valor

    def carregar_dados(self) -> None:
        self.carregando = True
        self.erro = ""
        self.aviso = ""
        if not _DB_PATH.is_file():
            self.erro = f"Banco não encontrado: {_DB_PATH}"
            self.anomalias = []
            self.carregando = False
            return
        self.anomalias = _buscar_anomalias()
        funil = _buscar_funil()
        self.extraidos = funil["extraidos"]
        self.analisados = funil["analisados"]
        self.laudos_ia = funil["laudos_ia"]
        if not self.anomalias:
            self.aviso = "Nenhuma anomalia no banco. Execute `analisar` na CLI."
        self.carregando = False

    @rx.event(background=True)
    async def investigar_ia(self, id_anomalia: int) -> None:
        async with self:
            self.investigando_id = id_anomalia
            self.mensagem_ia = ""
            alvo = next((a for a in self.anomalias if a["id"] == id_anomalia), None)
        try:
            if alvo is None:
                raise ValueError(f"Anomalia {id_anomalia} não encontrada.")
            from analise.motor_ia import InvestigadorIA
            from db.database import GerenciadorBanco

            narrativa = InvestigadorIA().investigar_anomalia(dict(alvo))
            GerenciadorBanco(db_path=_DB_PATH).atualizar_narrativa_anomalia(
                id_anomalia, narrativa
            )
            async with self:
                self.carregar_dados()
                self.investigando_id = 0
        except Exception as exc:
            async with self:
                self.mensagem_ia = f"Falha na investigação IA: {exc}"
                self.investigando_id = 0


def _metric_card(titulo: str, valor: str, detalhe: str, neon: str) -> rx.Component:
    return rx.box(
        rx.text(titulo, size="1", color="#94a3b8", weight="medium"),
        rx.heading(valor, size="6", font_family="Consolas, monospace", color="#00e5ff"),
        rx.text(detalhe, size="1", color="#64748b"),
        style={**_CARD_STYLE, "border_top": f"2px solid {neon}"},
    )


def _sidebar() -> rx.Component:
    return rx.box(
        rx.heading("◈ SENTINELA RJ", size="5"),
        rx.text("Threat Intelligence Console", size="1", color="#94a3b8"),
        rx.divider(margin_y="1rem"),
        rx.text("Navegação", size="2", weight="bold"),
        rx.radio(
            _MENU,
            value=SentinelaState.pagina,
            on_change=SentinelaState.set_pagina,
            direction="column",
            spacing="2",
        ),
        rx.divider(margin_y="1rem"),
        rx.text("Filtros Táticos", size="2", weight="bold"),
        rx.select(
            SentinelaState.orgaos,
            value=SentinelaState.filtro_orgao,
            on_change=SentinelaState.set_filtro_orgao,
            width="100%",
        ),
        rx.select(
            SentinelaState.indices,
            value=SentinelaState.filtro_indice,
            on_change=SentinelaState.set_filtro_indice,
            width="100%",
        ),
        style={
            "background": "#12161f",
            "padding": "1.5rem",
            "min_width": "260px",
            "height": "100vh",
            "position": "sticky",
            "top": "0",
        },
    )


def _metricas() -> rx.Component:
    return rx.grid(
        _metric_card(
            "ALERTAS ATIVOS",
            SentinelaState.total_alertas.to_string(),
            SentinelaState.total_criticos.to_string() + " críticos",
            "#ff2a55",
        ),
        _metric_card(
            "LAUDOS IA",
            SentinelaState.total_laudos.to_string(),
            rx.cond(
                SentinelaState.pendentes_ia > 0,
                SentinelaState.pendentes_ia.to_string() + " pendentes",
                "OK",
            ),
            "#00e5ff",
        ),
        _metric_card("VOLUME EM RISCO", SentinelaState.volume_risco, "em análise", "#00e5ff"),
        _metric_card(
            "BASE ANALISADA",
            SentinelaState.analisados.to_string(),
            SentinelaState.extraidos.to_string() + " extraídos",
            "#ff2a55",
        ),
        columns="4",
        spacing="4",
        width="100%",
    )


def _card_anomalia(anomalia: dict[str, Any]) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.heading("◈ ALERTA #", anomalia["id"], size="4"),
            rx.badge(anomalia["indice_suspeita"], color_scheme="red"),
            justify="between",
            width="100%",
        ),
        rx.grid(
            rx.vstack(rx.text("Órgão", size="1", color="#94a3b8"), rx.text(anomalia["orgao"])),
            rx.vstack(rx.text("Valor", size="1", color="#94a3b8"), rx.code(anomalia["valor_fmt"])),
            rx.vstack(rx.text("Fornecedor", size="1", color="#94a3b8"), rx.text(anomalia["fornecedor"])),
            rx.vstack(rx.text("Tipo", size="1", color="#94a3b8"), rx.text(anomalia["tipo_suspeita"])),
            columns="4",
            spacing="3",
            width="100%",
            margin_top="0.75rem",
        ),
        rx.text(anomalia["descricao"], size="1", color="#64748b", margin_top="0.5rem"),
        rx.cond(
            anomalia["tem_laudo"],
            rx.box(
                rx.text("▸ Veredito IA", weight="bold", margin_bottom="0.5rem"),
                rx.callout(anomalia["narrativa_ia"], icon="info"),
                margin_top="0.75rem",
            ),
            rx.cond(
                SentinelaState.investigando_id == anomalia["id"],
                rx.spinner(size="2"),
                rx.button(
                    "🧠 Investigar com IA",
                    on_click=SentinelaState.investigar_ia(anomalia["id"]),
                    color_scheme="red",
                    margin_top="0.75rem",
                ),
            ),
        ),
        style=_CARD_STYLE,
        margin_bottom="1rem",
    )


def _pagina_visao_geral() -> rx.Component:
    return rx.vstack(
        rx.heading("◈ Panorama de Ameaças", size="5"),
        rx.grid(
            rx.box(
                rx.text("Distribuição por Tipo", weight="bold", margin_bottom="0.5rem"),
                rx.cond(
                    SentinelaState.total_alertas > 0,
                    rx.plotly(data=SentinelaState.fig_pizza),
                    rx.callout("Sem dados para o gráfico.", icon="triangle_alert"),
                ),
            ),
            rx.box(
                rx.text("Volume Financeiro Anômalo", weight="bold", margin_bottom="0.5rem"),
                rx.cond(
                    SentinelaState.total_alertas > 0,
                    rx.plotly(data=SentinelaState.fig_barras),
                    rx.callout("Sem dados para o gráfico.", icon="triangle_alert"),
                ),
            ),
            columns="2",
            spacing="4",
            width="100%",
        ),
        width="100%",
        spacing="4",
    )


def _pagina_investigacao() -> rx.Component:
    return rx.vstack(
        rx.heading("◈ Matriz de Evidências", size="5"),
        rx.cond(
            SentinelaState.total_alertas > 0,
            rx.vstack(
                rx.data_table(
                    data=SentinelaState.anomalias_filtradas,
                    columns=[
                        "id",
                        "tipo_suspeita",
                        "indice_suspeita",
                        "orgao",
                        "fornecedor",
                        "valor_fmt",
                        "valor_global_fmt",
                        "status",
                    ],
                    search=True,
                    pagination=True,
                    width="100%",
                ),
                rx.divider(margin_y="1rem"),
                rx.heading("◈ Dossiês Individuais", size="5"),
                rx.foreach(SentinelaState.anomalias_filtradas, _card_anomalia),
                width="100%",
                spacing="3",
            ),
            rx.callout(
                "Nenhuma anomalia encontrada com os filtros aplicados.",
                icon="triangle_alert",
            ),
        ),
        width="100%",
        spacing="4",
    )


def _pagina_logs() -> rx.Component:
    return rx.vstack(
        rx.heading("◈ Percurso da Operação", size="5"),
        rx.text(
            "Pipeline de inteligência — extração → análise → laudo IA",
            size="2",
            color="#94a3b8",
        ),
        rx.callout(
            rx.vstack(
                rx.text("[01] Extração do Portal", weight="bold"),
                rx.text(SentinelaState.extraidos.to_string(), " contratos brutos coletados do PNCP."),
            ),
            icon="check",
            color_scheme="green",
        ),
        rx.callout(
            rx.vstack(
                rx.text("[02] Análise Estatística", weight="bold"),
                rx.text(
                    SentinelaState.analisados.to_string(),
                    " contratos processados (",
                    SentinelaState.taxa_analise,
                    "% da base).",
                ),
            ),
            icon="info",
        ),
        rx.callout(
            rx.vstack(
                rx.text("[03] Laudos de IA", weight="bold"),
                rx.text(
                    SentinelaState.laudos_ia.to_string(),
                    " vereditos Gemini (",
                    SentinelaState.taxa_laudo,
                    "% da base).",
                ),
            ),
            icon="check",
            color_scheme="green",
        ),
        width="100%",
        spacing="4",
    )


def _conteudo_principal() -> rx.Component:
    return rx.vstack(
        rx.heading("Sentinela RJ — Inteligência de Ameaças", size="8"),
        rx.text(
            "Console de monitoramento de contratos públicos · classificação restrita",
            size="2",
            color="#94a3b8",
        ),
        rx.cond(SentinelaState.erro != "", rx.callout(SentinelaState.erro, icon="circle_alert", color_scheme="red")),
        rx.cond(SentinelaState.aviso != "", rx.callout(SentinelaState.aviso, icon="info")),
        rx.cond(
            SentinelaState.mensagem_ia != "",
            rx.callout(SentinelaState.mensagem_ia, icon="circle_alert", color_scheme="red"),
        ),
        rx.cond(SentinelaState.carregando, rx.spinner(size="3")),
        rx.cond(
            SentinelaState.banco_ok & (SentinelaState.anomalias.length() > 0),
            rx.vstack(
                _metricas(),
                rx.divider(margin_y="1rem"),
                rx.match(
                    SentinelaState.pagina,
                    ("Visão Geral", _pagina_visao_geral()),
                    ("Investigação", _pagina_investigacao()),
                    ("Logs", _pagina_logs()),
                    _pagina_visao_geral(),
                ),
                width="100%",
                spacing="4",
            ),
        ),
        width="100%",
        spacing="4",
        padding="2rem",
    )


def index() -> rx.Component:
    return rx.box(
        rx.hstack(
            _sidebar(),
            rx.container(
                _conteudo_principal(),
                max_width="1280px",
                width="100%",
                padding="0",
            ),
            spacing="0",
            align="start",
            width="100%",
        ),
        style={"background": "#0b0e14", "min_height": "100vh", "color": "#e2e8f0"},
    )


_carregar_env()

app = rx.App(
    theme=rx.theme(
        appearance="dark",
        has_background=True,
        radius="medium",
        accent_color="crimson",
    ),
    style={"background_color": "#0b0e14"},
)
app.add_page(index, route="/", title="Sentinela RJ", on_load=SentinelaState.carregar_dados)
