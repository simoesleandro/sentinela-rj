"""Casos investigados — página pública e CRUD administrativo."""
import sqlite3

from flask import Blueprint, jsonify, render_template, request

from web_auth import requer_admin

import web_app as core

bp = Blueprint("casos", __name__)


# ---------------------------------------------------------------------------
# Casos investigados — página pública + admin CRUD
# ---------------------------------------------------------------------------
_CASOS_SEED = [
    {
        "titulo": "MJRE Construtora — Suspensão Judicial",
        "fornecedor_nome": "MJRE Construtora Ltda",
        "fornecedor_cnpj": "05851921000181",
        "valor": 315_980_953.18,
        "tipo_anomalia": "outlier_valor",
        "status": "suspenso",
        "resumo": (
            "Contrato de R$ 315.980.953,18 assinado em 23/03/2026 para Fresagem, Recapeamento "
            "Asfáltico e Sinalização Horizontal nas AP1 e AP2 — Programa Asfalto Liso Fase 3. "
            "Onze dias após a assinatura, a 3ª Vara da Fazenda Pública do TJRJ (juíza Mirela "
            "Erbisti) suspendeu o contrato por liminar, após ação apontando que a proposta "
            "vencedora era R$ 25 milhões mais cara do que a concorrente desclassificada. "
            "O Sentinela identificou o valor como outlier severo: 11,4× acima do limite IQR "
            "para a categoria Serviços de Engenharia (Z-score 8,7). Capital social da MJRE "
            "(R$ 16,5 mi) corresponde a apenas 4,6% do volume total contratado pela empresa."
        ),
        "ordem": 1,
    },
    {
        "titulo": "Bonus Track — Inexigibilidade Shows Copacabana",
        "fornecedor_nome": "Bonus Track Produções Ltda",
        "fornecedor_cnpj": "07072702000120",
        "valor": 70_000_000.0,
        "tipo_anomalia": "sem_licitacao_inexigibilidade",
        "status": "investigando",
        "resumo": (
            "Três contratos consecutivos por inexigibilidade (Art. 74, Lei 14.133/2021) "
            "somam R$ 70 milhões: Madonna em Copacabana (R$ 10 mi, abr/2024), Lady Gaga "
            "(R$ 15 mi, abr/2025) e pacote 'Todo Mundo no Rio 2026–2028' (R$ 45 mi, abr/2026) "
            "— três shows anuais a R$ 15 mi cada. O valor exato R$ 45.000.000,00 e a escalada "
            "sistemática de cachês suscitam questionamento sobre a adequação da exclusividade "
            "invocada: a Bonus Track não é produtora das artistas, apenas intermediária. "
            "O conjunto representa padrão de captura de mercado via contratação direta."
        ),
        "ordem": 2,
    },
    {
        "titulo": "Construtora Entre os Rios — Concentração Atípica",
        "fornecedor_nome": "Construtora Entre os Rios Ltda",
        "fornecedor_cnpj": "30307631000119",
        "valor": 86_480_775.04,
        "tipo_anomalia": "concentracao_fornecedor",
        "status": "investigando",
        "resumo": (
            "Quatro contratos com a Prefeitura do Rio em menos de 30 dias (09/03 a 08/04/2026), "
            "todos pelo mesmo órgão contratante, totalizando R$ 86,5 milhões: grama sintética "
            "e alambrados nas AP4/AP5 (R$ 45,9 mi), parque linear na Maré/AP3 (R$ 8,5 mi), "
            "urbanização em Vargem Pequena/AP4 (R$ 14,9 mi) e calçadão de Campo Grande "
            "(R$ 17,3 mi). O detector identificou concentração de 5 contratos em 90 dias "
            "(R$ 86,7 mi). Capital social de R$ 5,5 mi cobre apenas 4,3% do volume contratado "
            "(R$ 126,5 mi acumulados). Evolução de 1 para 4 contratos em 90 dias (×4,0)."
        ),
        "ordem": 3,
    },
    {
        "titulo": "Padrão Asfalto Fatiado — R$ 584mi em Pavimentação",
        "fornecedor_nome": "MJRE, Hydra, Metropolitana, Santa Luzia, Matos Costa",
        "fornecedor_cnpj": None,
        "valor": 584_271_894.23,
        "tipo_anomalia": "fracionamento_ap",
        "status": "investigando",
        "resumo": (
            "Cinco empresas dividiram R$ 584 milhões em contratos de pavimentação asfáltica "
            "distribuídos pelas cinco APs do Rio, firmados entre fev/2026 e mar/2026. "
            "Programa Conservação Fase 2 (R$ 268 mi, 4 empresas): Hydra/AP3 R$ 84,5 mi, "
            "Metropolitana/AP5 R$ 76,6 mi, Santa Luzia/AP4 R$ 60,5 mi, Matos Costa/AP1-2 "
            "R$ 46,7 mi. Programa Asfalto Liso Fase 3 (R$ 316 mi): MJRE/AP1-2 — contrato "
            "suspenso judicialmente. O fracionamento geográfico por AP distribui o objeto "
            "entre concorrências separadas, evitando a modalidade de grande vulto que exigiria "
            "concorrência pública unificada e maior escrutínio."
        ),
        "ordem": 4,
    },
]


