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
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

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
    print(f"  Salvos (todos): {sumario.get('salvos_municipio', sumario['salvos_rio'])}")
    for item in sumario.get("salvos_por_municipio") or []:
        if item.get("salvos"):
            print(f"    · {item.get('nome')}: {item['salvos']}")
    if sumario["paginas_falhas"]:
        _warn(f"Paginas com falha: {len(sumario['paginas_falhas'])} (ver log acima)")
    print(f"  Tempo total     : {_elapsed(t0)}")
    print()
    return 0


# ── Sub-comando: backfill ────────────────────────────────────────────────────

def cmd_backfill(args) -> int:
    import os
    from db.conexao import DB_PATH, get_conn
    from extrator.backfill import executar_backfill, status_backfill
    from extrator.config_municipio import rotulo_filtro

    di = args.data_ini or os.getenv("BACKFILL_DATA_INICIO", "20220101")
    df = args.data_fim or date.today().strftime("%Y%m%d")

    if getattr(args, "status", False):
        _header(f"backfill status  {di} -> {df}")
        if not DB_PATH.exists():
            _warn(f"Banco nao encontrado: {DB_PATH}")
            return 1
        conn = get_conn(row_factory=True)
        try:
            st = status_backfill(conn, di, df)
        finally:
            conn.close()
        print(f"  Filtro            : {st['filtro']}")
        print(f"  Janelas           : {st['janelas_concluidas']}/{st['janelas_total']} concluidas")
        if st["ultima_janela_concluida"]:
            u = st["ultima_janela_concluida"]
            print(f"  Ultima concluida  : {u[0]} -> {u[1]}")
        if st["proxima_janela"]:
            p = st["proxima_janela"]
            print(f"  Proxima pendente  : {p[0]} -> {p[1]}")
        else:
            _ok("Backfill concluido para este intervalo.")
        print()
        if not st["concluido"]:
            _info("Retomar: python __main__.py backfill --continuar")
        return 0

    _header(f"backfill  {di} -> {df}" + ("  (continuar)" if args.continuar else ""))
    _info(f"Filtro: {rotulo_filtro()}")
    t0 = time.perf_counter()

    try:
        resumo = executar_backfill(di, df, continuar=args.continuar)
    except Exception as exc:
        _warn(f"Erro no backfill: {exc}")
        return 1

    print()
    print(SEP)
    print("  RESUMO DO BACKFILL")
    print(SEP)
    print(f"  Janelas (total)   : {resumo['janelas']}")
    if resumo.get("janelas_puladas"):
        print(f"  Janelas puladas   : {resumo['janelas_puladas']} (ja no log)")
    print(f"  Janelas nesta run : {resumo.get('janelas_executadas', resumo['janelas'])}")
    print(f"  Brutos varridos   : {resumo['brutos_varridos']}")
    print(f"  Salvos municipio  : {resumo['salvos_municipio']}")
    if resumo["paginas_falhas"]:
        _warn(f"Paginas com falha: {len(resumo['paginas_falhas'])}")
    print(f"  Tempo total       : {_elapsed(t0)}")
    print()
    return 0


# ── Sub-comando: sancoes (CEIS/CNEP) ─────────────────────────────────────────

def cmd_sancoes_api(args) -> int:
    from db.conexao import get_conn, init_db
    from extrator.sancoes_api import SancoesApiError, chave_configurada, sincronizar_sancoes_api

    _header("sancoes-api — consulta CEIS/CNEP por CNPJ (Portal da Transparencia)")
    t0 = time.perf_counter()

    if not chave_configurada():
        _warn("TRANSPARENCIA_API_KEY nao configurada.")
        _warn("Cadastre em portaldatransparencia.gov.br/api-de-dados e defina no .env")
        return 1

    init_db()
    conn = get_conn(row_factory=True)
    try:
        resumo = sincronizar_sancoes_api(conn, limite=args.limite, pausa_s=args.pausa)
    except SancoesApiError as exc:
        _warn(str(exc))
        return 1
    finally:
        conn.close()

    _ok(f"Fornecedores checados: {resumo['checados']}")
    _ok(f"Com sancao federal: {resumo['fornecedores_sancionados']} "
        f"({resumo['sancoes_registradas']} sancoes)")
    print(f"  Pendentes restantes: {resumo['pendentes_restantes']}")
    print(f"  Tempo: {_elapsed(t0)}")
    print()
    return 0


