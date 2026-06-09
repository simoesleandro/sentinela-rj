"""
Sentinela RJ — Extrator de contratos do PNCP.

Estrategia:
- Endpoint /contratos NAO filtra por municipio. Varremos por data de publicacao
  (Brasil inteiro, paginado) e filtramos no nosso lado por:
    * municipio_ibge == 3304557 (Rio de Janeiro)  -- onde o orgao fica
    * esfera_id == 'M'                              -- de quem e o dinheiro (Municipio)
- API e instavel: retry com backoff (ja vimos HTTP 500 intermitente).
- Encoding vem bagunçado; forcamos UTF-8 na resposta.
- Guardamos o raw_json para auditoria posterior.

Uso:
    python -m extrator.pncp                  # ultimos 3 meses (default)
    python -m extrator.pncp 20250101 20251231  # intervalo custom (AAAAMMDD)
"""
import os
import sys
import json
import time
from datetime import date, timedelta

import requests

from db.conexao import init_db
from extrator.config_municipio import municipio_esfera, municipio_ibge, rotulo_filtro

BASE = os.getenv("PNCP_BASE_URL", "https://pncp.gov.br/api/consulta/v1").strip()
TIMEOUT = int(os.getenv("PNCP_TIMEOUT", "60"))
TAM_PAGINA = int(os.getenv("PNCP_TAM_PAGINA", "500"))


# ----------------------------- HTTP resiliente -----------------------------

def _get(path, params, tentativas=8):
    url = f"{BASE}{path}"
    ultimo = None
    for i in range(tentativas):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT)
            if r.status_code == 200:
                r.encoding = "utf-8"
                try:
                    return r.json()
                except ValueError:
                    # API as vezes devolve HTML de erro com status 200
                    print(f"    JSONDecodeError (tentativa {i+1}/{tentativas})")
                    ultimo = "JSONDecodeError"
            elif r.status_code == 204:
                return None  # sem conteudo
            else:
                print(f"    HTTP {r.status_code} (tentativa {i+1}/{tentativas})")
                ultimo = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            print(f"    {type(e).__name__} (tentativa {i+1}/{tentativas})")
            ultimo = str(e)
        time.sleep(min(2 * (i + 1), 15))
    raise RuntimeError(f"Falhou apos {tentativas} tentativas: {ultimo}")


# ----------------------------- Persistência -----------------------------

def _upsert_orgao(conn, o, uni):
    if not o or not o.get("cnpj"):
        return
    conn.execute(
        """INSERT INTO orgaos (cnpj, razao_social, poder_id, esfera_id,
               municipio_nome, municipio_ibge, uf_sigla, atualizado_em)
           VALUES (?,?,?,?,?,?,?,datetime('now'))
           ON CONFLICT(cnpj) DO UPDATE SET
               razao_social=excluded.razao_social,
               atualizado_em=datetime('now')""",
        (o.get("cnpj"), o.get("razaoSocial"), o.get("poderId"), o.get("esferaId"),
         (uni or {}).get("municipioNome"), (uni or {}).get("codigoIbge"),
         (uni or {}).get("ufSigla")),
    )


def _upsert_fornecedor(conn, d):
    ni = d.get("niFornecedor")
    if not ni:
        return
    conn.execute(
        """INSERT INTO fornecedores (ni, tipo_pessoa, razao_social, atualizado_em)
           VALUES (?,?,?,datetime('now'))
           ON CONFLICT(ni) DO UPDATE SET
               razao_social=excluded.razao_social,
               atualizado_em=datetime('now')""",
        (ni, d.get("tipoPessoa"), d.get("nomeRazaoSocialFornecedor")),
    )


