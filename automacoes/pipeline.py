"""Pipeline agendado — coletar → enriquecer → analisar → investigar → notificar."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"

_GEMINI_COOLDOWN_S = 4.0
_MSG_GEMINI_COOLDOWN = (
    "    [Sentinela-IA] Resposta processada. Aguardando 4s (Rate Limiting Prevention)..."
)
_PROMPT_REFINO_GEMINI_LOTE = (
    "MODO LOTE (pipeline agendado):\n"
    "- Abra com o padrão do alerta nas 2 primeiras frases (tipo, ator, valor, risco).\n"
    "- Máximo 4–6 frases no corpo; zero enrolação, zero prefácio, zero repetir o JSON.\n"
    "- Diga o que checar primeiro; linguagem de auditor, não de acusação."
)


def _env_bool(nome: str, padrao: bool = False) -> bool:
    raw = os.getenv(nome, "").strip().lower()
    if not raw:
        return padrao
    return raw in ("true", "1", "yes", "sim")


def _env_int(nome: str, padrao: int) -> int:
    raw = os.getenv(nome, "").strip()
    return int(raw) if raw else padrao


def _env_float(nome: str, padrao: float) -> float:
    raw = os.getenv(nome, "").strip()
    return float(raw) if raw else padrao


@dataclass
class PipelineConfig:
    janela_dias: int = 90
    enriquecer_limite: int = 0
    investigar_limite: int = 10
    ia_intervalo_s: float = 13.0
    discord_max: int = 5
    discord_resumo: bool = True
    skip_enriquecer: bool = False
    skip_investigar: bool = False
    skip_notificar: bool = False
    abort_on_error: bool = False
    cron: str = "0 8 * * 1"
    timezone: str = "America/Sao_Paulo"
    run_on_start: bool = False

    @classmethod
    def from_env(cls) -> PipelineConfig:
        return cls(
            janela_dias=_env_int("PIPELINE_JANELA_DIAS", 90),
            enriquecer_limite=_env_int("PIPELINE_ENRIQUECER_LIMITE", 0),
            investigar_limite=_env_int("PIPELINE_INVESTIGAR_LIMITE", 10),
            ia_intervalo_s=_env_float("PIPELINE_IA_INTERVALO_S", 13.0),
            discord_max=_env_int("PIPELINE_DISCORD_MAX", 5),
            discord_resumo=_env_bool("PIPELINE_DISCORD_RESUMO", True),
            skip_enriquecer=_env_bool("PIPELINE_SKIP_ENRIQUECER", False),
            skip_investigar=_env_bool("PIPELINE_SKIP_INVESTIGAR", True),
            skip_notificar=_env_bool("PIPELINE_SKIP_NOTIFICAR", False),
            abort_on_error=_env_bool("PIPELINE_ABORT_ON_ERROR", False),
            cron=os.getenv("PIPELINE_CRON", "0 8 * * 1").strip(),
            timezone=os.getenv("PIPELINE_TIMEZONE", "America/Sao_Paulo").strip(),
            run_on_start=_env_bool("PIPELINE_RUN_ON_START", False),
        )


@dataclass
class EtapaResult:
    ok: bool
    mensagem: str
    metricas: dict[str, Any] = field(default_factory=dict)
    erro: str | None = None


@dataclass
class PipelineResult:
    coletar: EtapaResult
    enriquecer: EtapaResult
    analisar: EtapaResult
    investigar: EtapaResult
    notificar: EtapaResult
    empenhos_diarios: EtapaResult = field(
        default_factory=lambda: EtapaResult(False, "nao executado")
    )
    novos_alta: list[dict[str, Any]] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    duracao_s: float = 0.0

    @property
    def sucesso(self) -> bool:
        return self.coletar.ok and self.analisar.ok


def _configurar_logging() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d')}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    return log_path


def _aguardar_rate_limit_gemini() -> None:
    logger.info(_MSG_GEMINI_COOLDOWN)
    time.sleep(_GEMINI_COOLDOWN_S)


def _janela_coleta(config: PipelineConfig) -> tuple[str, str]:
    hoje = date.today()
    ini = hoje - timedelta(days=config.janela_dias)
    return ini.strftime("%Y%m%d"), hoje.strftime("%Y%m%d")


def _etapa_coletar(config: PipelineConfig) -> EtapaResult:
    from extrator.pncp import coletar

    di, df = _janela_coleta(config)
    logger.info("[pipeline] coletar iniciado %s -> %s", di, df)
    try:
        sumario = coletar(di, df)
        msg = (
            f"salvos={sumario.get('salvos_rio', 0)} "
            f"brutos={sumario.get('brutos_varridos', 0)}"
        )
        logger.info("[pipeline] coletar OK — %s", msg)
        return EtapaResult(True, msg, metricas=sumario)
    except Exception as exc:
        logger.exception("[pipeline] coletar FALHOU")
        return EtapaResult(False, "falha na coleta", erro=str(exc))


def _etapa_enriquecer(config: PipelineConfig) -> EtapaResult:
    if config.skip_enriquecer:
        return EtapaResult(True, "pulado (PIPELINE_SKIP_ENRIQUECER)")

    from db.conexao import get_conn
    from extrator.enriquecedor import Enriquecedor

    conn = get_conn(row_factory=True)
    limite_sql = (
        f" LIMIT {config.enriquecer_limite}" if config.enriquecer_limite > 0 else ""
    )
    pendentes = conn.execute(
        f"""
        SELECT ni FROM fornecedores
        WHERE ultima_consulta_sancao IS NULL
           OR ultima_consulta_sancao < datetime('now', '-24 hours')
        ORDER BY ni
        {limite_sql}
        """
    ).fetchall()

    if not pendentes:
        conn.close()
        return EtapaResult(True, "nenhum fornecedor pendente")

    enriquecedor = Enriquecedor()
    consultados = erros = 0
    try:
        for row in pendentes:
            try:
                enriquecedor.enriquecer_fornecedor(conn, row["ni"])
                consultados += 1
            except Exception as exc:
                erros += 1
                logger.warning("[pipeline] enriquecer ni=%s: %s", row["ni"], exc)
        conn.commit()
    finally:
        conn.close()

    msg = f"consultados={consultados} erros={erros}"
    logger.info("[pipeline] enriquecer OK — %s", msg)
    return EtapaResult(True, msg, metricas={"consultados": consultados, "erros": erros})


def _etapa_analisar(config: PipelineConfig) -> tuple[EtapaResult, list[dict[str, Any]]]:
    from analisador.engine import executar_e_persistir
    from db.alertas_sync import carregar_alertas
    from db.conexao import get_conn
    from db.regras_alerta import filtrar_para_notificacao

    conn = get_conn(row_factory=True)
    try:
        _, _, contagens, resumo = executar_e_persistir(conn)
        ids_novos = resumo.get("ids_inseridos") or []
        ids_notificar = filtrar_para_notificacao(conn, ids_novos)
        novos = carregar_alertas(conn, ids_notificar)
        msg = (
            f"inseridos={resumo.get('inseridos', 0)} "
            f"atualizados={resumo.get('atualizados', 0)} "
            f"removidos={resumo.get('removidos', 0)} "
            f"notificar={len(ids_notificar)}"
        )
        logger.info("[pipeline] analisar OK — %s", msg)
        etapa = EtapaResult(
            True,
            msg,
            metricas={**resumo, "contagens": contagens, "ids_notificar": ids_notificar},
        )
        return etapa, novos
    except Exception as exc:
        logger.exception("[pipeline] analisar FALHOU")
        return EtapaResult(False, "falha na analise", erro=str(exc)), []
    finally:
        conn.close()


def _etapa_investigar(config: PipelineConfig) -> EtapaResult:
    if config.skip_investigar:
        return EtapaResult(True, "pulado (PIPELINE_SKIP_INVESTIGAR)")

    from analise.motor_ia import InvestigadorIA
    from db.conexao import DB_PATH
    from db.database import GerenciadorBanco

    if not DB_PATH.exists():
        return EtapaResult(False, "banco ausente", erro="DB não encontrado")

    try:
        investigador = InvestigadorIA(
            prompt_revisao_extra=_PROMPT_REFINO_GEMINI_LOTE,
        )
    except ValueError as exc:
        logger.warning("[pipeline] investigar indisponivel: %s", exc)
        return EtapaResult(False, "IA indisponivel", erro=str(exc))

    gerenciador = GerenciadorBanco(db_path=DB_PATH)
    pendentes = gerenciador.listar_anomalias_sem_narrativa(
        limite=config.investigar_limite
    )
    if not pendentes:
        return EtapaResult(True, "nenhuma narrativa pendente")

    sucesso = 0
    for indice, anomalia in enumerate(pendentes, start=1):
        id_anomalia = int(anomalia["id"])
        try:
            logger.info(
                "[pipeline] investigar id=%s (%d/%d)",
                id_anomalia,
                indice,
                len(pendentes),
            )
            resultado = investigador.investigar_anomalia(anomalia)
            gerenciador.atualizar_narrativa_anomalia(
                id_anomalia,
                resultado.narrativa_ia,
                narrativa_gemma=resultado.narrativa_gemma,
                gemma_utilizado=1 if resultado.narrativa_gemma else 0,
            )
            sucesso += 1
            if investigador.gemini_utilizado:
                _aguardar_rate_limit_gemini()
            time.sleep(config.ia_intervalo_s)
        except Exception as exc:
            logger.warning("[pipeline] investigar id=%s: %s", id_anomalia, exc)
            time.sleep(config.ia_intervalo_s)

    msg = f"{sucesso}/{len(pendentes)} narrativas"
    logger.info("[pipeline] investigar %s", msg)
    ok = sucesso == len(pendentes)
    return EtapaResult(ok, msg, metricas={"sucesso": sucesso, "total": len(pendentes)})


def _etapa_notificar(
    config: PipelineConfig,
    novos_alta: list[dict[str, Any]],
    resumo_pipeline: dict[str, Any],
) -> EtapaResult:
    if config.skip_notificar:
        return EtapaResult(True, "pulado (PIPELINE_SKIP_NOTIFICAR)")

    if not os.getenv("DISCORD_WEBHOOK_URL", "").strip():
        return EtapaResult(True, "webhook Discord nao configurado")

    from automacoes.utils.notificador import NotificadorAlertas

    try:
        notificador = NotificadorAlertas()
        enviados = 0
        if novos_alta:
            enviados = notificador.enviar_novos_alertas(
                novos_alta,
                max_embeds=config.discord_max,
            )
        if config.discord_resumo:
            notificador.enviar_resumo_pipeline(resumo_pipeline)
        msg = f"embeds={enviados} resumo={'sim' if config.discord_resumo else 'nao'}"
        logger.info("[pipeline] notificar OK — %s", msg)
        return EtapaResult(True, msg, metricas={"embeds": enviados})
    except Exception as exc:
        logger.exception("[pipeline] notificar FALHOU")
        return EtapaResult(False, "falha no Discord", erro=str(exc))


def _notificar_empenhos_telegram(metricas: dict[str, Any], data_ini: str, data_fim: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.debug("[pipeline] Telegram não configurado — notificação empenhos ignorada")
        return
    texto = (
        f"🔔 <b>Sentinela RJ — Novos Empenhos PNCP</b>\n"
        f"Período: {data_ini} → {data_fim}\n"
        f"Contratos PNCP varridos: {metricas['total_pncp']}\n"
        f"Fornecedores monitorados atingidos: {metricas['novos_monitorados']}\n"
        f"Lançamentos salvos: {metricas['salvos']}"
    )
    import requests as _req

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = _req.post(
            url,
            json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"},
            timeout=10,
        )
        r.raise_for_status()
        logger.info("[pipeline] Telegram empenhos enviado — %d lançamentos", metricas["salvos"])
    except Exception as exc:
        logger.warning("[pipeline] Telegram falhou: %s", exc)


def _etapa_empenhos_diarios(config: PipelineConfig) -> EtapaResult:
    from extrator.empenhos_diarios import coletar_empenhos_novos

    hoje = date.today()
    data_ini = (hoje - timedelta(days=2)).strftime("%Y%m%d")
    data_fim = hoje.strftime("%Y%m%d")
    logger.info("[pipeline] empenhos_diarios iniciado %s -> %s", data_ini, data_fim)
    try:
        metricas = coletar_empenhos_novos(data_ini, data_fim)
        msg = (
            f"total_pncp={metricas['total_pncp']} "
            f"novos_monitorados={metricas['novos_monitorados']} "
            f"salvos={metricas['salvos']}"
        )
        logger.info("[pipeline] empenhos_diarios OK — %s", msg)
        if metricas["salvos"] > 0:
            _notificar_empenhos_telegram(metricas, data_ini, data_fim)
        return EtapaResult(True, msg, metricas=metricas)
    except Exception as exc:
        logger.exception("[pipeline] empenhos_diarios FALHOU")
        return EtapaResult(False, "falha na coleta de empenhos", erro=str(exc))


def executar_empenhos_diarios(config: PipelineConfig | None = None) -> EtapaResult:
    """Executa somente a etapa de empenhos diários (usada pelo cron EMPENHOS_CRON)."""
    config = config or PipelineConfig.from_env()
    return _etapa_empenhos_diarios(config)


def _notificar_falha_critica(erro: str) -> None:
    if not os.getenv("DISCORD_WEBHOOK_URL", "").strip():
        return
    try:
        from automacoes.utils.notificador import NotificadorAlertas

        NotificadorAlertas().enviar_alerta_discord("Pipeline falhou", erro)
    except Exception:
        logger.exception("[pipeline] falha ao enviar alerta critico Discord")


def executar_pipeline(config: PipelineConfig | None = None) -> PipelineResult:
    config = config or PipelineConfig.from_env()
    t0 = time.perf_counter()
    erros: list[str] = []

    coletar = _etapa_coletar(config)
    if not coletar.ok and config.abort_on_error:
        _notificar_falha_critica(coletar.erro or coletar.mensagem)
        return PipelineResult(
            coletar=coletar,
            enriquecer=EtapaResult(False, "nao executado"),
            analisar=EtapaResult(False, "nao executado"),
            investigar=EtapaResult(False, "nao executado"),
            notificar=EtapaResult(False, "nao executado"),
            erros=[coletar.erro or coletar.mensagem],
            duracao_s=time.perf_counter() - t0,
        )
    if not coletar.ok:
        erros.append(f"coletar: {coletar.erro}")

    empenhos_diarios = _etapa_empenhos_diarios(config)
    if not empenhos_diarios.ok:
        erros.append(f"empenhos_diarios: {empenhos_diarios.erro}")

    enriquecer = _etapa_enriquecer(config)
    if not enriquecer.ok:
        erros.append(f"enriquecer: {enriquecer.erro}")

    analisar, novos_alta = _etapa_analisar(config)
    if not analisar.ok:
        erros.append(f"analisar: {analisar.erro}")
        if config.abort_on_error:
            _notificar_falha_critica(analisar.erro or analisar.mensagem)
            return PipelineResult(
                coletar=coletar,
                enriquecer=enriquecer,
                analisar=analisar,
                investigar=EtapaResult(False, "nao executado"),
                notificar=EtapaResult(False, "nao executado"),
                novos_alta=[],
                erros=erros,
                duracao_s=time.perf_counter() - t0,
            )

    investigar = _etapa_investigar(config)
    if not investigar.ok:
        erros.append(f"investigar: {investigar.erro}")

    if novos_alta:
        from db.alertas_sync import carregar_alertas
        from db.conexao import get_conn

        conn = get_conn(row_factory=True)
        try:
            ids = [int(a["id"]) for a in novos_alta]
            novos_alta = carregar_alertas(conn, ids)
        finally:
            conn.close()

    duracao_s = time.perf_counter() - t0
    resumo_discord = {
        "coletar": coletar.mensagem,
        "empenhos_diarios": empenhos_diarios.mensagem,
        "enriquecer": enriquecer.mensagem,
        "analisar": analisar.mensagem,
        "investigar": investigar.mensagem,
        "novos_alta": len(novos_alta),
        "duracao_s": duracao_s,
        "erros": erros,
    }
    notificar = _etapa_notificar(config, novos_alta, resumo_discord)
    if not notificar.ok:
        erros.append(f"notificar: {notificar.erro}")

    resultado = PipelineResult(
        coletar=coletar,
        enriquecer=enriquecer,
        analisar=analisar,
        investigar=investigar,
        notificar=notificar,
        empenhos_diarios=empenhos_diarios,
        novos_alta=novos_alta,
        erros=erros,
        duracao_s=duracao_s,
    )
    logger.info(
        "[pipeline] concluido sucesso=%s duracao=%.1fs novos_alta=%d",
        resultado.sucesso,
        duracao_s,
        len(novos_alta),
    )
    return resultado


def iniciar_scheduler(config: PipelineConfig | None = None) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    config = config or PipelineConfig.from_env()
    _configurar_logging()
    trigger = CronTrigger.from_crontab(config.cron, timezone=config.timezone)
    scheduler = BlockingScheduler(timezone=config.timezone)
    scheduler.add_job(
        executar_pipeline,
        trigger,
        kwargs={"config": config},
        id="sentinela_pipeline",
        name="Sentinela RJ Pipeline",
    )
    empenhos_cron = os.getenv("EMPENHOS_CRON", "0 6 * * *").strip()
    scheduler.add_job(
        executar_empenhos_diarios,
        CronTrigger.from_crontab(empenhos_cron, timezone=config.timezone),
        kwargs={"config": config},
        id="sentinela_empenhos",
        name="Sentinela RJ Empenhos Diários",
    )
    logger.info(
        "[pipeline] daemon iniciado cron=%s empenhos_cron=%s tz=%s",
        config.cron,
        empenhos_cron,
        config.timezone,
    )
    if config.run_on_start:
        executar_pipeline(config)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[pipeline] daemon encerrado")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline Sentinela RJ")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--once", action="store_true", help="Executa a esteira uma vez")
    grupo.add_argument(
        "--daemon",
        action="store_true",
        help="Executa continuamente via APScheduler",
    )
    args = parser.parse_args(argv)

    config = PipelineConfig.from_env()
    if args.daemon:
        iniciar_scheduler(config)
        return 0

    _configurar_logging()
    resultado = executar_pipeline(config)
    return 0 if resultado.sucesso else 1


if __name__ == "__main__":
    raise SystemExit(main())