def cmd_sancoes(args) -> int:
    from db.conexao import get_conn, DB_PATH
    from extrator.sancoes_ingestao import ingestir_ceis_cnp

    _header("sancoes — ingestao CEIS/CNEP")

    if not DB_PATH.exists():
        _warn(f"Banco nao encontrado: {DB_PATH}")
        return 1

    conn = get_conn(row_factory=True)
    try:
        resumo = ingestir_ceis_cnp(conn)
    except Exception as exc:
        _warn(f"Erro na ingestao: {exc}")
        return 1
    finally:
        conn.close()

    for fonte, dados in resumo.items():
        if dados.get("erro"):
            _warn(f"{fonte.upper()}: {dados['erro']}")
        else:
            _ok(f"{fonte.upper()}: {dados.get('inseridos', 0)} registros")
    print()
    return 0


# ── Sub-comando: licitacoes ──────────────────────────────────────────────────

def cmd_licitacoes(args) -> int:
    from db.conexao import get_conn, init_db
    from extrator.licitacoes import coletar, coletar_itens, janela_padrao

    _header("licitacoes — coleta de certames PNCP")
    t0 = time.perf_counter()

    init_db()
    inicio, fim = args.inicio, args.fim
    if not inicio or not fim:
        inicio, fim = janela_padrao()
    print(f"  Janela: {inicio} → {fim}")

    conn = get_conn(row_factory=True)
    try:
        resumo = coletar(conn, inicio, fim)
        _ok(f"Licitações coletadas/atualizadas: {resumo.pop('total', 0)}")
        for modalidade, qtd in sorted(resumo.items()):
            print(f"    {modalidade}: {qtd}")

        if not args.sem_itens:
            resumo_itens = coletar_itens(conn, limite=args.itens_limite)
            _ok(
                f"Itens: {resumo_itens['itens']} coletados em "
                f"{resumo_itens['licitacoes_processadas']} licitações "
                f"(pendentes: {resumo_itens['pendentes_restantes']})"
            )
    except Exception as exc:
        _warn(f"Erro na coleta: {exc}")
        return 1
    finally:
        conn.close()

    print(f"  Tempo: {_elapsed(t0)}")
    print()
    return 0


# ── Sub-comando: transparencia ───────────────────────────────────────────────

def cmd_transparencia(args) -> int:
    from db.conexao import get_conn, DB_PATH
    from extrator.transparencia_rj import executar_transparencia_rj

    _header("transparencia — cross-ref empenhos RJ")

    if not DB_PATH.exists():
        _warn(f"Banco nao encontrado: {DB_PATH}")
        return 1

    conn = get_conn(row_factory=True)
    try:
        resumo = executar_transparencia_rj(conn)
    except FileNotFoundError as exc:
        _warn(str(exc))
        return 1
    except Exception as exc:
        _warn(f"Erro: {exc}")
        return 1
    finally:
        conn.close()

    ing = resumo["ingestao"]
    cruz = resumo["cruzamento"]
    _ok(f"Empenhos ingeridos: {ing.get('inseridos', 0)}")
    _ok(f"Cruzamentos PNCP x Transparencia: {cruz.get('cruzamentos', 0)}")
    print()
    return 0


# ── Sub-comando: analisar ─────────────────────────────────────────────────────

