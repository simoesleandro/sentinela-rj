"""Configuração geográfica do monitoramento — zero hardcoding."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_PADRAO_IBGE = "3304557"
_PADRAO_ESFERA = "M"
_PADRAO_NOME = "Rio de Janeiro"

# Região Metropolitana e entorno — Rio como prioridade 1 (coleta principal).
_MUNICIPIOS_PADRAO_RM_RJ: tuple[tuple[str, str, int], ...] = (
    ("3304557", "Rio de Janeiro", 1),
    ("3303302", "Niterói", 2),
    ("3304904", "São Gonçalo", 2),
    ("3301702", "Duque de Caxias", 2),
    ("3303500", "Nova Iguaçu", 2),
    ("3301850", "Itaboraí", 3),
    ("3300456", "Belford Roxo", 3),
    ("3305109", "São João de Meriti", 3),
    ("3302270", "Nilópolis", 3),
    ("3304144", "Petrópolis", 3),
)

_NOMES_PADRAO = {ibge: nome for ibge, nome, _ in _MUNICIPIOS_PADRAO_RM_RJ}


@dataclass(frozen=True)
class MunicipioMonitorado:
    ibge: str
    nome: str
    esfera: str = _PADRAO_ESFERA
    prioridade: int = 2

    def rotulo(self) -> str:
        return f"{self.nome} (IBGE {self.ibge})"


def _parse_municipios_monitorados(raw: str) -> list[MunicipioMonitorado]:
    itens: list[MunicipioMonitorado] = []
    for parte in raw.split(","):
        trecho = parte.strip()
        if not trecho:
            continue
        if ":" in trecho:
            ibge, nome = trecho.split(":", 1)
            ibge, nome = ibge.strip(), nome.strip()
        else:
            ibge = trecho
            nome = _NOMES_PADRAO.get(ibge, f"Município {ibge}")
        if not ibge.isdigit():
            raise ValueError(f"IBGE inválido em MUNICIPIOS_MONITORADOS: '{trecho}'")
        prio = 1 if ibge == _PADRAO_IBGE else 2
        for p_ibge, p_nome, p_prio in _MUNICIPIOS_PADRAO_RM_RJ:
            if p_ibge == ibge:
                prio = p_prio
                if not nome or nome.startswith("Município "):
                    nome = p_nome
                break
        itens.append(
            MunicipioMonitorado(ibge=ibge, nome=nome, prioridade=prio),
        )
    if not itens:
        raise ValueError("MUNICIPIOS_MONITORADOS está vazio.")
    return sorted(itens, key=lambda m: (m.prioridade, m.nome))


def municipios_monitorados() -> list[MunicipioMonitorado]:
    """Lista de municípios na coleta automática (env ou padrão RM-RJ)."""
    raw = os.getenv("MUNICIPIOS_MONITORADOS", "").strip()
    if raw:
        return _parse_municipios_monitorados(raw)
    return [
        MunicipioMonitorado(ibge=ibge, nome=nome, prioridade=prio)
        for ibge, nome, prio in _MUNICIPIOS_PADRAO_RM_RJ
    ]


def municipio_principal() -> MunicipioMonitorado:
    return municipios_monitorados()[0]


def municipio_ibge() -> str:
    """IBGE do município principal (Rio por padrão) — compat legado."""
    override = os.getenv("MUNICIPIO_IBGE", "").strip()
    if override and not os.getenv("MUNICIPIOS_MONITORADOS", "").strip():
        return override
    return municipio_principal().ibge


def municipio_esfera() -> str:
    return os.getenv("MUNICIPIO_ESFERA", _PADRAO_ESFERA).strip().upper()


def municipio_nome() -> str:
    override = os.getenv("MUNICIPIO_NOME", "").strip()
    if override and not os.getenv("MUNICIPIOS_MONITORADOS", "").strip():
        return override
    return municipio_principal().nome


def rotulo_filtro() -> str:
    alvos = municipios_monitorados()
    if len(alvos) == 1:
        m = alvos[0]
        return f"IBGE {m.ibge} ({m.nome}) + esfera '{m.esfera}'"
    nomes = ", ".join(m.nome for m in alvos[:4])
    sufixo = f" +{len(alvos) - 4}" if len(alvos) > 4 else ""
    return f"{len(alvos)} municípios ({nomes}{sufixo}) · esfera '{municipio_esfera()}'"
