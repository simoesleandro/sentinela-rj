"""Testes para folha_pagamento/parser.py."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from folha_pagamento.parser import PayrollCSVParser, _extrair_competencia


_CABECALHO = (
    "NOME;MATRICULA;SIGLA_UA;TIPO_FOLHA;REMUNERAÇÃO BRUTA;DESCONTOS DE PREVIDÊNCIA;"
    "DESCONTOS DE IR;OUTROS DESCONTOS;DESCONTOS EXCEDENTE DE TETO;REMUNERAÇÃO LÍQUIDA\n"
)


def _escrever_csv(tmp_path: Path, nome_arquivo: str, linhas: list[str]) -> Path:
    caminho = tmp_path / nome_arquivo
    conteudo = _CABECALHO + "\n".join(linhas)
    caminho.write_bytes(conteudo.encode("latin-1"))
    return caminho


def test_extrair_competencia_do_nome_arquivo():
    assert _extrair_competencia(Path("ArquivoTC202106.csv")) == date(2021, 6, 1)


def test_extrair_competencia_nome_invalido_levanta_erro():
    with pytest.raises(ValueError):
        _extrair_competencia(Path("folha_junho.csv"))


def test_parse_encoding_latin1_e_decimal_br(tmp_path: Path):
    linhas = [
        "MARIA DA SILVA;12345;SMS;NORMAL;3018,31;301,83;150,00;10,50;0,00;2555,98",
    ]
    caminho = _escrever_csv(tmp_path, "ArquivoTC202106.csv", linhas)

    registros = PayrollCSVParser(caminho).parse()

    assert len(registros) == 1
    r = registros[0]
    assert r.nome == "MARIA DA SILVA"
    assert r.matricula == "12345"
    assert r.sigla_ua == "SMS"
    assert r.tipo_folha == "NORMAL"
    assert r.competencia == date(2021, 6, 1)
    assert r.remuneracao_bruta == 3018.31
    assert r.desconto_previdencia == 301.83
    assert r.desconto_ir == 150.00
    assert r.outros_descontos == 10.50
    assert r.desconto_excedente_teto == 0.00
    assert r.remuneracao_liquida == 2555.98


def test_parse_decimal_br_com_separador_de_milhar(tmp_path: Path):
    linhas = [
        "JOÃO SOUZA;54321;SME;NORMAL;12345,67;;;;;12345,67",
    ]
    caminho = _escrever_csv(tmp_path, "ArquivoTC202107.csv", linhas)

    registros = PayrollCSVParser(caminho).parse()

    assert registros[0].remuneracao_bruta == 12345.67
    assert registros[0].desconto_previdencia is None


def test_parse_matricula_duplicada_tipos_folha_diferentes(tmp_path: Path):
    """Mesma matrícula em TIPO_FOLHA diferentes gera múltiplos registros, não erro."""
    linhas = [
        "MARIA DA SILVA;12345;SMS;NORMAL;3018,31;;;;;3018,31",
        "MARIA DA SILVA;12345;SMS;SUPLEMENTO;500,00;;;;;500,00",
        "MARIA DA SILVA;12345;SMS;FOLHA DE FERIAS;1000,00;;;;;1000,00",
    ]
    caminho = _escrever_csv(tmp_path, "ArquivoTC202106.csv", linhas)

    registros = PayrollCSVParser(caminho).parse()

    assert len(registros) == 3
    assert {r.tipo_folha for r in registros} == {"NORMAL", "SUPLEMENTO", "FOLHA DE FERIAS"}
    assert all(r.matricula == "12345" for r in registros)
