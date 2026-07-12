"""
Sentinela RJ - Exportação de relatório em PDF via fpdf2.

Uso interno:
    from relatorios.pdf_export import gerar_pdf_bytes
    pdf_bytes = gerar_pdf_bytes(conn)
"""
from __future__ import annotations

import sqlite3
from datetime import date
from io import BytesIO

from fpdf import FPDF

from analise.labels import label_tipo

# Substituições pontuais para os poucos chars unicode fora do latin-1
# que aparecem em dados reais (tipografia, etc.). Chars PT-BR (ã á ç é...)
# são U+00C0-U+00FF e entram em latin-1 diretamente — não precisam de conversão.
_FORA_LATIN1 = str.maketrans({
    "—": "-",    # em dash —
    "–": "-",    # en dash –
    "‘": "'",    # ' left single quote
    "’": "'",    # ' right single quote
    "“": '"',    # " left double quote
    "”": '"',    # " right double quote
    "…": "...",  # … ellipsis
    "·": ".",    # · middle dot
    "•": "-",    # • bullet
})


def _safe(text: str, maxlen: int = 0) -> str:
    """Garante compatibilidade com Helvetica (latin-1): pre-substitui chars
    tipográficos fora do range e descarta o restante com 'replace'."""
    if not text:
        return ""
    s = str(text).translate(_FORA_LATIN1)
    s = s.encode("latin-1", errors="replace").decode("latin-1")
    return s[:maxlen] if maxlen else s

# ── Paleta ────────────────────────────────────────────────────────────────────
_AZUL      = (30,  64, 175)   # header / títulos
_AZUL_CLARO= (219, 234, 254)  # fundo de linha par na tabela
_CINZA     = (107, 114, 128)  # rodapé / texto secundário
_VERMELHO  = (220,  38,  38)  # severidade alta
_AMARELO   = (161, 124,   0)  # severidade média
_VERDE     = ( 22, 163,  74)  # severidade baixa
_BRANCO    = (255, 255, 255)
_PRETO     = (  0,   0,   0)

# Mapeamentos de tipo de alerta (espelha analise/labels.py)
# Rótulos de tipo vêm da fonte canônica (analise.labels), não de um dicionário
# próprio — mantém o vocabulário consistente entre dashboard, dossiê e PDF.
def _label(tipo: str) -> str:
    return label_tipo(tipo)


def _cor_sev(sev: str) -> tuple[int, int, int]:
    return {"alta": _VERMELHO, "media": _AMARELO}.get(sev, _VERDE)


# ── Consultas ─────────────────────────────────────────────────────────────────

def _kpis(conn: sqlite3.Connection) -> dict:
    contratos_total = conn.execute(
        "SELECT COUNT(*) FROM contratos WHERE valor_global > 0"
    ).fetchone()[0]
    valor_total = conn.execute(
        "SELECT COALESCE(SUM(valor_global), 0) FROM contratos WHERE valor_global > 0"
    ).fetchone()[0]
    alertas_abertos = conn.execute(
        "SELECT COUNT(*) FROM alertas WHERE COALESCE(status,'aberto') IN ('aberto','investigando')"
    ).fetchone()[0]
    return {
        "contratos_total": contratos_total,
        "valor_total": valor_total,
        "alertas_abertos": alertas_abertos,
    }


def _top_alertas(conn: sqlite3.Connection, limite: int = 10) -> list[dict]:
    # GROUP BY fornecedor+tipo garante 1 alerta por fornecedor/tipo,
    # mostrando os casos mais diversos (sem repetir o mesmo fornecedor).
    rows = conn.execute(
        """
        SELECT DISTINCT a.numero_controle_pncp, a.tipo, a.severidade,
               a.descricao, c.valor_global AS valor
        FROM alertas a
        JOIN contratos c ON a.numero_controle_pncp = c.numero_controle_pncp
        WHERE a.severidade = 'alta'
        GROUP BY c.fornecedor_ni, a.tipo
        ORDER BY c.valor_global DESC
        LIMIT ?
        """,
        (limite,),
    ).fetchall()
    return [dict(r) for r in rows]


def _casos(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT titulo, fornecedor_nome, valor, status, resumo FROM casos ORDER BY ordem ASC, id ASC"
    ).fetchall()
    return [dict(r) for r in rows]


# ── PDF ────────────────────────────────────────────────────────────────────────

