"""Conflito de interesse — candidatos sócio × servidor (Supabase/Postgres)."""
from flask import Blueprint, jsonify, render_template, request

from web_auth import requer_login

import web_app as core

bp = Blueprint("conflitos", __name__)


def _serializar_candidato_conflito(item: dict) -> dict:
    """psycopg2 devolve NUMERIC como Decimal e TIMESTAMP como datetime —
    nenhum dos dois é serializável por jsonify sem conversão explícita."""
    from conflito_interesse.compatibilidade import calcular_compatibilidade
    from conflito_interesse.priorizacao import calcular_prioridade_investigacao
    from conflito_interesse.qualificacao import classificar_qualificacao

    item["qualificacao_classe"] = classificar_qualificacao(item.get("qualificacao_socio"))
    if item.get("score_similaridade") is not None:
        item["score_similaridade"] = float(item["score_similaridade"])
    if item.get("valor_total_contratos") is not None:
        item["valor_total_contratos"] = float(item["valor_total_contratos"])
    item["compatibilidade_data"] = calcular_compatibilidade(
        item.get("faixa_etaria_socio"), item.get("primeira_competencia_servidor")
    )
    item["prioridade_investigacao"] = calcular_prioridade_investigacao(
        item.get("contrato_ativo"),
        item.get("qtd_servidores_matched_mesmo_socio"),
        item["compatibilidade_data"],
        item.get("tem_alerta_severidade_alta"),
        item.get("tem_sancao"),
        item.get("lotacao_orgao_contratante"),
    )
    for campo in ("detectado_em", "revisado_em", "data_entrada_sociedade", "primeira_competencia_servidor", "analise_ia_em"):
        if item.get(campo) is not None:
            item[campo] = item[campo].isoformat()
    return item


@bp.route("/conflitos-interesse")
def conflitos_interesse_page():
    return render_template("conflitos_interesse.html")


