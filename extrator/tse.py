"""Extrator de doações de campanha do TSE — Sentinela RJ.

Fonte: prestação de contas eleitorais de candidatos (dados abertos do TSE). O
arquivo nacional de receitas é um zip de ~1,2 GB com um CSV por UF dentro; em
vez de baixá-lo inteiro, lemos o índice do zip remoto por HTTP range e
extraímos APENAS o CSV da UF de interesse (RJ ≈ 66 MB expandido).

Por que só pessoa física importa: doação de EMPRESA para campanha é proibida
desde 2015 (Lei 13.165/2015 + ADI 4650/STF). Medido em jul/2026 sobre o RJ
2024: só 531 CNPJs "doadores" no estado inteiro, todos comitês/transferências
partidárias — o cruzamento clássico "empresa doou para quem a contrata" não
existe mais no Brasil. O valor está no doador pessoa física (25.428 no RJ), em
especial sócios-administradores de fornecedores.

Bônus que fecha identidade: a prestação de contas traz o CPF COMPLETO do doador
(público). Quando o nome de um sócio (QSA) bate com um doador e os 6 dígitos do
meio do CPF mascarado do QSA (``***MMMMMM**``) conferem com o CPF completo do
doador, a identidade do sócio fica confirmada com base documental — resolvendo
a lacuna "sem CPF" do conflito de interesse. Ver analisador/doacoes.py.

Uso:
    python __main__.py tse                 # RJ, eleição 2024 (padrão)
    python __main__.py tse --ano 2024 --uf RJ
"""
from __future__ import annotations

import csv
import re
import sqlite3
import tempfile
import unicodedata
from pathlib import Path

# CSV do TSE é enorme por linha (60 colunas, descrições longas)
csv.field_size_limit(10_000_000)

# Zip nacional de receitas de candidatos (um CSV por UF dentro).
_URL_RECEITAS = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/"
    "prestacao_de_contas_eleitorais_candidatos_{ano}.zip"
)
_ARQUIVO_UF = "receitas_candidatos_{ano}_{uf}.csv"

_PREPOSICOES = {"DE", "DA", "DO", "DOS", "DAS", "E"}


def normalizar_nome(nome: str | None) -> str:
    """Upper-case, sem acento, sem preposições soltas, espaços colapsados.

    Mesma família de normalização do match sócio×servidor
    (conflito_interesse.normalizador) — replicada aqui para o extrator ficar
    autônomo. O que garante o match não é o nome (permissivo de propósito) e
    sim a confirmação pelos 6 dígitos do CPF, feita no detector.
    """
    sem_acento = (
        unicodedata.normalize("NFKD", nome or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    limpo = re.sub(r"[^A-Za-z ]", " ", sem_acento.upper())
    tokens = [t for t in limpo.split() if t not in _PREPOSICOES]
    return " ".join(tokens)


def _valor_br(v: str | None) -> float:
    """'1.500,00' -> 1500.0 (formato monetário BR do TSE)."""
    if not v:
        return 0.0
    v = v.strip().replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return 0.0


def _data_iso(v: str | None) -> str | None:
    """'27/08/2024' -> '2024-08-27'."""
    if not v:
        return None
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", v.strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def baixar_receitas_uf(ano: int, uf: str, destino: Path) -> Path:
    """Extrai só o CSV de receitas da UF do zip remoto, via HTTP range.

    Usa remotezip: lê o índice do zip sem baixar o arquivo inteiro (~1,2 GB) e
    puxa apenas a entrada da UF (RJ ≈ 8 MB comprimido). Retorna o caminho do
    CSV extraído em `destino`.
    """
    from remotezip import RemoteZip

    nome = _ARQUIVO_UF.format(ano=ano, uf=uf.upper())
    url = _URL_RECEITAS.format(ano=ano)
    with RemoteZip(url) as z:
        if nome not in z.namelist():
            raise FileNotFoundError(
                f"'{nome}' não encontrado no zip do TSE ({ano}). "
                f"Confira ano/UF."
            )
        z.extract(nome, destino)
    return destino / nome


def ingerir_receitas(conn: sqlite3.Connection, csv_path: Path, ano: int, uf: str) -> dict:
    """Ingere doações de PESSOA FÍSICA do CSV de receitas na doacoes_campanha.

    Idempotente por SQ_RECEITA (id da receita no TSE). Ignora doadores PJ
    (14 dígitos): não há doação legal de empresa desde 2015.
    """
    inseridas = 0
    lidas = 0
    pj_ignoradas = 0
    lote: list[tuple] = []

    with open(csv_path, encoding="latin-1", newline="") as fh:
        leitor = csv.DictReader(fh, delimiter=";")
        for row in leitor:
            lidas += 1
            doc = (row.get("NR_CPF_CNPJ_DOADOR") or "").strip()
            if not doc.isdigit():
                continue
            if len(doc) == 14:
                pj_ignoradas += 1
                continue
            if len(doc) != 11:
                continue
            nome_doador = (row.get("NM_DOADOR") or "").strip()
            lote.append((
                ano,
                uf.upper(),
                (row.get("NM_UE") or "").strip() or None,
                (row.get("DS_CARGO") or "").strip() or None,
                (row.get("NM_CANDIDATO") or "").strip() or None,
                (row.get("SQ_CANDIDATO") or "").strip() or None,
                (row.get("SG_PARTIDO") or "").strip() or None,
                doc,
                nome_doador or None,
                normalizar_nome(nome_doador),
                _valor_br(row.get("VR_RECEITA")),
                _data_iso(row.get("DT_RECEITA")),
                (row.get("SQ_RECEITA") or "").strip() or None,
            ))
            if len(lote) >= 2000:
                inseridas += _gravar_lote(conn, lote)
                lote.clear()

    if lote:
        inseridas += _gravar_lote(conn, lote)
    conn.commit()
    return {
        "linhas_lidas": lidas,
        "doacoes_pf_inseridas": inseridas,
        "pj_ignoradas": pj_ignoradas,
    }


def _gravar_lote(conn: sqlite3.Connection, lote: list[tuple]) -> int:
    cur = conn.executemany(
        """
        INSERT INTO doacoes_campanha (
            ano_eleicao, uf, municipio_ue, cargo, candidato_nome, candidato_sq,
            partido, doador_cpf, doador_nome, doador_nome_norm, valor,
            data_receita, sq_receita
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(sq_receita) DO NOTHING
        """,
        lote,
    )
    return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


def sincronizar_tse(
    conn: sqlite3.Connection, *, ano: int = 2024, uf: str = "RJ"
) -> dict:
    """Baixa (só a UF, via range) e ingere as receitas de campanha do TSE."""
    with tempfile.TemporaryDirectory(prefix="tse_") as tmp:
        csv_path = baixar_receitas_uf(ano, uf, Path(tmp))
        resumo = ingerir_receitas(conn, csv_path, ano, uf)
    resumo["ano"] = ano
    resumo["uf"] = uf.upper()
    return resumo