class _PDF(FPDF):
    def __init__(self):
        super().__init__("P", "mm", "A4")
        self.set_auto_page_break(auto=True, margin=18)
        self._pagina_num = 0
        self.add_page()

    # cabecalho de cada pagina
    def header(self):
        self._pagina_num += 1
        self.set_fill_color(*_AZUL)
        self.rect(0, 0, 210, 16, "F")
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*_BRANCO)
        self.set_xy(10, 4)
        self.cell(0, 8, "SENTINELA RJ - Relatorio de Monitoramento", ln=False)
        self.set_font("Helvetica", "", 8)
        self.set_xy(0, 4)
        self.cell(200, 8, f"Pag. {self._pagina_num}", align="R", ln=False)
        self.set_text_color(*_PRETO)
        self.ln(18)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*_CINZA)
        self.multi_cell(
            0, 4,
            "Fonte: Portal Nacional de Contratacoes Publicas (PNCP)  |  "
            "Dados sujeitos a atualizacao - uso para fins de transparencia e controle social.",
            align="C",
        )
        self.set_text_color(*_PRETO)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _titulo_secao(self, texto: str) -> None:
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*_AZUL)
        self.cell(0, 7, _safe(texto), ln=True)
        self.set_draw_color(*_AZUL)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)
        self.set_text_color(*_PRETO)

    def _kpi_box(self, label: str, valor: str, x: float, y: float, w: float = 57) -> None:
        self.set_xy(x, y)
        self.set_fill_color(*_AZUL_CLARO)
        self.rect(x, y, w, 18, "F")
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_CINZA)
        self.set_xy(x + 2, y + 2)
        self.cell(w - 4, 5, _safe(label).upper(), ln=True)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*_AZUL)
        self.set_xy(x + 2, y + 7)
        self.cell(w - 4, 8, _safe(valor), ln=True)
        self.set_text_color(*_PRETO)

    def _row_alerta(self, n: int, row: dict, y_atual: float) -> float:
        """Desenha a linha e retorna a altura real usada (mm)."""
        # Larguras: # 8 | Sev. 15 | Tipo 35 | Desc. 95 | Valor 30  (total 183 + margens = 190)
        LINE_H = 6.0
        sev   = row.get("severidade", "baixa")
        cor   = _cor_sev(sev)
        tipo  = _safe(_label(row.get("tipo", "")))
        raw   = _safe(row.get("descricao") or "")
        desc  = raw[:80] + "..." if len(raw) > 80 else raw
        valor = row.get("valor") or 0
        bg    = _AZUL_CLARO if n % 2 == 0 else _BRANCO

        # Calcula quantas linhas o multi_cell vai usar para dimensionar o fundo
        self.set_font("Helvetica", "", 7)
        n_linhas = max(1, -(-len(desc) // max(1, int(95 / max(0.1, self.get_string_width("n"))))))
        row_h = LINE_H * n_linhas + 2  # +2mm de padding vertical

        self.set_fill_color(*bg)
        self.set_xy(10, y_atual)
        self.rect(10, y_atual, 190, row_h, "F")

        # #
        self.set_font("Helvetica", "", 8)
        self.set_xy(10, y_atual + 1)
        self.cell(8, LINE_H, str(n), align="C")

        # badge severidade (x=18, w=15)
        self.set_fill_color(*cor)
        self.rect(18, y_atual + 1.5, 15, 5, "F")
        self.set_text_color(*_BRANCO)
        self.set_font("Helvetica", "B", 6)
        self.set_xy(18, y_atual + 2)
        self.cell(15, 4, sev.upper(), align="C")
        self.set_text_color(*_PRETO)

        # tipo (x=33, w=35)
        self.set_font("Helvetica", "", 7)
        self.set_xy(33, y_atual + 1)
        self.cell(35, LINE_H, tipo[:22])

        # descrição (x=68, w=95) — multi_cell com quebra de linha se necessário
        self.set_xy(68, y_atual + 1)
        self.multi_cell(95, LINE_H, desc, border=0)

        # valor (x=163) — posição absoluta para não depender de onde multi_cell parou
        self.set_font("Helvetica", "B", 7)
        self.set_xy(163, y_atual + 1)
        self.cell(30, LINE_H, f"R$ {valor:,.0f}".replace(",", "X").replace(".", ",").replace("X", "."), align="R")

        return row_h

    def _row_caso(self, n: int, row: dict, y_atual: float) -> None:
        status = row.get("status", "")
        cor_st = {"confirmado": _VERMELHO, "investigando": _AMARELO}.get(status, _VERDE)
        bg = _AZUL_CLARO if n % 2 == 0 else _BRANCO
        titulo = _safe(row.get("titulo") or "", 55)
        forn   = _safe(row.get("fornecedor_nome") or "", 35)
        valor  = row.get("valor") or 0

        self.set_fill_color(*bg)
        self.set_xy(10, y_atual)
        self.rect(10, y_atual, 190, 8, "F")

        self.set_font("Helvetica", "", 8)
        self.set_xy(10, y_atual + 1)
        self.cell(8, 6, str(n), align="C")

        # badge status
        self.set_fill_color(*cor_st)
        self.rect(19, y_atual + 1.5, 22, 5, "F")
        self.set_text_color(*_BRANCO)
        self.set_font("Helvetica", "B", 6)
        self.set_xy(19, y_atual + 2)
        self.cell(22, 4, status.upper(), align="C")
        self.set_text_color(*_PRETO)

        self.set_font("Helvetica", "", 7)
        self.set_xy(43, y_atual + 1)
        self.cell(70, 6, titulo)

        self.set_xy(115, y_atual + 1)
        self.cell(55, 6, forn)

        self.set_font("Helvetica", "B", 7)
        self.set_xy(172, y_atual + 1)
        self.cell(28, 6, f"R$ {valor:,.0f}".replace(",", "X").replace(".", ",").replace("X", "."), align="R")


# ── Seções ────────────────────────────────────────────────────────────────────

def _secao_capa(pdf: _PDF, hoje: date) -> None:
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*_AZUL)
    pdf.ln(6)
    pdf.cell(0, 10, "SENTINELA RJ", ln=True, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(*_CINZA)
    pdf.cell(0, 7, "Relatorio de Monitoramento de Contratos Publicos", ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"Gerado em: {hoje.strftime('%d/%m/%Y')}  |  Fonte: PNCP", ln=True, align="C")
    pdf.set_text_color(*_PRETO)
    pdf.ln(4)


def _secao_kpis(pdf: _PDF, kpis: dict) -> None:
    pdf._titulo_secao("Visao Geral")

    valor_fmt = f"R$ {kpis['valor_total']:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    y = pdf.get_y()
    pdf._kpi_box("Total de Contratos",   str(kpis["contratos_total"]), 10,  y, 57)
    pdf._kpi_box("Valor Monitorado",     valor_fmt,                    72,  y, 68)
    pdf._kpi_box("Alertas Abertos",      str(kpis["alertas_abertos"]), 145, y, 55)
    pdf.ln(26)


def _secao_alertas(pdf: _PDF, alertas: list[dict]) -> None:
    pdf._titulo_secao(f"Top {len(alertas)} Alertas - Alta Severidade")

    if not alertas:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 7, "Nenhum alerta de alta severidade encontrado.", ln=True)
        pdf.ln(3)
        return

    # cabecalho da tabela
    y = pdf.get_y()
    pdf.set_fill_color(*_AZUL)
    pdf.rect(10, y, 190, 7, "F")
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*_BRANCO)
    pdf.set_xy(10, y + 1)
    pdf.cell(8,  5, "#",        align="C")
    pdf.cell(15, 5, "Sev.",     align="C")
    pdf.cell(35, 5, "Tipo")
    pdf.cell(95, 5, "Descricao")
    pdf.cell(30, 5, "Valor",    align="R")
    pdf.set_text_color(*_PRETO)
    pdf.ln(8)

    for i, row in enumerate(alertas, 1):
        if pdf.get_y() > 265:
            pdf.add_page()
        y0 = pdf.get_y()
        row_h = pdf._row_alerta(i, row, y0)
        pdf.set_y(y0 + row_h)

    pdf.ln(4)


