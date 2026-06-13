"""Sentinela RJ — Dossiê investigativo exportável por alerta."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from analise.labels import icon_severidade, label_severidade, label_tipo
from db.conexao import DB_PATH

DIR_RELATORIOS = Path(__file__).resolve().parent
_LIMITE_CORRELATOS = 10
_PNCP_URL = "https://pncp.gov.br/app/contratos/{pncp_id}"

_SQL_ALERTA = """
SELECT a.id, a.tipo, a.severidade, a.score, a.descricao, a.metodologia,
       a.valor_referencia, a.status, a.criado_em, a.narrativa_ia,
       a.numero_controle_pncp,
       c.objeto, c.valor_global, c.valor_inicial, c.data_assinatura,
       c.data_vigencia_inicio, c.data_vigencia_fim,
       c.categoria_processo_nome, c.informacao_complementar,
       c.numero_contrato_empenho, c.fornecedor_ni,
       f.ni AS fornecedor_ni, f.razao_social AS fornecedor_nome,
       f.tipo_pessoa, f.tem_sancao,
       o.cnpj AS orgao_cnpj, o.razao_social AS orgao_nome, o.municipio_nome
FROM alertas a
LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
WHERE a.id = ?
"""

_SQL_CORRELATOS = """
SELECT a.id, a.tipo, a.severidade, a.score, a.valor_referencia, a.descricao,
       a.numero_controle_pncp
FROM alertas a
LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
WHERE a.id != ?
  AND (
    c.fornecedor_ni = ?
    OR a.tipo = ?
  )
ORDER BY a.score DESC, a.valor_referencia DESC
LIMIT ?
"""

_SQL_CADASTRO = """
SELECT situacao_cadastral, descricao_situacao, data_inicio_atividade,
       capital_social, porte, natureza_juridica, socios, municipio, uf,
       cnae_fiscal_descricao, atualizado_em