def cmd_analisar(args) -> int:
    from db.conexao import get_conn, DB_PATH
    from analisador.engine import executar_e_persistir

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

    todas, n_inseridos, contagens, _ = executar_e_persistir(conn)
    for nome, total in contagens.items():
        _ok(f"{nome:<14}{total:3d} anomalias")

    conn.close()

    por_sev = Counter(a.severidade for a in todas)
    por_tipo = Counter(a.tipo for a in todas)

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


# ── Sub-comando: enriquecer ──────────────────────────────────────────────────

def cmd_enriquecer(args) -> int:
    from db.conexao import get_conn, DB_PATH
    from extrator.enriquecedor import Enriquecedor

    _header("enriquecer")

    if not DB_PATH.exists():
        _warn(f"Banco nao encontrado: {DB_PATH}")
        _warn("Execute primeiro: python -m sentinela coletar")
        print()
        return 1

    conn = get_conn(row_factory=True)

    if args.reset:
        _warn("--reset: limpando sancoes e zerando flags em todos os fornecedores...")
        conn.execute("DELETE FROM fornecedor_sancoes")
        conn.execute("UPDATE fornecedores SET tem_sancao = 0, ultima_consulta_sancao = NULL")
        conn.commit()
        _ok("Reset concluido.")
        print()

    c = conn.cursor()
    c.execute("""
        SELECT ni, razao_social FROM fornecedores
        WHERE ultima_consulta_sancao IS NULL
           OR ultima_consulta_sancao < datetime('now', '-24 hours')
        ORDER BY ni
    """)
    pendentes = c.fetchall()

    total = len(pendentes)
    if total == 0:
        _info("Todos os fornecedores ja foram consultados nas ultimas 24h.")
        print()
        conn.close()
        return 0

    _info(f"{total} fornecedor(es) a consultar...")
    print()

    enriquecedor = Enriquecedor()
    t0 = time.perf_counter()
    consultados = com_sancao = sem_sancao = erros = 0
    _VERBOSE_ATE = 5  # diagnóstico detalhado nos primeiros N fornecedores

    for i, forn in enumerate(pendentes, 1):
        razao = (forn["razao_social"] or forn["ni"])[:50]
        enriquecedor.verbose = (i <= _VERBOSE_ATE)
        _info(f"Enriquecendo {i}/{total}: {razao}")
        try:
            resumo = enriquecedor.enriquecer_fornecedor(conn, forn["ni"])
            consultados += 1
            if not resumo["encontrado"]:
                sem_sancao += 1  # CNPJ não encontrado na BrasilAPI
            elif not resumo["ativo"]:
                com_sancao += 1
                _ok(f"  Inativo/inapto: {resumo['situacao'] or '?'}")
            else:
                sem_sancao += 1
        except Exception as e:
            erros += 1
            _warn(f"  Excecao inesperada: {e}")

    conn.close()

    print()
    print(SEP)
    print("  RESUMO DO ENRIQUECIMENTO")
    print(SEP)
    print(f"  Consultados   : {consultados}")
    print(f"  Inativos/aptos: {com_sancao}")
    print(f"  Ativos/n.enc. : {sem_sancao}")
    print(f"  Com erro/API  : {erros}")
    print(f"  Tempo total   : {_elapsed(t0)}")
    print()
    return 0


# ── Sub-comando: investigar ─────────────────────────────────────────────────

def cmd_investigar(args) -> int:
    from db.conexao import DB_PATH
    from db.database import GerenciadorBanco
    from analise.motor_ia import InvestigadorIA

    _header("investigar")

    if not DB_PATH.exists():
        _warn(f"Banco nao encontrado: {DB_PATH}")
        _warn("Execute primeiro: python -m sentinela coletar")
        print()
        return 1

    limite = getattr(args, "limite", 10)
    t0 = time.perf_counter()
    gerenciador = GerenciadorBanco(db_path=DB_PATH)

    try:
        investigador = InvestigadorIA()
    except ValueError as exc:
        _warn(str(exc))
        print()
        return 1

    pendentes = gerenciador.listar_anomalias_sem_narrativa(limite=limite)
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
            resultado = investigador.investigar_anomalia(anomalia)
            gerenciador.atualizar_narrativa_anomalia(
                id_anomalia,
                resultado.narrativa_ia,
                narrativa_gemma=resultado.narrativa_gemma,
                gemma_utilizado=1 if resultado.narrativa_gemma else 0,
            )
            sucesso += 1
            _ok(f"id={id_anomalia}  narrativa salva ({len(resultado.narrativa_ia)} chars)")
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


