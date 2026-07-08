"""Cruzamento lotação do servidor × órgão contratante do fornecedor.

O PNCP registra todos os contratos da PCRJ sob o órgão genérico "MUNICIPIO DE
RIO DE JANEIRO" — zero granularidade de secretaria. A granularidade real está
no campo ``processo`` do contrato, cujo prefixo identifica o órgão de origem
(``SMS-PRO-2024/...`` = Saúde, ``SME-PRO-...`` = Educação, ``GM-PRO-...`` =
Guarda Municipal etc., medido em jul/2026 sobre 4.931 contratos com processo).

Do lado do servidor, a folha traz ``sigla_ua`` hierárquica ("S/SUBPAV/CAP-3.3",
"GM/IG/DOP/...", "RS/PRE/NG-HMRG") cuja raiz identifica o órgão de lotação.

Este módulo mapeia os dois vocabulários. O sinal resultante é o mais forte do
domínio: a Lei 14.133/2021 (art. 14) impede de disputar licitação quem mantém
vínculo com o órgão contratante — sócio-servidor lotado no MESMO órgão que
contratou a empresa não é "mais um homônimo possível", é o caso central.

Limitações conhecidas (documentadas de propósito):
- COMLURB, RIOTUR, RIOCENTRO, RIO-URBE: empresas públicas cujas compras não
  aparecem no recorte municipal do PNCP coletado — sem lado de contrato para
  cruzar (COMLURB sozinha é o maior grupo de candidatos).
- FUNPREVI (X): servidor aposentado — sem lotação atual, o sinal não se aplica.
- O mapa é deliberadamente conservador: raiz de sigla fora do dicionário não
  cruza (sem chute), e ausência de match NÃO enfraquece o candidato.
"""
from __future__ import annotations

import re
import sqlite3

# raiz da sigla_ua (antes da primeira "/") → prefixos de processo do órgão.
# Só entradas defensáveis com os dados reais; ambíguas ficam de fora.
MAPA_LOTACAO_ORGAO: dict[str, frozenset[str]] = {
    # Saúde: S/ = Secretaria (SMS), RS/ = RioSaúde (rede hospitalar municipal,
    # processos RSU-; hospitais são financiados por contratos SMS)
    "S": frozenset({"SMS"}),
    "SMS": frozenset({"SMS"}),
    "RS": frozenset({"SMS", "RSU"}),
    # Educação
    "E": frozenset({"SME"}),
    "SME": frozenset({"SME"}),
    # Guarda Municipal
    "GM": frozenset({"GM"}),
    # Fazenda
    "F": frozenset({"SMF"}),
    "SMF": frozenset({"SMF"}),
    # Casa Civil
    "CVL": frozenset({"CVL"}),
    # Procuradoria
    "PG": frozenset({"PGM"}),
    "PGM": frozenset({"PGM"}),
    # Fundação Parques e Jardins
    "FPJ": frozenset({"FPJ"}),
    # Assistência Social
    "AS": frozenset({"ASS"}),
    # Cultura
    "SMC": frozenset({"SMC"}),
    # Administração
    "SMA": frozenset({"SMA"}),
    # Controladoria
    "CGM": frozenset({"CGM"}),
    # Instituto Pereira Passos
    "IPP": frozenset({"IPP"}),
    # Empresas públicas com processo próprio no PNCP municipal
    "CET-RIO": frozenset({"CET"}),
    "IPLANRIO": frozenset({"IPL"}),
    "RIOLUZ": frozenset({"LUZ"}),
}

_RE_PREFIXO_PROCESSO = re.compile(r"^([A-Z]{2,15})-")


def raiz_sigla_ua(sigla_ua: str | None) -> str | None:
    """Raiz do órgão de lotação, ou None quando o sinal não se aplica
    (sem sigla, aposentado FUNPREVI, "A DISPOSIÇÃO"...)."""
    if not sigla_ua:
        return None
    raiz = sigla_ua.strip().upper().split("/", 1)[0].strip()
    if not raiz or raiz.startswith("FUNPREVI"):
        return None
    return raiz


def prefixo_processo(processo: str | None) -> str | None:
    """Prefixo de órgão do número de processo ('SMS-PRO-2024/...' → 'SMS')."""
    if not processo:
        return None
    m = _RE_PREFIXO_PROCESSO.match(processo.strip().upper())
    return m.group(1) if m else None


def prefixos_processo_fornecedor(conn: sqlite3.Connection, fornecedor_ni: str) -> frozenset[str]:
    """Prefixos de órgão distintos dos processos de TODOS os contratos do
    fornecedor (mesma convenção valor > 0 do resto do domínio)."""
    rows = conn.execute(
        "SELECT DISTINCT processo FROM contratos "
        "WHERE fornecedor_ni = ? AND valor_global > 0 AND processo IS NOT NULL",
        (fornecedor_ni,),
    ).fetchall()
    prefixos = {prefixo_processo(r[0]) for r in rows}
    prefixos.discard(None)
    return frozenset(prefixos)  # type: ignore[arg-type]


def lotacao_bate_orgao(sigla_ua: str | None, prefixos_contratos: frozenset[str]) -> bool:
    """True quando o órgão de lotação do servidor aparece entre os órgãos de
    origem dos processos dos contratos do fornecedor."""
    raiz = raiz_sigla_ua(sigla_ua)
    if raiz is None or not prefixos_contratos:
        return False
    orgaos_lotacao = MAPA_LOTACAO_ORGAO.get(raiz)
    if not orgaos_lotacao:
        return False
    return bool(orgaos_lotacao & prefixos_contratos)