FROM fornecedor_cadastro
WHERE fornecedor_ni = ?
"""


class DossieNaoEncontradoError(LookupError):
    """Alerta inexistente no banco."""


class DossieAlerta(TypedDict, total=False):
    meta: dict[str, Any]
    alerta: dict[str, Any]
    contrato: dict[str, Any]
    fornecedor: dict[str, Any]
    orgao: dict[str, Any]
    cadastro: dict[str, Any] | None
    correlatos: list[dict[str, Any]]
    investigacao: dict[str, Any] | None


def _row_para_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


def _formatar_moeda(valor: float | None) -> str:
    if valor is None:
        return "—"
    return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _barra_score(score: float | None) -> str:
    if score is None:
        return "—"
    s = max(0.0, min(1.0, float(score)))
    filled = round(s * 20)
    return "█" * filled + "░" * (20 - filled) + f" {s * 100:.0f}%"


def _tem_narrativa(texto: Any) -> bool:
    return bool(str(texto or "").strip())


def _buscar_alerta(conn: sqlite3.Connection, alerta_id: int) -> dict[str, Any]:
    row = conn.execute(_SQL_ALERTA, (alerta_id,)).fetchone()
    if row is None:
        raise DossieNaoEncontradoError(f"Alerta não encontrado: id={alerta_id}")
    return _row_para_dict(row)


def _buscar_cadastro(conn: sqlite3.Connection, fornecedor_ni: str | None) -> dict[str, Any] | None:
    if not fornecedor_ni:
        return None
    row = conn.execute(_SQL_CADASTRO, (fornecedor_ni,)).fetchone()
    if row is None:
        return None
    dados = _row_para_dict(row)
    try:
        dados["socios"] = json.loads(dados.get("socios") or "[]")
    except json.JSONDecodeError:
        dados["socios"] = []
    return dados


def _buscar_correlatos(
    conn: sqlite3.Connection,
    alerta_id: int,
    fornecedor_ni: str | None,
    tipo: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        _SQL_CORRELATOS,
        (alerta_id, fornecedor_ni, tipo, _LIMITE_CORRELATOS),
    ).fetchall()
    return [_row_para_dict(r) for r in rows]


def carregar_dossie(conn: sqlite3.Connection, alerta_id: int) -> DossieAlerta:
    linha = _buscar_alerta(conn, alerta_id)
    fornecedor_ni = linha.get("fornecedor_ni")
    tipo = str(linha.get("tipo") or "")
    score = linha.get("score")
    return {
        "meta": {
            "alerta_id": alerta_id,
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "fonte": "Sentinela RJ / PNCP",
        },
        "alerta": {
            "id": linha["id"],
            "tipo": tipo,
            "tipo_label": label_tipo(tipo),
            "severidade": linha.get("severidade"),
            "severidade_label": label_severidade(str(linha.get("severidade") or "")),
            "score": score,
            "descricao": linha.get("descricao"),
            "metodologia": linha.get("metodologia"),
            "valor_referencia": linha.get("valor_referencia"),
            "status": linha.get("status"),
            "criado_em": linha.get("criado_em"),
            "narrativa_ia": linha.get("narrativa_ia"),
        },
        "contrato": {
            "numero_controle_pncp": linha.get("numero_controle_pncp"),
            "objeto": linha.get("objeto"),
            "valor_global": linha.get("valor_global"),
            "valor_inicial": linha.get("valor_inicial"),
            "data_assinatura": linha.get("data_assinatura"),
            "data_vigencia_inicio": linha.get("data_vigencia_inicio"),
            "data_vigencia_fim": linha.get("data_vigencia_fim"),
            "categoria_processo_nome": linha.get("categoria_processo_nome"),
            "informacao_complementar": linha.get("informacao_complementar"),
            "numero_contrato_empenho": linha.get("numero_contrato_empenho"),
            "url_pncp": (
                _PNCP_URL.format(pncp_id=linha["numero_controle_pncp"])
                if linha.get("numero_controle_pncp")
                else None
            ),
        },
        "fornecedor": {
            "ni": fornecedor_ni,
            "razao_social": linha.get("fornecedor_nome"),
            "tipo_pessoa": linha.get("tipo_pessoa"),
            "tem_sancao": bool(linha.get("tem_sancao")),
        },
        "orgao": {
            "cnpj": linha.get("orgao_cnpj"),
            "razao_social": linha.get("orgao_nome"),
            "municipio_nome": linha.get("municipio_nome"),
        },
        "cadastro": _buscar_cadastro(conn, fornecedor_ni),
        "correlatos": _buscar_correlatos(conn, alerta_id, fornecedor_ni, tipo),
        "investigacao": _buscar_investigacao(conn, alerta_id),
    }


def _buscar_investigacao(
    conn: sqlite3.Connection,
    alerta_id: int,
) -> dict[str, Any] | None:
    try:
        row = conn.execute(
            "SELECT * FROM investigacoes WHERE alerta_id = ? ORDER BY id DESC LIMIT 1",
            (alerta_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return _row_para_dict(row) if row else None


def garantir_narrativa_ia(
    dados: DossieAlerta,
    *,
    gerar: bool,
    db_path: Path | None = None,
) -> str:
    alerta = dados["alerta"]
    existente = str(alerta.get("narrativa_ia") or "")
    if _tem_narrativa(existente):
        return existente.strip()
    if not gerar:
        return ""
    from analise.motor_ia import InvestigadorIA
    from db.database import GerenciadorBanco

    payload = {**alerta, **dados.get("contrato", {}), **dados.get("fornecedor", {})}
    resultado = InvestigadorIA().investigar_anomalia(payload)
    caminho = db_path or DB_PATH
    GerenciadorBanco(db_path=caminho).atualizar_narrativa_anomalia(
        int(alerta["id"]),
        resultado.narrativa_ia,
        narrativa_gemma=resultado.narrativa_gemma,
        gemma_utilizado=1 if resultado.narrativa_gemma else 0,
    )
    alerta["narrativa_ia"] = resultado.narrativa_ia
    return resultado.narrativa_ia


def _secao_cabecalho(dados: DossieAlerta) -> str:
    a = dados["alerta"]
    sev = str(a.get("severidade") or "")
    return "\n".join([
        f"# DOSSIÊ INVESTIGATIVO — ALERTA #{a['id']}",
        "",
        f"**Gerado em:** {dados['meta']['gerado_em']}  ",
        f"**Fonte:** {dados['meta']['fonte']}  ",
        f"**Status:** `{a.get('status', 'aberto')}`  ",
        f"**Severidade:** {icon_severidade(sev)} {label_severidade(sev)}  ",
        f"**Score:** `{_barra_score(a.get('score'))}`  ",
        "",
        "---",
        "",
    ])


def _secao_alerta(dados: DossieAlerta) -> str:
    a = dados["alerta"]
    return "\n".join([
        "## Hipótese Estatística",
        "",
        f"**Tipo:** {a.get('tipo_label')} (`{a.get('tipo')}`)  ",
        f"**Valor em análise:** {_formatar_moeda(a.get('valor_referencia'))}  ",
        f"**Registrado em:** {a.get('criado_em') or '—'}  ",
        "",
        a.get("descricao") or "*Sem descrição.*",
        "",
        f"**Metodologia:** {a.get('metodologia') or '—'}",
        "",
        "---",
        "",
    ])


def _secao_contrato(dados: DossieAlerta) -> str:
    c = dados["contrato"]
    if not c.get("numero_controle_pncp"):
        return "## Contrato Vinculado\n\n*Nenhum contrato PNCP associado a este alerta.*\n\n---\n\n"
    link = c.get("url_pncp") or "—"
    return "\n".join([
        "## Contrato Vinculado",
        "",
        f"**PNCP:** `{c['numero_controle_pncp']}`  ",
        f"**Link:** {link}  ",
        f"**Empenho:** {c.get('numero_contrato_empenho') or '—'}  ",
        f"**Categoria:** {c.get('categoria_processo_nome') or '—'}  ",
        f"**Valor global:** {_formatar_moeda(c.get('valor_global'))}  ",
        f"**Assinatura:** {c.get('data_assinatura') or '—'} → {c.get('data_vigencia_fim') or '—'}  ",
        "",
        "**Objeto:**",
        "",
        c.get("objeto") or "*Não informado.*",
        "",
        "---",
        "",
    ])


def _secao_partes(dados: DossieAlerta) -> str:
    f = dados["fornecedor"]
    o = dados["orgao"]
    sancao = "Sim" if f.get("tem_sancao") else "Não"
    return "\n".join([
        "## Partes",
        "",
        "| Papel | Identificador | Nome |",
        "|-------|---------------|------|",
        f"| Órgão | `{o.get('cnpj') or '—'}` | {o.get('razao_social') or '—'} |",
        f"| Fornecedor | `{f.get('ni') or '—'}` | {f.get('razao_social') or '—'} |",
        "",
        f"**Tipo pessoa:** {f.get('tipo_pessoa') or '—'}  ",
        f"**Flag sanção cadastral:** {sancao}  ",
        "",
        "---",
        "",
    ])


def _secao_cadastro(dados: DossieAlerta) -> str:
    cad = dados.get("cadastro")
    if not cad:
        return "## Cadastro BrasilAPI\n\n*Dados cadastrais não disponíveis. Execute `enriquecer`.*\n\n---\n\n"
    socios = cad.get("socios") or []
    linhas_soc = [f"- {s.get('nome', s)}" if isinstance(s, dict) else f"- {s}" for s in socios[:8]]
    bloco_socios = "\n".join(linhas_soc) if linhas_soc else "*QSA não informado.*"
    return "\n".join([
        "## Cadastro BrasilAPI",
        "",
        f"**Situação:** {cad.get('descricao_situacao') or cad.get('situacao_cadastral') or '—'}  ",
        f"**Capital social:** {_formatar_moeda(cad.get('capital_social'))}  ",
        f"**Porte:** {cad.get('porte') or '—'}  ",
        f"**Início atividade:** {cad.get('data_inicio_atividade') or '—'}  ",
        "",
        "**Quadro societário (amostra):**",
        "",
        bloco_socios,
        "",
        "---",
        "",
    ])


def _secao_correlatos(dados: DossieAlerta) -> str:
    itens = dados.get("correlatos") or []
    if not itens:
        return "## Alertas Correlatos\n\n*Nenhum alerta correlato encontrado.*\n\n---\n\n"
    linhas = [
        "| ID | Score | Sev. | Tipo | Valor |",
        "|---:|------:|------|------|------:|",
    ]
    for item in itens:
        linhas.append(
            f"| {item['id']} | {float(item.get('score') or 0):.3f} | "
            f"{icon_severidade(str(item.get('severidade') or ''))} | "
            f"{label_tipo(str(item.get('tipo') or ''))} | "
            f"{_formatar_moeda(item.get('valor_referencia'))} |"
        )
    return "\n".join(["## Alertas Correlatos", ""] + linhas + ["", "---", ""])


def _secao_investigacao_profunda(dados: DossieAlerta) -> str:
    inv = dados.get("investigacao")
    if not inv:
        return ""
    linhas = [
        "## Investigação Profunda",
        "",
        f"**Status:** {inv.get('status', '—')}  ",
        f"**Conclusão:** {inv.get('conclusao', '—')}  ",
        f"**Grau de confiança:** {inv.get('grau_confianca', '—')}  ",
        f"**Recomendação:** {inv.get('recomendacao', '—')}",
        "",
        "### Síntese do Agente",
        "",
        str(inv.get("sintese") or ""),
        "",
        "---",
        "",
    ]
    return "\n".join(linhas)


def _secao_veredito_ia(narrativa: str) -> str:
    if not narrativa.strip():
        return "## Veredito IA\n\n*Narrativa não gerada. Use `--gerar-ia` ou `?gerar_ia=true`.*\n"
    return "\n".join([
        "## Veredito IA",
        "",
        narrativa.strip(),
        "",
        "---",
        "",
        "*Narrativa gerada por InvestigadorIA (Ollama llama3.1 local por padrão).*",
    ])


def renderizar_markdown(dados: DossieAlerta) -> str:
    narrativa = str(dados["alerta"].get("narrativa_ia") or "")
    partes = [
        _secao_cabecalho(dados),
        _secao_alerta(dados),
        _secao_contrato(dados),
        _secao_partes(dados),
        _secao_cadastro(dados),
        _secao_correlatos(dados),
        _secao_investigacao_profunda(dados),
        _secao_veredito_ia(narrativa),
    ]
    return "\n".join(partes)


def renderizar_pdf(dados: DossieAlerta) -> bytes:
    """Exporta dossiê como PDF (texto plano a partir do Markdown)."""
    from fpdf import FPDF

    texto = renderizar_markdown(dados)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    largura = pdf.epw
    for linha in texto.splitlines():
        seguro = (
            linha.replace("—", "-")
            .encode("latin-1", errors="replace")
            .decode("latin-1")
        )
        pdf.multi_cell(largura, 4.5, seguro)
    out = pdf.output()
    if isinstance(out, bytes):
        return out
    if isinstance(out, bytearray):
        return bytes(out)
    return str(out).encode("latin-1")


def serializar_json(dados: DossieAlerta) -> dict[str, Any]:
    return dict(dados)


def obter_dossie(
    conn: sqlite3.Connection,
    alerta_id: int,
    *,
    gerar_ia: bool = False,
    db_path: Path | None = None,
) -> DossieAlerta:
    dados = carregar_dossie(conn, alerta_id)
    garantir_narrativa_ia(dados, gerar=gerar_ia, db_path=db_path)
    return dados


def exportar_dossie(
    conn: sqlite3.Connection,
    alerta_id: int,
    dir_saida: Path | None = None,
    *,
    gerar_ia: bool = False,
    formato: str = "md",
    db_path: Path | None = None,
) -> Path:
    dados = obter_dossie(conn, alerta_id, gerar_ia=gerar_ia, db_path=db_path)
    destino = dir_saida or DIR_RELATORIOS
    destino.mkdir(parents=True, exist_ok=True)
    hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if formato.lower() == "json":
        caminho = destino / f"dossie_alerta_{alerta_id}_{hoje}.json"
        caminho.write_text(
            json.dumps(serializar_json(dados), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return caminho
    if formato.lower() == "pdf":
        caminho = destino / f"dossie_alerta_{alerta_id}_{hoje}.pdf"
        caminho.write_bytes(renderizar_pdf(dados))
        return caminho
    caminho = destino / f"dossie_alerta_{alerta_id}_{hoje}.md"
    caminho.write_text(renderizar_markdown(dados), encoding="utf-8")
    return caminho