# ── Sub-comando: investigar_profundo ─────────────────────────────────────────

def cmd_investigar_profundo(args) -> int:
    import json
    from datetime import datetime, timezone

    from db.conexao import get_conn
    from investigacao import AgenteInvestigador

    alerta_id = args.alerta_id
    _header(f"investigar_profundo  alerta #{alerta_id}")

    conn = get_conn(row_factory=True)
    try:
        row = conn.execute(
            """
            SELECT a.*,
                   f.razao_social AS fornecedor_nome,
                   f.ni AS fornecedor_ni,
                   o.cnpj AS orgao_cnpj,
                   o.razao_social AS orgao_nome
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            WHERE a.id = ?
            """,
            (alerta_id,),
        ).fetchone()

        if row is None:
            _warn(f"Alerta {alerta_id} não encontrado")
            return 1

        dados = dict(row)
        agente = AgenteInvestigador()
        print()
        print(SEP)
        print(f"  INVESTIGAÇÃO PROFUNDA — Alerta #{alerta_id}")
        print(SEP)

        resultado = agente.investigar(alerta_id, dados)
        agora = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            INSERT INTO investigacoes
            (alerta_id, status, iniciado_em, concluido_em, evidencias,
             sintese, conclusao, grau_confianca, recomendacao, erro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alerta_id,
                resultado.status,
                agora,
                agora,
                json.dumps(resultado.evidencias, ensure_ascii=False, default=str),
                resultado.sintese,
                resultado.conclusao,
                resultado.grau_confianca,
                resultado.recomendacao,
                resultado.erro,
            ),
        )
        conn.commit()
    except Exception as exc:
        _warn(f"Falha na investigação profunda: {exc}")
        return 1
    finally:
        conn.close()

    print()
    print(SEP)
    print("  RESULTADO")
    print(SEP)
    print(f"  Status      : {resultado.status}")
    print(f"  Conclusão   : {resultado.conclusao}")
    print(f"  Confiança   : {resultado.grau_confianca}")
    print(f"  Recomendação: {resultado.recomendacao}")
    print(SEP)
    print()
    return 0 if resultado.status == "concluida" else 1


# ── Sub-comando: publicar ─────────────────────────────────────────────────────

def cmd_publicar(args) -> int:
    _header("publicar")
    print()
    _info("Etapa 1/3 — analisar")
    if cmd_analisar(args) != 0:
        return 1

    print()
    _info("Etapa 2/3 — investigar (narrativas IA)")
    inv_args = argparse.Namespace(limite=args.limite_ia)
    rc_inv = cmd_investigar(inv_args)
    if rc_inv != 0:
        _warn("Investigacao parcial ou falhou; relatorio sera gerado mesmo assim.")

    print()
    _info("Etapa 3/3 — relatorio")
    return cmd_relatorio(args)


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


# ── Sub-comando: dossie ───────────────────────────────────────────────────────

