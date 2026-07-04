"""Parser de arquivos CSV de folha de pagamento da PCRJ (portal contrachequeapi.rio.gov.br).

Formato fonte: ArquivoTC{AAAAMM}.csv, encoding latin-1, delimitador ';', decimais em
formato brasileiro (vírgula). A competência não existe como coluna — vem do nome do arquivo.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_NOME_ARQUIVO_RE = re.compile(r"ArquivoTC(\d{4})(\d{2})\.csv$", re.IGNORECASE)


@dataclass
class RegistroFolha:
    nome: str
    matricula: str
    sigla_ua: str
    tipo_folha: str
    competencia: date
    remuneracao_bruta: float | None
    desconto_previdencia: float | None
    desconto_ir: float | None
    outros_descontos: float | None
    desconto_excedente_teto: float | None
    remuneracao_liquida: float | None


def _extrair_competencia(caminho: Path) -> date:
    m = _NOME_ARQUIVO_RE.search(caminho.name)
    if not m:
        raise ValueError(
            f"Nome de arquivo inválido, esperado ArquivoTC{{AAAAMM}}.csv: {caminho.name}"
        )
    ano, mes = int(m.group(1)), int(m.group(2))
    return date(ano, mes, 1)


def _decimal_br(valor: str | None) -> float | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    return float(valor.replace(".", "").replace(",", "."))


class PayrollCSVParser:
    """Lê um CSV de folha de pagamento da PCRJ e retorna registros validados.

    Não conhece banco de dados — apenas parsing e conversão de tipos.
    """

    def __init__(self, caminho: str | Path):
        self._caminho = Path(caminho)

    def parse(self) -> list[RegistroFolha]:
        competencia = _extrair_competencia(self._caminho)
        registros: list[RegistroFolha] = []
        with self._caminho.open(encoding="latin-1", newline="") as f:
            leitor = csv.DictReader(f, delimiter=";")
            for linha in leitor:
                registros.append(
                    RegistroFolha(
                        nome=linha["NOME"].strip(),
                        matricula=linha["MATRICULA"].strip(),
                        sigla_ua=linha["SIGLA_UA"].strip(),
                        tipo_folha=linha["TIPO_FOLHA"].strip(),
                        competencia=competencia,
                        remuneracao_bruta=_decimal_br(linha["REMUNERAÇÃO BRUTA"]),
                        desconto_previdencia=_decimal_br(linha["DESCONTOS DE PREVIDÊNCIA"]),
                        desconto_ir=_decimal_br(linha["DESCONTOS DE IR"]),
                        outros_descontos=_decimal_br(linha["OUTROS DESCONTOS"]),
                        desconto_excedente_teto=_decimal_br(linha["DESCONTOS EXCEDENTE DE TETO"]),
                        remuneracao_liquida=_decimal_br(linha["REMUNERAÇÃO LÍQUIDA"]),
                    )
                )
        return registros