@bp.route("/api/conflitos-interesse")
def api_conflitos_interesse_list():
    from conflito_interesse.triagem_repository import (
        MOTIVOS_DESCARTE_PADRAO,
        ConflitoTriagemRepository,
    )
    from db.triagem_core import STATUS_VALIDOS, normalizar_status, status_permitidos

    status_param = (request.args.get("status") or "aberto").strip().lower()
    todos = status_param in ("", "todos", "all")
    if not todos and status_param not in STATUS_VALIDOS:
        return jsonify({"error": f"Filtro de status inválido: '{status_param}'."}), 400

    conn = core.get_conflito_conn()
    try:
        cur = conn.cursor()
        if todos:
            cur.execute(
                """
                SELECT id, fornecedor_ni, nome_socio, qualificacao_socio,
                       matricula_servidor, nome_servidor, sigla_ua,
                       score_similaridade, data_entrada_sociedade,
                       faixa_etaria_socio, primeira_competencia_servidor,
                       contrato_ativo, valor_total_contratos,
                       qtd_servidores_matched_mesmo_socio,
                       tem_alerta_severidade_alta, tem_sancao,
                       qtd_servidores_mesmo_nome, lotacao_orgao_contratante,
                       analise_ia, analise_ia_em, analise_ia_provedor,
                       status, detectado_em, revisado_em
                FROM candidatos_conflito_interesse
                """
            )
        else:
            cur.execute(
                """
                SELECT id, fornecedor_ni, nome_socio, qualificacao_socio,
                       matricula_servidor, nome_servidor, sigla_ua,
                       score_similaridade, data_entrada_sociedade,
                       faixa_etaria_socio, primeira_competencia_servidor,
                       contrato_ativo, valor_total_contratos,
                       qtd_servidores_matched_mesmo_socio,
                       tem_alerta_severidade_alta, tem_sancao,
                       qtd_servidores_mesmo_nome, lotacao_orgao_contratante,
                       analise_ia, analise_ia_em, analise_ia_provedor,
                       status, detectado_em, revisado_em
                FROM candidatos_conflito_interesse
                WHERE status = %s
                """,
                (normalizar_status(status_param),),
            )
        colunas = [d[0] for d in cur.description]
        items = []
        for row in cur.fetchall():
            item = _serializar_candidato_conflito(dict(zip(colunas, row)))
            item["transicoes_permitidas"] = status_permitidos(item["status"])
            items.append(item)

        # Prioritários primeiro; dentro deles, lotação × órgão contratante no
        # topo; score de nome desempata (ver chave_ordenacao_fila).
        from conflito_interesse.priorizacao import chave_ordenacao_fila

        items.sort(key=chave_ordenacao_fila)

        resumo = ConflitoTriagemRepository(conn).resumo_status()

        return jsonify({
            "items": items,
            "resumo": resumo,
            "motivos_descarte": list(MOTIVOS_DESCARTE_PADRAO),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()


@bp.route("/conflitos-interesse/<int:candidato_id>/status", methods=["POST"])
@requer_login
@core.csrf_required
def api_conflitos_interesse_status(candidato_id: int):
    from conflito_interesse.triagem_repository import (
        CandidatoConflitoNaoEncontradoError,
        ConflitoTriagemRepository,
    )
    from db.triagem_core import TriagemError, normalizar_status

    body = request.get_json(silent=True) or {}
    status = body.get("status")
    if not status:
        return jsonify({"error": "Campo 'status' é obrigatório."}), 400

    conn = core.get_conflito_conn()
    try:
        repo = ConflitoTriagemRepository(conn)
        repo.atualizar_status(
            candidato_id,
            str(status),
            nota=body.get("nota"),
            motivo_descarte=body.get("motivo_descarte"),
        )
        return jsonify({"ok": True, "id": candidato_id, "status": normalizar_status(status)})
    except CandidatoConflitoNaoEncontradoError:
        return jsonify({"error": "not found"}), 404
    except TriagemError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()


_COLUNAS_ANALISE_IA = """
    id, fornecedor_ni, nome_socio, qualificacao_socio,
    matricula_servidor, nome_servidor, sigla_ua,
    score_similaridade, data_entrada_sociedade,
    faixa_etaria_socio, primeira_competencia_servidor,
    contrato_ativo, valor_total_contratos,
    qtd_servidores_matched_mesmo_socio,
    tem_alerta_severidade_alta, tem_sancao,
    qtd_servidores_mesmo_nome, lotacao_orgao_contratante,
    status, detectado_em, revisado_em
"""


@bp.route("/conflitos-interesse/<int:candidato_id>/analise-ia", methods=["POST"])
def api_conflitos_interesse_analise_ia(candidato_id: int):
    """Parecer de IA sobre o candidato — mesma cota diária dos endpoints de
    investigação de alertas (checar_cota_ia). O parecer é persistido para não
    gastar cota de novo em quem já foi analisado."""
    from conflito_interesse.analise_ia import analisar_candidato

    usuario, erro = core.checar_cota_ia()
    if erro:
        return erro

    conn = core.get_conflito_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {_COLUNAS_ANALISE_IA} FROM candidatos_conflito_interesse WHERE id = %s",
            (candidato_id,),
        )
        row = cur.fetchone()
        if row is None:
            return jsonify({"error": "not found"}), 404

        colunas = [d[0] for d in cur.description]
        item = _serializar_candidato_conflito(dict(zip(colunas, row)))

        try:
            parecer, provedor = analisar_candidato(item)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 503

        cur.execute(
            """UPDATE candidatos_conflito_interesse
               SET analise_ia = %s, analise_ia_em = now(), analise_ia_provedor = %s
               WHERE id = %s""",
            (parecer, provedor, candidato_id),
        )
        conn.commit()
        core.registrar_consumo_ia(usuario, "conflito_analise_ia")

        return jsonify({
            "id": candidato_id,
            "analise_ia": parecer,
            "analise_ia_provedor": provedor,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()