def cmd_dossie(args) -> int:
    from db.conexao import get_conn, DB_PATH
    from relatorios.dossie import DossieNaoEncontradoError, exportar_dossie

    _header("dossie")

    if not DB_PATH.exists():
        _warn(f"Banco nao encontrado: {DB_PATH}")
        print()
        return 1

    dir_saida = Path(args.dir) if args.dir else None
    t0 = time.perf_counter()
    conn = get_conn(row_factory=True)
    try:
        caminho = exportar_dossie(
            conn,
            args.alerta,
            dir_saida,
            gerar_ia=args.gerar_ia,
            formato=args.formato,
            db_path=DB_PATH,
        )
    except DossieNaoEncontradoError as exc:
        _warn(str(exc))
        print()
        return 1
    except ValueError as exc:
        _warn(f"Falha na geracao de narrativa IA: {exc}")
        print()
        return 1
    finally:
        conn.close()

    n_linhas = sum(1 for _ in caminho.open(encoding="utf-8"))
    print()
    print(SEP)
    print("  RESUMO DO DOSSIE")
    print(SEP)
    print(f"  Alerta  : {args.alerta}")
    print(f"  Arquivo : {caminho}")
    print(f"  Tamanho : {caminho.stat().st_size:,} bytes  |  {n_linhas} linhas")
    print(f"  Tempo   : {_elapsed(t0)}")
    print()
    return 0


# ── Sub-comando: pipeline ─────────────────────────────────────────────────────