def _secao_casos(pdf: _PDF, casos: list[dict]) -> None:
    pdf._titulo_secao("Casos Investigados")

    if not casos:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 7, "Nenhum caso registrado.", ln=True)
        pdf.ln(3)
        return

    # cabecalho
    y = pdf.get_y()
    pdf.set_fill_color(*_AZUL)
    pdf.rect(10, y, 190, 7, "F")
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*_BRANCO)
    pdf.set_xy(10, y + 1)
    pdf.cell(8,  5, "#",        align="C")
    pdf.cell(22, 5, "Status",   align="C")
    pdf.cell(72, 5, "Titulo")
    pdf.cell(58, 5, "Fornecedor")
    pdf.cell(28, 5, "Valor",    align="R")
    pdf.set_text_color(*_PRETO)
    pdf.ln(8)

    for i, caso in enumerate(casos, 1):
        if pdf.get_y() > 265:
            pdf.add_page()
        pdf._row_caso(i, caso, pdf.get_y())
        pdf.ln(8)

        # resumo em linha seguinte se houver
        resumo = _safe((caso.get("resumo") or "").strip(), 200)
        if resumo:
            pdf.set_font("Helvetica", "I", 7)
            pdf.set_text_color(*_CINZA)
            pdf.set_x(22)
            pdf.multi_cell(175, 4, resumo)
            pdf.set_text_color(*_PRETO)
            pdf.ln(1)

    pdf.ln(2)


# ── Ponto de entrada público ──────────────────────────────────────────────────

def gerar_pdf_bytes(conn: sqlite3.Connection) -> bytes:
    """Gera o relatório completo e retorna os bytes do PDF."""
    hoje = date.today()

    kpis    = _kpis(conn)
    alertas = _top_alertas(conn)
    casos   = _casos(conn)

    pdf = _PDF()
    _secao_capa(pdf, hoje)
    _secao_kpis(pdf, kpis)
    _secao_alertas(pdf, alertas)
    _secao_casos(pdf, casos)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
