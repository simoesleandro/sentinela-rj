"""
Sentinela RJ — CLI principal.

Uso:
    python -m sentinela status
    python -m sentinela coletar [data_ini data_fim]
    python -m sentinela analisar [--dir DIR]
    python -m sentinela relatorio [--dir DIR]
    python -m sentinela painel
    python -m sentinela investigar

Executar a partir da raiz do projeto (onde fica este arquivo).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

# ── Helpers de saída ─────────────────────────────────────────────────────────

SEP = "-" * 56


def _header(titulo: str) -> None:
    print()
    print(SEP)
    print(f"  SENTINELA RJ  |  {titulo}")
    print(SEP)


def _ok(msg: str) -> None:
    print(f"  OK   {msg}")


def _info(msg: str) -> None:
    print(f"  ..   {msg}")


def _warn(msg: str) -> None:
    print(f"  !!   {msg}")


def _elapsed(t0: float) -> str:
    s = time.perf_counter() - t0
    return f"{s:.1f}s" if s >= 1 else f"{s*1000:.0f}ms"


# ── Sub-comando: status ───────────────────────────────────────────────────────

def cmd_status(_args) -> int:
    from db.conexao import get_conn, DB_PATH

    _header("status")

    if not DB_PATH.exists():
        _warn(f"Banco nao encontrado: {DB_PATH}")
        _warn("Execute primeiro: python -m sentinela coletar")
        print()
        return 1

    conn = get_conn(row_factory=True)
    c = conn.cursor()

    c.execute("""
        SELECT COUNT(*)                        AS n,
               COALESCE(SUM(valor_global), 0)  AS total,
               COUNT(DISTINCT fornecedor_ni)   AS n_forn,
               COUNT(DISTINCT orgao_cnpj)      AS n_orgaos,
               MIN(data_assinatura)            AS d_min,
               MAX(data_assinatura)            AS d_max
        FROM contratos WHERE valor_global > 0
    """)
    s = dict(c.fetchone())

    c.execute("SELECT COUNT(*) AS n FROM alertas WHERE status = 'aberto'")
    n_alertas = c.fetchone()["n"]

    c.execute("""
        SELECT finalizado_em, data_inicial, data_final, registros_municipio
        FROM coletas_log ORDER BY id DESC LIMIT 1
    """)
    ult = c.fetchone()

    conn.close()

    print(f"\n  Banco        : {DB_PATH}")
    print(f"  Contratos    : {s['n']}  |  R$ {s['total']:,.2f}")
    print(f"  Fornecedores : {s['n_forn']}  |  Orgaos: {s['n_orgaos']}")
    print(f"  Periodo      : {s['d_min']} -> {s['d_max']}")
    print()

    if ult and ult["finalizado_em"]:
        print(f"  Ultima coleta: {ult['finalizado_em']}")
        print(f"  Janela       : {ult['data_inicial']} -> {ult['data_final']}")
        print(f"  Registros    : {ult['registros_municipio']} contratos do municipio")
    else:
        print("  Ultima coleta: nao registrada (coletas_log vazio)")

    print()
    print(f"  Alertas abertos: {n_alertas}")
    print()
    return 0


# ── Sub-comando: coletar ──────────────────────────────────────────────────────

def cmd_coletar(args) -> int:
    from extrator.pncp import coletar

    if args.data_ini and args.data_fim:
        di, df = args.data_ini, args.data_fim
    else:
        hoje = date.today()
        di = (hoje - timedelta(days=90)).strftime("%Y%m%d")
        df = hoje.strftime("%Y%m%d")

    _header(f"coletar  {di} -> {df}")
    t0 = time.perf_counter()

    try:
        sumario = coletar(di, df)
    except Exception as e:
        print()
        _warn(f"Erro durante coleta: {e}")
        return 1

    print()
    print(SEP)
    print("  RESUMO DA COLETA")
    print(SEP)
    print(f"  Brutos varridos : {sumario['brutos_varridos']}")
    print(f"  Salvos (Rio/mun): {sumario['salvos_rio']}")
    if sumario["paginas_falhas"]:
        _warn(f"Paginas com falha: {len(sumario['paginas_falhas'])} (ver log acima)")
    print(f"  Tempo total     : {_elapsed(t0)}")
    print()
    return 0


# ── Sub-comando: analisar ─────────────────────────────────────────────────────

def cmd_analisar(args) -> int:
    from db.conexao import get_conn, DB_PATH
    from analisador import outliers, concentracao, licitacao, fracionamento
    from analisador.engine import persistir_alertas

    _header("analisar")

    if not DB_PATH.exists():
        _warn(f"Banco nao encontrado: {DB_PATH}")
        _warn("Execute primeiro: python -m sentinela coletar")
        print()
        return 1

    t0 = time.perf_counter()
    conn = get_conn(row_factory=True)

    print()
    _info("Executando detectores...")

    r_out  = outliers.detectar(conn)
    _ok(f"outliers      {len(r_out):3d} anomalias")

    r_conc = concentracao.detectar(conn)
    _ok(f"concentracao  {len(r_conc):3d} anomalias")

    r_lic  = licitacao.detectar(conn)
    _ok(f"licitacao     {len(r_lic):3d} anomalias")

    r_frac = fracionamento.detectar(conn)
    _ok(f"fracionamento {len(r_frac):3d} anomalias")

    todas = sorted(r_out + r_conc + r_lic + r_frac, key=lambda a: a.score, reverse=True)

    # Limpa alertas anteriores e persiste os novos
    conn.execute("DELETE FROM alertas")
    n_inseridos = persistir_alertas(conn, todas)

    conn.close()

    # Contagens por severidade e tipo
    por_sev  = Counter(a.severidade for a in todas)
    por_tipo = Counter(a.tipo       for a in todas)

    print()
    print(SEP)
    print("  RESUMO DA ANALISE")
    print(SEP)
    print(f"  Total de anomalias : {len(todas)}")
    print(f"  ALTA               : {por_sev['alta']}")
    print(f"  MEDIA              : {por_sev['media']}")
    print(f"  BAIXA              : {por_sev['baixa']}")
    print()
    print("  Por tipo:")
    for tipo, n in por_tipo.most_common():
        label = tipo.replace("sem_licitacao_", "").replace("_", " ")
        print(f"    {n:3d}  {label}")
    print()
    print(f"  Alertas salvos no banco: {n_inseridos}")
    print()

    print("  Top anomalias:")
    for i, a in enumerate(todas[:8], 1):
        sev = {"alta": "ALTA ", "media": "MEDIA", "baixa": "BAIXA"}.get(a.severidade, "?    ")
        print(f"    {i:2d}. {a.score:.3f}  [{sev}]  {a.titulo[:55]}")

    print()
    print(f"  Tempo total: {_elapsed(t0)}")
    print()
    return 0


# ── Sub-comando: painel ─────────────────────────────────────────────────────

def cmd_painel(_args) -> int:
    from relatorios.painel_html import GeradorPainelHTML

    _header("painel")
    t0 = time.perf_counter()

    try:
        caminho = GeradorPainelHTML().gerar()
    except FileNotFoundError as exc:
        _warn(str(exc))
        _warn("Execute primeiro: python -m sentinela coletar")
        print()
        return 1

    print()
    print(SEP)
    print("  RESUMO DO PAINEL")
    print(SEP)
    print(f"  Arquivo : {caminho}")
    print(f"  Tamanho : {caminho.stat().st_size:,} bytes")
    print(f"  Tempo   : {_elapsed(t0)}")
    print()
    return 0


# ── Sub-comando: investigar ─────────────────────────────────────────────────

def cmd_investigar(_args) -> int:
    from db.conexao import DB_PATH
    from db.database import GerenciadorBanco
    from analise.motor_ia import InvestigadorIA

    _header("investigar")

    if not DB_PATH.exists():
        _warn(f"Banco nao encontrado: {DB_PATH}")
        _warn("Execute primeiro: python -m sentinela coletar")
        print()
        return 1

    if not os.environ.get("GEMINI_API_KEY", "").strip():
        _warn("GEMINI_API_KEY nao definida no ambiente.")
        print()
        return 1

    t0 = time.perf_counter()
    gerenciador = GerenciadorBanco(db_path=DB_PATH)

    try:
        investigador = InvestigadorIA()
    except ValueError as exc:
        _warn(str(exc))
        print()
        return 1

    pendentes = gerenciador.listar_anomalias_sem_narrativa(limite=10)
    if not pendentes:
        _info("Nenhuma anomalia pendente de narrativa IA.")
        print()
        return 0

    print()
    _info(f"Processando {len(pendentes)} anomalias...")
    sucesso = 0

    for anomalia in pendentes:
        id_anomalia = int(anomalia["id"])
        try:
            narrativa = investigador.investigar_anomalia(anomalia)
            gerenciador.atualizar_narrativa_anomalia(id_anomalia, narrativa)
            sucesso += 1
            _ok(f"id={id_anomalia}  narrativa salva ({len(narrativa)} chars)")
            time.sleep(13)
        except Exception as exc:
            _warn(f"id={id_anomalia}  falhou: {exc}")
            if "429" in str(exc):
                time.sleep(30)
            else:
                time.sleep(13)

    print()
    print(SEP)
    print("  RESUMO DA INVESTIGACAO")
    print(SEP)
    print(f"  Processadas : {len(pendentes)}")
    print(f"  Com sucesso : {sucesso}")
    print(f"  Tempo       : {_elapsed(t0)}")
    print()
    return 0 if sucesso == len(pendentes) else 1


# ── Sub-comando: relatorio ────────────────────────────────────────────────────

def cmd_relatorio(args) -> int:
    from db.conexao import get_conn, DB_PATH
    from relatorios.builder import gerar

    _header("relatorio")

    if not DB_PATH.exists():
        _warn(f"Banco nao encontrado: {DB_PATH}")
        _warn("Execute primeiro: python -m sentinela coletar")
        print()
        return 1

    dir_saida = Path(args.dir) if args.dir else None
    t0 = time.perf_counter()

    print()
    conn = get_conn(row_factory=True)
    try:
        caminho = gerar(conn, dir_saida)
    finally:
        conn.close()

    n_linhas = sum(1 for _ in caminho.open(encoding="utf-8"))

    print()
    print(SEP)
    print("  RESUMO DO RELATORIO")
    print(SEP)
    print(f"  Arquivo : {caminho}")
    print(f"  Tamanho : {caminho.stat().st_size:,} bytes  |  {n_linhas} linhas")
    print(f"  Tempo   : {_elapsed(t0)}")
    print()
    return 0


# ── Parser e entry-point ──────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sentinela",
        description="Sentinela RJ — monitoramento de contratos publicos municipais",
    )
    sub = p.add_subparsers(dest="cmd", metavar="COMANDO")
    sub.required = True

    # status
    sub.add_parser("status", help="Mostra estatisticas do banco e ultima coleta")

    # coletar
    col = sub.add_parser("coletar", help="Coleta contratos do PNCP e salva no banco")
    col.add_argument("data_ini", nargs="?", metavar="AAAAMMDD",
                     help="Data inicial (padrao: hoje - 90 dias)")
    col.add_argument("data_fim", nargs="?", metavar="AAAAMMDD",
                     help="Data final (padrao: hoje)")

    # analisar
    sub.add_parser("analisar",
                   help="Detecta anomalias e salva alertas no banco")

    # relatorio
    rel = sub.add_parser("relatorio", help="Gera relatorio Markdown de anomalias")
    rel.add_argument("--dir", metavar="DIR",
                     help="Diretorio de saida (padrao: relatorios/)")

    # painel
    sub.add_parser("painel", help="Gera painel HTML estatico de controle")

    # investigar
    sub.add_parser(
        "investigar",
        help="Gera narrativas IA via Gemini (requer GEMINI_API_KEY)",
    )

    return p


def _carregar_env() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    try:
        with env_path.open(encoding="utf-8") as handle:
            for linha in handle:
                linha = linha.strip()
                if not linha or linha.startswith("#"):
                    continue
                chave, separador, valor = linha.partition("=")
                if not separador:
                    continue
                chave = chave.strip()
                if chave:
                    os.environ[chave] = valor.strip()
    except FileNotFoundError:
        pass


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    dispatch = {
        "status":    cmd_status,
        "coletar":   cmd_coletar,
        "analisar":  cmd_analisar,
        "relatorio": cmd_relatorio,
        "painel":      cmd_painel,
        "investigar":  cmd_investigar,
    }

    try:
        sys.exit(dispatch[args.cmd](args))
    except KeyboardInterrupt:
        print("\n  Interrompido pelo usuario.")
        sys.exit(130)
    except Exception as e:
        print(f"\n  ERRO: {e}")
        sys.exit(1)


if __name__ == "__main__":
    _carregar_env()
    main()