def cmd_pipeline(args) -> int:
    from automacoes.pipeline import PipelineConfig, executar_pipeline, iniciar_scheduler

    config = PipelineConfig.from_env()
    if args.daemon:
        _header("pipeline daemon")
        iniciar_scheduler(config)
        return 0

    _header("pipeline")
    t0 = time.perf_counter()
    resultado = executar_pipeline(config)
    print()
    print(SEP)
    print("  RESUMO DO PIPELINE")
    print(SEP)
    print(f"  Coletar     : {resultado.coletar.mensagem}")
    print(f"  Enriquecer  : {resultado.enriquecer.mensagem}")
    print(f"  Analisar    : {resultado.analisar.mensagem}")
    print(f"  Investigar  : {resultado.investigar.mensagem}")
    print(f"  Notificar   : {resultado.notificar.mensagem}")
    print(f"  Novos alta  : {len(resultado.novos_alta)}")
    print(f"  Tempo       : {_elapsed(t0)}")
    if resultado.erros:
        print(f"  Avisos      : {len(resultado.erros)}")
    print()
    return 0 if resultado.sucesso else 1


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

    sub.add_parser("analisar",
                   help="Detecta anomalias e salva alertas no banco")

    # backfill
    bf = sub.add_parser(
        "backfill",
        help="Coleta historica PNCP em janelas mensais (multi-municipio via env)",
    )
    bf.add_argument("data_ini", nargs="?", help="Data inicial AAAAMMDD (env BACKFILL_DATA_INICIO)")
    bf.add_argument("data_fim", nargs="?", help="Data final AAAAMMDD (padrao: hoje)")
    bf.add_argument(
        "--continuar",
        action="store_true",
        help="Retoma do ultimo mes concluido (consulta coletas_log)",
    )
    bf.add_argument(
        "--status",
        action="store_true",
        help="Mostra progresso do backfill sem coletar",
    )

    # sancoes
    sub.add_parser(
        "sancoes",
        help="Ingere CSV CEIS/CNEP (SANCOES_*_URL ou data/raw/sancoes/)",
    )

    # transparencia
    sub.add_parser(
        "transparencia",
        help="Ingere empenhos Transparencia RJ e cruza com contratos PNCP",
    )

    # sancoes-api
    sapi = sub.add_parser(
        "sancoes-api",
        help="Consulta CEIS/CNEP por CNPJ na API do Portal da Transparencia (incremental)",
    )
    sapi.add_argument("--limite", type=int, default=300, metavar="N",
                      help="Fornecedores a checar por execucao (padrao: 300)")
    sapi.add_argument("--pausa", type=float, default=0.75, metavar="S",
                      help="Pausa entre chamadas em segundos (padrao: 0.75, ~80/min)")

    # licitacoes
    lic = sub.add_parser(
        "licitacoes",
        help="Coleta certames competitivos do PNCP (estimado x homologado, itens)",
    )
    lic.add_argument("--inicio", metavar="AAAAMMDD", help="Data inicial (padrao: 6 meses atras)")
    lic.add_argument("--fim", metavar="AAAAMMDD", help="Data final (padrao: hoje)")
    lic.add_argument("--sem-itens", action="store_true", help="Pula a coleta de itens")
    lic.add_argument("--itens-limite", type=int, default=200, metavar="N",
                     help="Maximo de licitacoes com itens por execucao (padrao: 200)")

    # relatorio
    rel = sub.add_parser("relatorio", help="Gera relatorio Markdown de anomalias")
    rel.add_argument("--dir", metavar="DIR",
                     help="Diretorio de saida (padrao: relatorios/)")

    # dossie
    dos = sub.add_parser(
        "dossie",
        help="Exporta dossiê investigativo consolidado de um alerta",
    )
    dos.add_argument(
        "--alerta",
        type=int,
        required=True,
        metavar="ID",
        help="ID do alerta na tabela alertas",
    )
    dos.add_argument(
        "--formato",
        choices=("md", "json", "pdf"),
        default="md",
        help="Formato de exportacao (padrao: md)",
    )
    dos.add_argument(
        "--dir",
        metavar="DIR",
        help="Diretorio de saida (padrao: relatorios/)",
    )
    dos.add_argument(
        "--gerar-ia",
        action="store_true",
        help="Gera narrativa via Ollama se narrativa_ia estiver vazia",
    )

    # investigar
    inv = sub.add_parser(
        "investigar",
        help="Gera narrativas IA via Ollama local (ollama pull llama3.1)",
    )
    inv.add_argument(
        "--limite",
        type=int,
        default=10,
        metavar="N",
        help="Maximo de alertas a processar por execucao (padrao: 10)",
    )

    # investigar_profundo
    ip = sub.add_parser(
        "investigar_profundo",
        help="Investigacao profunda ReAct (PNCP + BrasilAPI + Gemma4)",
    )
    ip.add_argument(
        "alerta_id",
        type=int,
        metavar="ID",
        help="ID do alerta na tabela alertas",
    )

    # publicar
    pub = sub.add_parser(
        "publicar",
        help="Pipeline completo: analisar + investigar + relatorio",
    )
    pub.add_argument("--dir", metavar="DIR",
                     help="Diretorio de saida do relatorio (padrao: relatorios/)")
    pub.add_argument(
        "--limite-ia",
        type=int,
        default=50,
        metavar="N",
        help="Maximo de narrativas IA na etapa investigar (padrao: 50)",
    )

    # enriquecer
    enr = sub.add_parser(
        "enriquecer",
        help="Enriquece fornecedores via BrasilAPI (cadastro + sync CEIS/CNEP)",
    )
    enr.add_argument(
        "--reset",
        action="store_true",
        help="Zera tem_sancao e ultima_consulta_sancao antes de re-consultar tudo",
    )

    # pipeline
    pip = sub.add_parser(
        "pipeline",
        help="Esteira completa: coletar -> enriquecer -> analisar -> investigar -> Discord",
    )
    pip_grp = pip.add_mutually_exclusive_group(required=True)
    pip_grp.add_argument(
        "--once",
        action="store_true",
        help="Executa o pipeline uma vez (Task Scheduler)",
    )
    pip_grp.add_argument(
        "--daemon",
        action="store_true",
        help="Executa continuamente via APScheduler",
    )

    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    dispatch = {
        "status":    cmd_status,
        "coletar":   cmd_coletar,
        "backfill":  cmd_backfill,
        "sancoes":   cmd_sancoes,
        "sancoes-api": cmd_sancoes_api,
        "transparencia": cmd_transparencia,
        "licitacoes": cmd_licitacoes,
        "analisar":  cmd_analisar,
        "relatorio": cmd_relatorio,
        "dossie":    cmd_dossie,
        "publicar":  cmd_publicar,
        "investigar":  cmd_investigar,
        "investigar_profundo": cmd_investigar_profundo,
        "enriquecer":  cmd_enriquecer,
        "pipeline":    cmd_pipeline,
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
    main()