def _seed_casos(db: sqlite3.Connection) -> None:
    """Insere os casos iniciais se a tabela estiver vazia."""
    n = db.execute("SELECT COUNT(*) FROM casos").fetchone()[0]
    if n > 0:
        return
    for c in _CASOS_SEED:
        db.execute(
            """INSERT INTO casos (titulo, fornecedor_nome, fornecedor_cnpj, valor,
               tipo_anomalia, status, resumo, ordem)
               VALUES (?,?,?,?,?,?,?,?)""",
            (c["titulo"], c["fornecedor_nome"], c["fornecedor_cnpj"], c["valor"],
             c["tipo_anomalia"], c["status"], c["resumo"], c["ordem"]),
        )
    db.commit()


@bp.route("/casos")
def casos_page():
    db = core.get_db()
    try:
        _seed_casos(db)
        stats_row = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(valor_global),0) FROM contratos WHERE valor_global > 0"
        ).fetchone()
        return render_template(
            "casos.html",
            total_contratos=stats_row[0],
            valor_total=stats_row[1],
        )
    finally:
        db.close()


@bp.route("/admin/casos")
def admin_casos_page():
    return render_template("admin_casos.html")


@bp.route("/api/casos", methods=["GET"])
def api_casos_list():
    db = core.get_db()
    try:
        _seed_casos(db)
        rows = db.execute(
            "SELECT * FROM casos ORDER BY ordem ASC, id ASC"
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@bp.route("/api/casos", methods=["POST"])
@requer_admin
@core.csrf_required
def api_casos_create():
    data = request.get_json(force=True)
    required = ("titulo", "status")
    for field_name in required:
        if not data.get(field_name):
            return jsonify({"error": f"Campo obrigatório: {field_name}"}), 422
    db = core.get_db()
    try:
        cur = db.execute(
            """INSERT INTO casos (titulo, fornecedor_nome, fornecedor_cnpj, valor,
               tipo_anomalia, status, resumo, ordem)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                data["titulo"],
                data.get("fornecedor_nome"),
                data.get("fornecedor_cnpj", "").replace(".", "").replace("/", "").replace("-", "") or None,
                data.get("valor"),
                data.get("tipo_anomalia"),
                data["status"],
                data.get("resumo"),
                int(data.get("ordem", 0)),
            ),
        )
        db.commit()
        row = db.execute("SELECT * FROM casos WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201
    except sqlite3.IntegrityError as e:
        return jsonify({"error": str(e)}), 422
    finally:
        db.close()


@bp.route("/api/casos/<int:caso_id>", methods=["PATCH"])
@requer_admin
@core.csrf_required
def api_casos_update(caso_id: int):
    data = request.get_json(force=True)
    db = core.get_db()
    try:
        row = db.execute("SELECT id FROM casos WHERE id = ?", (caso_id,)).fetchone()
        if not row:
            return jsonify({"error": "Caso não encontrado"}), 404
        fields = ["titulo", "fornecedor_nome", "fornecedor_cnpj", "valor",
                  "tipo_anomalia", "status", "resumo", "ordem"]
        sets, vals = [], []
        for f in fields:
            if f in data:
                v = data[f]
                if f == "fornecedor_cnpj" and v:
                    v = str(v).replace(".", "").replace("/", "").replace("-", "") or None
                sets.append(f"{f} = ?")
                vals.append(v)
        if not sets:
            return jsonify({"error": "Nenhum campo para atualizar"}), 422
        sets.append("atualizado_em = datetime('now')")
        vals.append(caso_id)
        db.execute(f"UPDATE casos SET {', '.join(sets)} WHERE id = ?", vals)
        db.commit()
        updated = db.execute("SELECT * FROM casos WHERE id = ?", (caso_id,)).fetchone()
        return jsonify(dict(updated))
    finally:
        db.close()


@bp.route("/api/casos/<int:caso_id>", methods=["DELETE"])
@requer_admin
@core.csrf_required
def api_casos_delete(caso_id: int):
    db = core.get_db()
    try:
        row = db.execute("SELECT id FROM casos WHERE id = ?", (caso_id,)).fetchone()
        if not row:
            return jsonify({"error": "Caso não encontrado"}), 404
        db.execute("DELETE FROM casos WHERE id = ?", (caso_id,))
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()
