"""Fornecedores e rede — ranking, dossiê, comparador, órgãos, grafo e sócios."""
import json

from flask import Blueprint, jsonify, request

import web_app as core
from routes.conflitos import _serializar_candidato_conflito

bp = Blueprint("fornecedores", __name__)


# ---------------------------------------------------------------------------
# Fornecedores ranking
# ---------------------------------------------------------------------------
def _calcular_score(
    alertas_count: int,
    valor_total: float,
    severidades: list[str],
    tipos: list[str],
) -> float:
    if alertas_count == 0:
        return 0.0
    severity_sum = sum(3 if s == "alta" else 2 if s == "media" else 1 for s in severidades)
    type_diversity = len(set(tipos))
    valor_factor = min(valor_total / 100_000_000, 3.0)
    raw = severity_sum + type_diversity + valor_factor
    return min(round(raw, 1), 10.0)


@bp.route("/api/fornecedores/ranking")
def fornecedores_ranking():
    db = core.get_db()
    try:
        limit = min(100, max(1, int(request.args.get("limit", 10))))
        orderby = request.args.get("orderby", "valor")
        order_col = "total_contratos" if orderby == "contratos" else "valor_total"
        q = request.args.get("q", "").strip()

        ranking_conditions = ["c.valor_global > 0"]
        ranking_params: list = []
        ibge = core._municipio_ibge_request()
        join_o = ""
        if ibge:
            join_o = "JOIN orgaos o ON o.cnpj = c.orgao_cnpj"
            core._aplicar_filtro_municipio(ranking_conditions, ranking_params, ibge)
        if q:
            cnpj_q = q.replace(".", "").replace("/", "").replace("-", "")
            ranking_conditions.append("(f.razao_social LIKE ? OR f.ni LIKE ?)")
            ranking_params.extend([f"%{q}%", f"%{cnpj_q}%"])

        ranking_where = "WHERE " + " AND ".join(ranking_conditions)

        rows = db.execute(
            f"""
            SELECT c.fornecedor_ni,
                   f.razao_social AS fornecedor,
                   COUNT(*) AS total_contratos,
                   SUM(c.valor_global) AS valor_total,
                   COUNT(DISTINCT a.id) AS alertas,
                   COALESCE(f.tem_sancao, 0) AS tem_sancao
            FROM contratos c
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN alertas a ON a.numero_controle_pncp = c.numero_controle_pncp
            {join_o}
            {ranking_where}
            GROUP BY c.fornecedor_ni
            ORDER BY {order_col} DESC
            LIMIT ?
            """,
            ranking_params + [limit],
        ).fetchall()

        items = []
        for r in rows:
            item = dict(r)
            item["tem_sancao"] = bool(item.get("tem_sancao"))
            alert_rows = db.execute(
                """
                SELECT a.severidade, a.tipo
                FROM alertas a
                LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
                WHERE c.fornecedor_ni = ?
                """,
                (item["fornecedor_ni"],),
            ).fetchall()
            severidades = [ar["severidade"] for ar in alert_rows]
            tipos = [ar["tipo"] for ar in alert_rows]
            score = _calcular_score(item["alertas"], item["valor_total"] or 0, severidades, tipos)
            item["risk_score"] = score
            item["risk_label"] = (
                "CRÍTICO" if score >= 8 else
                "ALTO"    if score >= 6 else
                "MÉDIO"   if score >= 4 else
                "BAIXO"
            )
            item["risk_color"] = (
                "#ef4444" if score >= 8 else
                "#f97316" if score >= 6 else
                "#eab308" if score >= 4 else
                "#22c55e"
            )
            items.append(item)

        items.sort(key=lambda x: x["risk_score"], reverse=True)
        return jsonify({"items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fornecedor — dossier
# ---------------------------------------------------------------------------
@bp.route("/api/fornecedores/investigados")
def fornecedores_investigados():
    """Fornecedores com alertas no Sentinela — catálogo para o comparador."""
    db = core.get_db()
    try:
        q = request.args.get("q", "").strip()
        ibge = core._municipio_ibge_request()
        params: list = []
        filtro_forn = ""
        filtro_mun_c = ""
        filtro_mun_a = ""
        if ibge:
            filtro_mun_c = "AND o.municipio_ibge = ?"
            filtro_mun_a = "AND o.municipio_ibge = ?"
            params.extend([ibge, ibge])
        if q:
            cnpj_q = q.replace(".", "").replace("/", "").replace("-", "")
            filtro_forn = "AND (f.razao_social LIKE ? OR f.ni LIKE ?)"
            params.extend([f"%{q}%", f"%{cnpj_q}%"])
        rows = db.execute(
            f"""
            WITH contratos_agg AS (
                SELECT c.fornecedor_ni,
                       COUNT(*) AS total_contratos,
                       COALESCE(SUM(c.valor_global), 0) AS valor_total
                FROM contratos c
                JOIN orgaos o ON o.cnpj = c.orgao_cnpj
                WHERE c.valor_global > 0 {filtro_mun_c}
                GROUP BY c.fornecedor_ni
            ),
            alertas_agg AS (
                SELECT c.fornecedor_ni,
                       COUNT(DISTINCT a.id) AS total_alertas,
                       COUNT(DISTINCT CASE WHEN a.severidade = 'alta' THEN a.id END) AS alertas_alta
                FROM alertas a
                JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
                JOIN orgaos o ON o.cnpj = c.orgao_cnpj
                WHERE c.valor_global > 0
                  AND COALESCE(a.status, 'aberto') != 'descartado'
                  {filtro_mun_a}
                GROUP BY c.fornecedor_ni
            )
            SELECT f.ni AS fornecedor_ni,
                   f.razao_social AS fornecedor,
                   aa.total_alertas,
                   aa.alertas_alta,
                   ca.total_contratos,
                   ca.valor_total,
                   COALESCE(f.tem_sancao, 0) AS tem_sancao
            FROM fornecedores f
            JOIN alertas_agg aa ON aa.fornecedor_ni = f.ni
            JOIN contratos_agg ca ON ca.fornecedor_ni = f.ni
            WHERE 1=1 {filtro_forn}
            ORDER BY aa.alertas_alta DESC, aa.total_alertas DESC, ca.valor_total DESC, f.razao_social
            """,
            params,
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["tem_sancao"] = bool(item.get("tem_sancao"))
            items.append(item)
        return jsonify({"items": items, "total": len(items)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


@bp.route("/api/fornecedores/comparar")
def fornecedores_comparar():
    from analise.comparador import ComparadorError, montar_comparacao

    nis = request.args.getlist("ni")
    if not nis:
        bruto = request.args.get("nis", "").strip()
        if bruto:
            nis = [p.strip() for p in bruto.replace(";", ",").split(",") if p.strip()]
    if not nis:
        return jsonify({"error": "Informe ao menos dois CNPJs via ?ni= ou ?nis=."}), 400

    db = core.get_db()
    try:
        return jsonify(montar_comparacao(db, nis))
    except ComparadorError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


@bp.route("/api/fornecedores/<fornecedor_ni>")
def fornecedor_dossie(fornecedor_ni: str):
    db = core.get_db()
    try:
        forn = db.execute(
            "SELECT ni, razao_social, tipo_pessoa, tem_sancao, ultima_consulta_sancao FROM fornecedores WHERE ni = ?",
            (fornecedor_ni,),
        ).fetchone()
        if forn is None:
            return jsonify({"error": "not found"}), 404

        contratos_rows = db.execute(
            """
            SELECT c.numero_controle_pncp, c.objeto, c.valor_global,
                   c.data_assinatura, c.data_vigencia_fim,
                   c.categoria_processo_nome AS categoria,
                   o.razao_social AS orgao,
                   EXISTS(
                     SELECT 1 FROM alertas a
                     WHERE a.numero_controle_pncp = c.numero_controle_pncp
                   ) AS tem_alerta
            FROM contratos c
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            WHERE c.fornecedor_ni = ? AND c.valor_global > 0
            ORDER BY c.data_assinatura DESC
            """,
            (fornecedor_ni,),
        ).fetchall()
        contratos = [dict(r) for r in contratos_rows]
        for c in contratos:
            c["tem_alerta"] = bool(c["tem_alerta"])

        total_contratos = len(contratos)
        valor_total = sum(c["valor_global"] or 0 for c in contratos)
        valor_medio = valor_total / total_contratos if total_contratos else 0
        datas = [c["data_assinatura"] for c in contratos if c["data_assinatura"]]

        anomalias_rows = db.execute(
            """
            SELECT a.id, a.tipo, a.severidade, a.descricao,
                   a.valor_referencia AS valor_grupo,
                   c.valor_global AS valor_contrato,
                   a.narrativa_ia, a.numero_controle_pncp,
                   c.objeto, c.data_assinatura
            FROM alertas a
            LEFT JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
            WHERE c.fornecedor_ni = ?
            ORDER BY a.severidade DESC, c.valor_global DESC
            """,
            (fornecedor_ni,),
        ).fetchall()
        anomalias = [dict(r) for r in anomalias_rows]

        alertas_abertos = db.execute(
            """SELECT COUNT(*) FROM alertas a
               JOIN contratos c ON c.numero_controle_pncp = a.numero_controle_pncp
               WHERE c.fornecedor_ni = ?
                 AND COALESCE(a.status, 'aberto') IN ('aberto', 'investigando')""",
            (fornecedor_ni,),
        ).fetchone()[0]

        severidades = [a["severidade"] for a in anomalias]
        tipos_a = [a["tipo"] for a in anomalias]
        risk_score = _calcular_score(len(anomalias), valor_total, severidades, tipos_a)
        risk_label = (
            "CRÍTICO" if risk_score >= 8 else
            "ALTO"    if risk_score >= 6 else
            "MÉDIO"   if risk_score >= 4 else
            "BAIXO"
        )
        risk_color = (
            "#ef4444" if risk_score >= 8 else
            "#f97316" if risk_score >= 6 else
            "#eab308" if risk_score >= 4 else
            "#22c55e"
        )

        orgaos_rows = db.execute(
            """
            SELECT o.razao_social AS orgao, c.orgao_cnpj AS cnpj,
                   COUNT(*) AS total_contratos,
                   SUM(c.valor_global) AS valor_total
            FROM contratos c
            LEFT JOIN orgaos o ON o.cnpj = c.orgao_cnpj
            WHERE c.fornecedor_ni = ? AND c.valor_global > 0
            GROUP BY c.orgao_cnpj
            ORDER BY valor_total DESC
            """,
            (fornecedor_ni,),
        ).fetchall()

        relacionados_rows = db.execute(
            """
            SELECT f2.razao_social AS fornecedor, f2.ni,
                   COUNT(*) AS contratos_comuns,
                   SUM(c2.valor_global) AS valor_total,
                   MAX(c2.objeto) AS objeto_comum
            FROM alertas a1
            JOIN alertas a2 ON a2.tipo = 'fracionamento_ap'
              AND a2.numero_controle_pncp != a1.numero_controle_pncp
              AND a2.descricao LIKE '%' || (
                SELECT SUBSTR(a1.descricao, INSTR(a1.descricao, '—')+2, 60)
              ) || '%'
            JOIN contratos c2 ON c2.numero_controle_pncp = a2.numero_controle_pncp
            JOIN fornecedores f2 ON f2.ni = c2.fornecedor_ni
            WHERE a1.numero_controle_pncp IN (
              SELECT numero_controle_pncp FROM contratos WHERE fornecedor_ni = ?
            )
            AND f2.ni != ?
            GROUP BY f2.ni
            LIMIT 10
            """,
            (fornecedor_ni, fornecedor_ni),
        ).fetchall()

        timeline_rows = db.execute(
            """
            SELECT strftime('%Y-%m', data_assinatura) AS periodo,
                   COUNT(*) AS contratos,
                   SUM(valor_global) AS valor
            FROM contratos
            WHERE fornecedor_ni = ? AND valor_global > 0 AND data_assinatura IS NOT NULL
            GROUP BY periodo
            ORDER BY periodo
            """,
            (fornecedor_ni,),
        ).fetchall()

        cadastro_row = db.execute(
            """
            SELECT situacao_cadastral, descricao_situacao,
                   data_inicio_atividade, cnae_fiscal, cnae_fiscal_descricao,
                   capital_social, porte, natureza_juridica,
                   socios, cnaes_secundarios, municipio, uf, atualizado_em
            FROM fornecedor_cadastro
            WHERE fornecedor_ni = ?
            """,
            (fornecedor_ni,),
        ).fetchone()

        cadastro = dict(cadastro_row) if cadastro_row else None
        if cadastro:
            for campo in ("socios", "cnaes_secundarios"):
                raw = cadastro.get(campo)
                if raw:
                    try:
                        cadastro[campo] = json.loads(raw)
                    except Exception:
                        cadastro[campo] = []

        empenho_agg = db.execute(
            """SELECT COUNT(*) AS total, COALESCE(SUM(valor), 0) AS valor_total
               FROM transparencia_rj_lancamentos
               WHERE fornecedor_ni = ?""",
            (fornecedor_ni,),
        ).fetchone()
        empenhos_recentes = db.execute(
            """SELECT valor, data_lancamento, descricao, orgao, documento
               FROM transparencia_rj_lancamentos
               WHERE fornecedor_ni = ?
               ORDER BY data_lancamento DESC
               LIMIT 10""",
            (fornecedor_ni,),
        ).fetchall()

        return jsonify({
            "identidade": dict(forn),
            "cadastro": cadastro,
            "resumo": {
                "total_contratos": total_contratos,
                "valor_total": valor_total,
                "valor_medio": valor_medio,
                "alertas_abertos": alertas_abertos,
                "primeiro_contrato": min(datas) if datas else None,
                "ultimo_contrato": max(datas) if datas else None,
                "risk_score": risk_score,
                "risk_label": risk_label,
                "risk_color": risk_color,
            },
            "contratos": contratos,
            "anomalias": anomalias,
            "orgaos_contratantes": [dict(r) for r in orgaos_rows],
            "fornecedores_relacionados": [dict(r) for r in relacionados_rows],
            "timeline": {
                "labels": [r["periodo"] for r in timeline_rows],
                "contratos": [r["contratos"] for r in timeline_rows],
                "valor": [r["valor"] for r in timeline_rows],
            },
            "empenhos": {
                "total": empenho_agg["total"],
                "valor_total": empenho_agg["valor_total"],
                "recentes": [dict(r) for r in empenhos_recentes],
            },
            "conflitos_interesse": _listar_conflitos_interesse_fornecedor(fornecedor_ni),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


def _listar_conflitos_interesse_fornecedor(fornecedor_ni: str) -> list[dict]:
    """Candidatos a conflito de interesse para este CNPJ — best-effort: se o
    Postgres de conflito_interesse não estiver configurado/acessível, a
    página de fornecedor continua funcionando normalmente sem essa seção."""
    try:
        conn = core.get_conflito_conn()
    except Exception:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, nome_socio, qualificacao_socio, matricula_servidor,
                   nome_servidor, sigla_ua, score_similaridade, status
            FROM candidatos_conflito_interesse
            WHERE fornecedor_ni = %s
            ORDER BY score_similaridade DESC
            """,
            (fornecedor_ni,),
        )
        colunas = [d[0] for d in cur.description]
        return [
            _serializar_candidato_conflito(dict(zip(colunas, row)))
            for row in cur.fetchall()
        ]
    except Exception:
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Órgãos ranking
# ---------------------------------------------------------------------------
@bp.route("/api/orgaos/ranking")
def orgaos_ranking():
    db = core.get_db()
    try:
        ibge = core._municipio_ibge_request()
        conditions: list[str] = []
        params: list = []
        core._aplicar_filtro_municipio(conditions, params, ibge)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = db.execute(
            f"""
            SELECT o.razao_social AS orgao,
                   o.cnpj,
                   o.municipio_nome,
                   COUNT(DISTINCT c.numero_controle_pncp) AS total_contratos,
                   COALESCE(SUM(c.valor_global), 0) AS valor_total,
                   COUNT(DISTINCT a.id) AS total_alertas,
                   COUNT(DISTINCT CASE WHEN a.severidade='alta' THEN a.id END) AS alertas_alta,
                   COUNT(DISTINCT CASE WHEN a.tipo='outlier_valor' THEN a.id END) AS outliers,
                   COUNT(DISTINCT CASE WHEN a.tipo LIKE 'sem_licitacao%' THEN a.id END) AS sem_licitacao,
                   COUNT(DISTINCT CASE WHEN a.tipo='concentracao_fornecedor' THEN a.id END) AS concentracao,
                   COUNT(DISTINCT CASE WHEN a.tipo='fracionamento_ap' THEN a.id END) AS fracionamento
            FROM orgaos o
            LEFT JOIN contratos c ON c.orgao_cnpj = o.cnpj
            LEFT JOIN alertas a ON a.numero_controle_pncp = c.numero_controle_pncp
            {where}
            GROUP BY o.cnpj
            ORDER BY total_alertas DESC
            """,
            params,
        ).fetchall()
        return jsonify({"items": [dict(r) for r in rows], "municipio_ibge": ibge})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@bp.route("/api/orgaos/<cnpj>/contratos")
def orgaos_contratos(cnpj: str):
    db = core.get_db()
    try:
        rows = db.execute("""
            SELECT c.numero_controle_pncp, c.objeto, c.valor_global,
                   c.data_assinatura, f.razao_social AS fornecedor,
                   COUNT(a.id) AS alertas
            FROM contratos c
            LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
            LEFT JOIN alertas a ON a.numero_controle_pncp = c.numero_controle_pncp
            WHERE c.orgao_cnpj = ?
            GROUP BY c.numero_controle_pncp
            ORDER BY alertas DESC, c.valor_global DESC
            LIMIT 50
        """, (cnpj,)).fetchall()
        return jsonify({"items": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Grafo investigativo
# ---------------------------------------------------------------------------
@bp.route("/api/grafo/fornecedor/<fornecedor_ni>")
def grafo_fornecedor(fornecedor_ni: str):
    from analise.grafo import GrafoNaoEncontradoError, montar_grafo_fornecedor

    db = core.get_db()
    try:
        return jsonify(montar_grafo_fornecedor(db, fornecedor_ni))
    except GrafoNaoEncontradoError:
        return jsonify({"error": "not found"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


@bp.route("/api/grafo/alerta/<int:alerta_id>")
def grafo_alerta(alerta_id: int):
    from analise.grafo import GrafoNaoEncontradoError, montar_grafo_alerta

    db = core.get_db()
    try:
        return jsonify(montar_grafo_alerta(db, alerta_id))
    except GrafoNaoEncontradoError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Rede — sócios compartilhados
# ---------------------------------------------------------------------------
@bp.route("/api/socios/compartilhados")
def socios_compartilhados():
    import json as _json
    import re as _re
    db = core.get_db()
    try:
        ibge = core._municipio_ibge_request()
        conditions = [
            "fc.socios IS NOT NULL",
            "fc.socios != '[]'",
            "ct.valor_global > 0",
        ]
        params: list = []
        if ibge:
            conditions.append("o.municipio_ibge = ?")
            params.append(ibge)
        where = "WHERE " + " AND ".join(conditions)
        rows = db.execute(
            f"""
            SELECT fc.fornecedor_ni,
                   fc.socios,
                   f.razao_social,
                   COUNT(ct.numero_controle_pncp) AS total_contratos,
                   SUM(ct.valor_global)            AS valor_total
            FROM fornecedor_cadastro fc
            JOIN fornecedores f  ON f.ni  = fc.fornecedor_ni
            JOIN contratos ct    ON ct.fornecedor_ni = fc.fornecedor_ni
            JOIN orgaos o ON o.cnpj = ct.orgao_cnpj
            {where}
            GROUP BY fc.fornecedor_ni
            """,
            params,
        ).fetchall()

        re_cnpj = _re.compile(r"^\d{14}$")
        por_socio: dict[str, list[dict]] = {}

        for r in rows:
            try:
                socios = _json.loads(r["socios"])
            except (TypeError, _json.JSONDecodeError):
                continue
            for s in socios:
                nome = (s.get("nome_socio") or "").strip()
                if not nome or nome.lower() == "none" or len(nome) < 5:
                    continue
                doc = _re.sub(r"\D", "", s.get("cnpj_cpf_do_socio") or "")
                if re_cnpj.match(doc):
                    continue
                por_socio.setdefault(nome, []).append({
                    "ni": r["fornecedor_ni"],
                    "razao_social": r["razao_social"] or r["fornecedor_ni"],
                    "valor_total": r["valor_total"] or 0.0,
                    "total_contratos": r["total_contratos"] or 0,
                })

        items = []
        for nome_socio, fornecedores in por_socio.items():
            vistos: set[str] = set()
            forn_unicos = []
            for f in fornecedores:
                if f["ni"] not in vistos:
                    vistos.add(f["ni"])
                    forn_unicos.append(f)

            if len(forn_unicos) < 2:
                continue

            valor_total = sum(f["valor_total"] for f in forn_unicos)
            if valor_total < 1_000_000:
                continue

            total_contratos = sum(f["total_contratos"] for f in forn_unicos)
            items.append({
                "nome_socio": nome_socio,
                "fornecedores": sorted(forn_unicos, key=lambda x: x["valor_total"], reverse=True),
                "total_fornecedores": len(forn_unicos),
                "total_contratos": total_contratos,
                "valor_total": round(valor_total, 2),
                "severidade": "alta" if valor_total >= 10_000_000 else "media",
            })

        items.sort(key=lambda x: x["valor_total"], reverse=True)
        return jsonify({"items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
