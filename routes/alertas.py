"""Alertas — listagem, triagem, agrupamento, detalhe, investigações de IA e dossiê."""
import json
import math
import sqlite3
import threading
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from analise.motivos_descarte import MOTIVOS_FALSO_POSITIVO, extrair_motivo_descarte
from analise.score_composto import calcular_score_composto
from web_auth import requer_login

import web_app as core

bp = Blueprint("alertas", __name__)


# ---------------------------------------------------------------------------
# Alertas — list
# ---------------------------------------------------------------------------
@bp.route("/api/alertas")
def alertas_list():
    db = core.get_db()
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        tipo = request.args.get("tipo")
        severidade = request.args.get("severidade")
        ano = request.args.get("ano")
        fornecedor = request.args.get("fornecedor")

        base = """
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
        """
        conditions: list[str] = []
        params: list = []

        if tipo:
            conditions.append("a.tipo = ?")
            params.append(tipo)
        if severidade:
            conditions.append("a.severidade = ?")
            params.append(severidade)
        if ano:
            conditions.append("strftime('%Y', c.data_assinatura) = ?")
            params.append(ano)
        if fornecedor:
            conditions.append("f.razao_social LIKE ?")
            params.append(f"%{fornecedor}%")
        core._aplicar_filtro_municipio(conditions, params, core._municipio_ibge_request())

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = db.execute(
            f"SELECT COUNT(*) {base} {where}", params
        ).fetchone()[0]

        pages = math.ceil(total / per_page) if total else 0
        offset = (page - 1) * per_page

        rows = db.execute(
            f"""
            SELECT a.id, a.tipo, a.severidade, a.descricao, a.valor_referencia,
                   a.narrativa_ia, a.numero_controle_pncp,
                   f.razao_social AS fornecedor,
                   c.objeto, c.data_assinatura, c.orgao_cnpj,
                   o.razao_social AS orgao
            {base} {where}
            ORDER BY a.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

        return jsonify(
            {
                "items": [dict(r) for r in rows],
                "total": total,
                "page": page,
                "pages": pages,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Alertas — triagem (helpers + fila)
# ---------------------------------------------------------------------------
_SEV_PRIORITY = {"alta": 3, "media": 2, "baixa": 1}
_STATUS_PRIORITY = {"aberto": 4, "investigando": 3, "confirmado": 2, "descartado": 1}


def _aplicar_filtro_status(
    conditions: list[str],
    params: list,
    status_param: str | None,
) -> None:
    from db.triagem import filtro_status_sql

    if not status_param:
        return
    clause, filtro_params = filtro_status_sql(status_param)
    if clause:
        conditions.append(clause)
        params.extend(filtro_params)


@bp.route("/api/alertas/triagem")
def alertas_triagem():
    from db.filtro_municipio import resumo_triagem_municipio
    from db.triagem import resumo_status

    db = core.get_db()
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        status = request.args.get("status", "fila")
        ibge = core._municipio_ibge_request()

        base = """
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
        """
        conditions: list[str] = []
        params: list = []
        _aplicar_filtro_status(conditions, params, status)
        core._aplicar_filtro_municipio(conditions, params, ibge)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = db.execute(f"SELECT COUNT(*) {base} {where}", params).fetchone()[0]
        pages = math.ceil(total / per_page) if total else 0
        offset = (page - 1) * per_page

        rows = db.execute(
            f"""
            SELECT a.id, a.tipo, a.severidade, a.score, a.status,
                   a.descricao, a.valor_referencia, a.notas_triagem,
                   a.status_atualizado_em, a.narrativa_ia, a.numero_controle_pncp,
                   f.razao_social AS fornecedor,
                   c.objeto, c.data_assinatura,
                   o.razao_social AS orgao
            {base} {where}
            ORDER BY {core._SCORE_SQL} DESC, a.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

        items = []
        for row in rows:
            item = dict(row)
            item["score_composto"] = calcular_score_composto(
                item.get("score"), item.get("severidade"), item.get("valor_referencia"),
            )
            items.append(item)

        resumo = resumo_triagem_municipio(db, ibge) if ibge else resumo_status(db)
        return jsonify({
            "resumo": resumo,
            "items": items,
            "total": total,
            "page": page,
            "pages": pages,
            "municipio_ibge": ibge,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@bp.route("/api/alertas/feedback/descartes")
def alertas_feedback_descartes():
    """Resumo de descartes por tipo de alerta e motivo de falso positivo."""
    db = core.get_db()
    try:
        rows = db.execute(
            """
            SELECT a.tipo, h.nota
            FROM alertas_historico h
            JOIN alertas a ON a.id = h.alerta_id
            WHERE h.status_novo = 'descartado'
            """
        ).fetchall()
        por_tipo: dict[str, int] = {}
        por_motivo: dict[str, int] = {}
        sem_motivo = 0
        for row in rows:
            tipo = row["tipo"] or "desconhecido"
            por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
            motivo = extrair_motivo_descarte(row["nota"])
            if motivo:
                por_motivo[motivo] = por_motivo.get(motivo, 0) + 1
            else:
                sem_motivo += 1
        return jsonify({
            "motivos_disponiveis": MOTIVOS_FALSO_POSITIVO,
            "por_tipo": por_tipo,
            "por_motivo": por_motivo,
            "sem_motivo_estruturado": sem_motivo,
            "total_descartes": len(rows),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Alertas — grouped
# ---------------------------------------------------------------------------
def _anexar_conflito(db, items) -> None:
    """Anexa a cada grupo o resumo de conflito de interesse do fornecedor
    (materializado em fornecedores_conflito por db.conflito_flags). Sem candidato
    → `conflito` = None. Tabela ausente (DB antigo) é tratada como sem dados."""
    fnis = [it["fornecedor_ni"] for it in items if it.get("fornecedor_ni")]
    if not fnis:
        return
    placeholders = ",".join("?" * len(fnis))
    try:
        rows = db.execute(
            f"""SELECT fornecedor_ni, qtd_candidatos, tem_lotacao, tem_cpf_confirmado
                FROM fornecedores_conflito WHERE fornecedor_ni IN ({placeholders})""",
            fnis,
        ).fetchall()
    except Exception:
        rows = []
    por_ni = {r["fornecedor_ni"]: r for r in rows}
    for it in items:
        r = por_ni.get(it.get("fornecedor_ni"))
        it["conflito"] = {
            "qtd": r["qtd_candidatos"],
            "forte": bool(r["tem_lotacao"]),
            "cpf_confirmado": bool(r["tem_cpf_confirmado"]),
        } if r else None


@bp.route("/api/alertas/agrupados")
def alertas_agrupados():
    db = core.get_db()
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        tipo = request.args.get("tipo")
        severidade = request.args.get("severidade")
        ano = request.args.get("ano")
        fornecedor = request.args.get("fornecedor")
        valor_min = request.args.get("valor_min", type=float)
        status = request.args.get("status")
        conflito = request.args.get("conflito")

        joins = """
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
        """
        conditions: list[str] = []
        params: list = []

        _aplicar_filtro_status(conditions, params, status)
        core._aplicar_filtro_municipio(conditions, params, core._municipio_ibge_request())

        if tipo:
            conditions.append("a.tipo = ?")
            params.append(tipo)
        if severidade:
            conditions.append("a.severidade = ?")
            params.append(severidade)
        if ano:
            conditions.append("strftime('%Y', c.data_assinatura) = ?")
            params.append(ano)
        if fornecedor:
            cnpj = fornecedor.replace(".", "").replace("/", "").replace("-", "")
            conditions.append("(f.razao_social LIKE ? OR f.ni LIKE ?)")
            params.extend([f"%{fornecedor}%", f"%{cnpj}%"])
        if valor_min is not None:
            conditions.append("a.valor_referencia >= ?")
            params.append(valor_min)
        # Cruzamento com conflito de interesse (sócio-servidor): 'forte' = há
        # candidato com lotação × órgão contratante; 'qualquer' = há candidato.
        if conflito == "forte":
            conditions.append(
                "c.fornecedor_ni IN (SELECT fornecedor_ni FROM fornecedores_conflito WHERE tem_lotacao = 1)"
            )
        elif conflito in ("qualquer", "1", "true"):
            conditions.append(
                "c.fornecedor_ni IN (SELECT fornecedor_ni FROM fornecedores_conflito)"
            )

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = db.execute(
            f"SELECT COUNT(*) FROM (SELECT DISTINCT c.fornecedor_ni, a.tipo {joins} {where})",
            params,
        ).fetchone()[0]

        pages = math.ceil(total / per_page) if total else 0
        offset = (page - 1) * per_page

        group_rows = db.execute(
            f"""
            SELECT c.fornecedor_ni, a.tipo, f.razao_social AS fornecedor_nome,
                   MAX({core._SCORE_SQL}) AS score_composto
            {joins} {where}
            GROUP BY c.fornecedor_ni, a.tipo, f.razao_social
            ORDER BY score_composto DESC, c.fornecedor_ni, a.tipo
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

        items = []
        for gr in group_rows:
            fni = gr["fornecedor_ni"]
            tp = gr["tipo"]

            detail_cond = ["c.fornecedor_ni = ?", "a.tipo = ?"]
            detail_params: list = [fni, tp]
            if ano:
                detail_cond.append("strftime('%Y', c.data_assinatura) = ?")
                detail_params.append(ano)

            alerts = db.execute(
                f"""
                SELECT a.id, a.severidade, a.status, a.descricao, a.valor_referencia,
                       a.narrativa_ia, a.numero_controle_pncp, c.objeto,
                       c.data_assinatura, o.razao_social AS orgao
                FROM alertas a
                LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
                LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
                WHERE {' AND '.join(detail_cond)}
                ORDER BY a.id DESC
                """,
                detail_params,
            ).fetchall()

            severidades = [a["severidade"] for a in alerts]
            statuses = [a["status"] or "aberto" for a in alerts]
            max_sev = max(severidades, key=lambda s: _SEV_PRIORITY.get(s, 0), default="baixa")
            max_status = max(
                statuses,
                key=lambda s: _STATUS_PRIORITY.get(s, 0),
                default="aberto",
            )
            valor_total = sum(a["valor_referencia"] or 0 for a in alerts)
            valor_max = max((a["valor_referencia"] or 0 for a in alerts), default=0)
            datas = [a["data_assinatura"] for a in alerts if a["data_assinatura"]]
            narrativa = next((a["narrativa_ia"] for a in alerts if a["narrativa_ia"]), None)

            items.append({
                "grupo_id": f"{fni}__{tp}",
                "fornecedor_ni": fni,
                "fornecedor": gr["fornecedor_nome"] or fni,
                "tipo": tp,
                "severidade": max_sev,
                "status": max_status,
                "score_composto": round(float(gr["score_composto"] or 0), 4),
                "ocorrencias": len(alerts),
                "valor_total": valor_total,
                "valor_max": valor_max,
                "data_mais_recente": max(datas) if datas else None,
                "narrativa_ia": narrativa,
                "alertas": [
                    {
                        "id": a["id"],
                        "status": a["status"] or "aberto",
                        "descricao": a["descricao"],
                        "valor_referencia": a["valor_referencia"],
                        "objeto": a["objeto"],
                        "data_assinatura": a["data_assinatura"],
                        "numero_controle_pncp": a["numero_controle_pncp"],
                        "orgao": a["orgao"],
                    }
                    for a in alerts
                ],
            })

        _anexar_conflito(db, items)

        return jsonify({
            "items": items,
            "total": total,
            "page": page,
            "pages": pages,
            "municipio_ibge": core._municipio_ibge_request(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Alertas — detail
# ---------------------------------------------------------------------------
@bp.route("/api/alertas/<int:alert_id>", methods=["GET", "PATCH", "OPTIONS"])
@requer_login
def alertas_detail(alert_id: int):
    if request.method == "OPTIONS":
        return "", 204

    if request.method == "PATCH":
        from db.triagem import (
            AlertaNaoEncontradoError,
            TriagemError,
            atualizar_status_alerta,
        )

        body = request.get_json(silent=True) or {}
        status = body.get("status")
        if not status:
            return jsonify({"error": "Campo 'status' é obrigatório."}), 400

        db = core.get_db()
        try:
            resultado = atualizar_status_alerta(
                db,
                alert_id,
                status=str(status),
                nota=body.get("nota"),
                motivo_descarte=body.get("motivo_descarte"),
            )
            return jsonify(resultado)
        except AlertaNaoEncontradoError:
            return jsonify({"error": "not found"}), 404
        except TriagemError as exc:
            return jsonify({"error": str(exc)}), 422
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        finally:
            db.close()

    db = core.get_db()
    try:
        row = db.execute(
            """
            SELECT a.*,
                   c.objeto, c.data_assinatura, c.data_vigencia_inicio,
                   c.data_vigencia_fim, c.valor_inicial, c.valor_global,
                   c.informacao_complementar, c.numero_contrato_empenho,
                   c.fornecedor_ni,
                   f.razao_social AS fornecedor, f.tipo_pessoa,
                   o.razao_social AS orgao
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            WHERE a.id = ?
            """,
            (alert_id,),
        ).fetchone()
        if row is None:
            return jsonify({"error": "not found"}), 404
        from db.transparencia_cruzamentos import listar_empenhos_vinculados
        from db.triagem import listar_historico, normalizar_status, status_permitidos

        payload = dict(row)
        payload["status"] = normalizar_status(payload.get("status"))
        payload["historico"] = listar_historico(db, alert_id)
        payload["transicoes_permitidas"] = status_permitidos(payload["status"])
        payload["transparencia_rj"] = listar_empenhos_vinculados(
            db, payload.get("numero_controle_pncp")
        )
        _anexar_conflito(db, [payload])  # adiciona payload["conflito"]
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@bp.route("/api/alertas/<int:alert_id>/investigar", methods=["POST", "OPTIONS"])
def alertas_investigar(alert_id: int):
    if request.method == "OPTIONS":
        return "", 204

    usuario, erro = core.checar_cota_ia()
    if erro:
        return erro

    from analise.motor_ia import InvestigadorIA
    from db.conexao import DB_PATH
    from db.database import GerenciadorBanco

    db = core.get_db()
    try:
        row = db.execute(
            """
            SELECT a.id, a.tipo, a.severidade, a.descricao, a.metodologia,
                   a.valor_referencia, a.numero_controle_pncp, a.status,
                   COALESCE(c.objeto, '') AS objeto,
                   COALESCE(c.valor_global, 0) AS valor_global,
                   COALESCE(f.razao_social, '') AS fornecedor
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            WHERE a.id = ?
            """,
            (alert_id,),
        ).fetchone()
        if row is None:
            return jsonify({"error": "not found"}), 404

        try:
            investigador = InvestigadorIA()
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 503

        payload = dict(row)
        parecer = investigador.emitir_parecer(payload)
        # Persiste a análise como narrativa_ia (dossiê e histórico do alerta).
        GerenciadorBanco(db_path=DB_PATH).atualizar_narrativa_anomalia(
            alert_id, parecer.get("analise", ""),
        )
        core.registrar_consumo_ia(usuario, "investigar")
        from analise.motor_ia import NOMES_PROVEDOR

        return jsonify({
            "id": alert_id,
            "parecer": parecer,
            "narrativa_ia": parecer.get("analise", ""),
            "provedor_nome": NOMES_PROVEDOR.get(parecer.get("provedor"), parecer.get("provedor")),
        })
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Investigação Profunda — Agente ReAct
# ---------------------------------------------------------------------------
@bp.route("/api/alertas/<int:alert_id>/investigar_profundo", methods=["POST", "OPTIONS"])
def alertas_investigar_profundo(alert_id: int):
    if request.method == "OPTIONS":
        return "", 204

    usuario, erro = core.checar_cota_ia()
    if erro:
        return erro

    db = core.get_db()
    try:
        row = db.execute(
            """
            SELECT a.id, a.tipo, a.severidade, a.descricao, a.metodologia,
                   a.valor_referencia, a.numero_controle_pncp, a.status,
                   COALESCE(c.objeto, '') AS objeto,
                   COALESCE(c.valor_global, 0) AS valor_global,
                   COALESCE(f.razao_social, '') AS fornecedor_nome,
                   COALESCE(f.ni, '') AS fornecedor_ni,
                   COALESCE(o.cnpj, '') AS orgao_cnpj,
                   COALESCE(o.razao_social, '') AS orgao_nome
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            WHERE a.id = ?
            """,
            (alert_id,),
        ).fetchone()

        if row is None:
            return jsonify({"error": "not found"}), 404

        dados_alerta = dict(row)
    finally:
        db.close()

    db2 = core.get_db()
    try:
        inv_existente = db2.execute(
            """
            SELECT id, status FROM investigacoes
            WHERE alerta_id = ? AND status = 'rodando'
            ORDER BY id DESC LIMIT 1
            """,
            (alert_id,),
        ).fetchone()
        if inv_existente:
            return jsonify({"status": "ja_rodando", "alerta_id": alert_id}), 202
    finally:
        db2.close()

    db3 = core.get_db()
    try:
        cur = db3.execute(
            """
            INSERT INTO investigacoes (alerta_id, status, iniciado_em)
            VALUES (?, 'rodando', ?)
            """,
            (alert_id, datetime.now(timezone.utc).isoformat()),
        )
        inv_id = cur.lastrowid
        db3.commit()
    finally:
        db3.close()

    core.registrar_consumo_ia(usuario, "investigar_profundo")

    def _rodar_agente(alerta_id: int, inv_id: int, dados: dict) -> None:
        from investigacao import AgenteInvestigador

        resultado = AgenteInvestigador().investigar(alerta_id, dados)

        conn = sqlite3.connect(core.DB_PATH)
        try:
            conn.execute(
                """
                UPDATE investigacoes SET
                    status = ?,
                    concluido_em = ?,
                    evidencias = ?,
                    sintese = ?,
                    conclusao = ?,
                    grau_confianca = ?,
                    recomendacao = ?,
                    erro = ?
                WHERE id = ?
                """,
                (
                    resultado.status,
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(resultado.evidencias, ensure_ascii=False, default=str),
                    resultado.sintese,
                    resultado.conclusao,
                    resultado.grau_confianca,
                    resultado.recomendacao,
                    resultado.erro,
                    inv_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    thread = threading.Thread(
        target=_rodar_agente,
        args=(alert_id, inv_id, dados_alerta),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "status": "iniciado",
        "alerta_id": alert_id,
        "inv_id": inv_id,
        "mensagem": "Investigação profunda iniciada em background.",
    }), 202


@bp.route("/api/investigacoes/<int:alert_id>/status", methods=["GET"])
def investigacao_status(alert_id: int):
    """Retorna o status atual da investigação profunda do alerta."""
    db = core.get_db()
    try:
        row = db.execute(
            """
            SELECT id, status, iniciado_em, concluido_em,
                   sintese, conclusao, grau_confianca, recomendacao, erro,
                   evidencias
            FROM investigacoes
            WHERE alerta_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (alert_id,),
        ).fetchone()

        if row is None:
            return jsonify({"status": "nenhuma"}), 200

        dados = dict(row)

        ev: dict = {}
        try:
            ev = json.loads(dados.get("evidencias") or "{}")
        except Exception:
            pass

        return jsonify({
            "id": dados["id"],
            "alerta_id": alert_id,
            "status": dados["status"],
            "iniciado_em": dados["iniciado_em"],
            "concluido_em": dados["concluido_em"],
            "sintese": dados["sintese"],
            "conclusao": dados["conclusao"],
            "grau_confianca": dados["grau_confianca"],
            "recomendacao": dados["recomendacao"],
            "erro": dados["erro"],
            "resumos": {
                "cadastro": (ev.get("cadastro") or {}).get("resumo"),
                "historico_fornecedor": (ev.get("historico_fornecedor") or {}).get("resumo"),
                "historico_orgao": (ev.get("historico_orgao") or {}).get("resumo"),
                "processos_tjrj": (ev.get("processos_tjrj") or {}).get("resumo"),
                "decisoes_tcm": (ev.get("decisoes_tcm") or {}).get("resumo"),
            },
        })
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Dossiê investigativo
# ---------------------------------------------------------------------------
@bp.route("/api/dossie/<int:alerta_id>")
def dossie_api(alerta_id: int):
    from relatorios.dossie import (
        DossieNaoEncontradoError,
        obter_dossie,
        renderizar_markdown,
        renderizar_pdf,
        serializar_json,
    )

    formato = request.args.get("formato", "json").strip().lower()
    gerar_ia = request.args.get("gerar_ia", "false").strip().lower() in (
        "true",
        "1",
        "yes",
    )
    usuario = None
    if gerar_ia:
        usuario, erro = core.checar_cota_ia()
        if erro:
            return erro
    db = core.get_db()
    try:
        dados = obter_dossie(db, alerta_id, gerar_ia=gerar_ia, db_path=core.DB_PATH)
        if gerar_ia:
            core.registrar_consumo_ia(usuario, "dossie_ia")
    except DossieNaoEncontradoError:
        return jsonify({"error": "not found"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()

    if formato == "md":
        return Response(
            renderizar_markdown(dados),
            mimetype="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="dossie-alerta-{alerta_id}.md"'
                ),
            },
        )
    if formato == "pdf":
        return Response(
            renderizar_pdf(dados),
            mimetype="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="dossie-alerta-{alerta_id}.pdf"'
                ),
            },
        )
    return jsonify(serializar_json(dados))