def _insert_contrato(conn, d):
    o = d.get("orgaoEntidade") or {}
    uni = d.get("unidadeOrgao") or {}
    tc = d.get("tipoContrato") or {}
    cp = d.get("categoriaProcesso") or {}
    conn.execute(
        """INSERT OR REPLACE INTO contratos (
            numero_controle_pncp, numero_controle_compra, ano_contrato,
            sequencial_contrato, tipo_contrato_id, tipo_contrato_nome,
            numero_contrato_empenho, processo, orgao_cnpj, fornecedor_ni,
            municipio_ibge, municipio_nome, uf_sigla, esfera_id, poder_id,
            unidade_nome, unidade_codigo, objeto, categoria_processo_id,
            categoria_processo_nome, informacao_complementar, valor_inicial,
            valor_global, valor_acumulado, valor_parcela, numero_parcelas,
            receita, data_assinatura, data_vigencia_inicio, data_vigencia_fim,
            data_publicacao_pncp, data_atualizacao, fruto_adesao,
            tem_remanejamento, numero_retificacao, emenda_parlamentar,
            identificador_cipi, url_cipi, raw_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            d.get("numeroControlePNCP"), d.get("numeroControlePncpCompra"),
            d.get("anoContrato"), d.get("sequencialContrato"),
            tc.get("id"), tc.get("nome"), d.get("numeroContratoEmpenho"),
            d.get("processo"), o.get("cnpj"), d.get("niFornecedor"),
            uni.get("codigoIbge"), uni.get("municipioNome"), uni.get("ufSigla"),
            o.get("esferaId"), o.get("poderId"), uni.get("nomeUnidade"),
            uni.get("codigoUnidade"), d.get("objetoContrato"),
            cp.get("id"), cp.get("nome"), d.get("informacaoComplementar"),
            d.get("valorInicial"), d.get("valorGlobal"), d.get("valorAcumulado"),
            d.get("valorParcela"), d.get("numeroParcelas"),
            1 if d.get("receita") else 0, d.get("dataAssinatura"),
            d.get("dataVigenciaInicio"), d.get("dataVigenciaFim"),
            d.get("dataPublicacaoPncp"), d.get("dataAtualizacao"),
            1 if d.get("frutoAdesao") else 0,
            1 if d.get("temRemanejamento") else 0, d.get("numeroRetificacao"),
            json.dumps(d.get("emendaParlamentar"), ensure_ascii=False) if d.get("emendaParlamentar") else None,
            d.get("identificadorCipi"), d.get("urlCipi"),
            json.dumps(d, ensure_ascii=False),
        ),
    )


def _e_do_municipio_alvo(d):
    uni = d.get("unidadeOrgao") or {}
    o = d.get("orgaoEntidade") or {}
    return (uni.get("codigoIbge") == municipio_ibge()) and (
        o.get("esferaId") == municipio_esfera()
    )


# ----------------------------- Coleta -----------------------------

def _coletar_janela(conn, data_inicial, data_final):
    """Coleta uma janela (idealmente <= 1 mes). Tolera falha de pagina isolada."""
    print(f"\n>>> Janela {data_inicial} a {data_final}")
    pagina = 1
    total_paginas = None
    brutos = 0
    salvos = 0
    paginas_falhas = []

    while total_paginas is None or pagina <= total_paginas:
        try:
            j = _get("/contratos", {
                "dataInicial": data_inicial,
                "dataFinal": data_final,
                "pagina": pagina,
                "tamanhoPagina": TAM_PAGINA,
            })
        except RuntimeError as e:
            print(f"  !! pagina {pagina} falhou definitivamente: {e}")
            paginas_falhas.append(pagina)
            pagina += 1
            continue

        if not j or not j.get("data"):
            break
        if total_paginas is None:
            total_paginas = j.get("totalPaginas")
            print(f"  Brasil: {j.get('totalRegistros')} contratos, {total_paginas} paginas")

        lote = j["data"]
        brutos += len(lote)
        do_municipio = [d for d in lote if _e_do_municipio_alvo(d)]
        for d in do_municipio:
            _upsert_orgao(conn, d.get("orgaoEntidade"), d.get("unidadeOrgao"))
            _upsert_fornecedor(conn, d)
            _insert_contrato(conn, d)
            salvos += 1
        conn.commit()

        if pagina % 50 == 0 or do_municipio:
            print(f"  pag {pagina}/{total_paginas} | municipio {len(do_municipio)} | acumulado janela {salvos}")
        pagina += 1
        time.sleep(0.3)

    if paginas_falhas:
        print(f"  ATENCAO: {len(paginas_falhas)} paginas falharam: {paginas_falhas[:20]}")
    print(f"  Janela ok: brutos {brutos} | salvos {salvos}")
    return brutos, salvos, pagina - 1, paginas_falhas


def _janelas_mensais(data_inicial, data_final):
    """Quebra [di, df] em fatias mensais (AAAAMMDD) para aliviar a API."""
    di = date(int(data_inicial[:4]), int(data_inicial[4:6]), int(data_inicial[6:8]))
    df = date(int(data_final[:4]), int(data_final[4:6]), int(data_final[6:8]))
    out = []
    ini = di
    while ini <= df:
        if ini.month == 12:
            prox = date(ini.year + 1, 1, 1)
        else:
            prox = date(ini.year, ini.month + 1, 1)
        fim = min(prox - timedelta(days=1), df)
        out.append((ini.strftime("%Y%m%d"), fim.strftime("%Y%m%d")))
        ini = prox
    return out


def coletar(data_inicial: str, data_final: str) -> dict:
    """Ponto de entrada público. Retorna sumário da coleta."""
    conn = init_db()
    print(f"Coletando contratos PNCP de {data_inicial} a {data_final}")
    print(f"Filtro: {rotulo_filtro()}")

    iniciado = time.strftime("%Y-%m-%d %H:%M:%S")
    janelas = _janelas_mensais(data_inicial, data_final)
    print(f"Dividido em {len(janelas)} janela(s) mensal(is): {janelas}")

    tot_brutos = tot_salvos = tot_paginas = 0
    todas_falhas = []
    for (di, df) in janelas:
        b, s, p, falhas = _coletar_janela(conn, di, df)
        tot_brutos += b
        tot_salvos += s
        tot_paginas += p
        todas_falhas += [f"{di}:{pg}" for pg in falhas]

    finalizado = time.strftime("%Y-%m-%d %H:%M:%S")
    obs = f"filtro {rotulo_filtro()}"
    if todas_falhas:
        obs += f" | paginas_falhas={len(todas_falhas)}"
    conn.execute(
        """INSERT INTO coletas_log (fonte, data_inicial, data_final, paginas_lidas,
               registros_brutos, registros_municipio, iniciado_em, finalizado_em, observacao)
           VALUES ('PNCP /contratos', ?,?,?,?,?,?,?,?)""",
        (data_inicial, data_final, tot_paginas, tot_brutos, tot_salvos, iniciado, finalizado, obs),
    )
    conn.commit()
    conn.close()

    sumario = {
        "data_inicial": data_inicial,
        "data_final": data_final,
        "brutos_varridos": tot_brutos,
        "salvos_rio": tot_salvos,
        "salvos_municipio": tot_salvos,
        "paginas_falhas": todas_falhas,
    }
    print(f"\n=== Coleta concluida ===")
    print(f"Brutos varridos: {tot_brutos} | Salvos (municipio alvo): {tot_salvos}")
    if todas_falhas:
        print(f"Paginas que falharam: {todas_falhas}")
    return sumario


def _ultimos_3_meses():
    hoje = date.today()
    inicio = hoje - timedelta(days=90)
    return inicio.strftime("%Y%m%d"), hoje.strftime("%Y%m%d")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        di, df = sys.argv[1], sys.argv[2]
    else:
        di, df = _ultimos_3_meses()
    coletar(di, df)
