"""
Detector de anomalias no padrão de empenhos vs. contratos — Sentinela RJ.

Três sinais cruzando transparencia_rj_lancamentos com contratos:

1. contrato_sem_empenho
   Contrato com valor > R$1mi assinado há mais de 60 dias sem nenhum empenho
   publicado no PNCP. Indício de obra parada, contrato fantasma ou suspensão
   não registrada. Exemplo real: MJRE R$315,9mi suspenso judicialmente.

2. empenho_total_dia_unico
   100% do valor contratual empenhado em lote único no mesmo dia de publicação.
   Pagamento integral antecipado sem execução parcelada levanta suspeita de
   favorecimento ou serviço fictício. Exemplo real: Bonus Track R$45mi.

3. empenho_acima_contrato
   Soma dos empenhos de um fornecedor para um contrato supera 110% do valor
   contratado. Indica superfaturamento ou aditivos não registrados no PNCP.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from analisador.engine import AnomaliaResult

_MIN_VALOR_CONTRATO   = 1_000_000     # R$1mi — piso para sinal 1
_DIAS_SEM_EMPENHO_MED = 60            # dias → severidade média
_DIAS_SEM_EMPENHO_ALT = 180           # dias → severidade alta
_MIN_VALOR_DIA_UNICO  = 10_000_000    # R$10mi — piso para sinal 2
_RATIO_SUPERFAT       = 1.10          # 110% → superfaturamento


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    resultados: list[AnomaliaResult] = []
    hoje = date.today()

    # ── pré-carrega empenhos agrupados por (fornecedor_ni, documento) ──────
    # documento == numero_controle_pncp quando gravado por empenhos_diarios.py
    emp_rows = conn.execute("""
        SELECT fornecedor_ni, documento, valor, data_lancamento
        FROM transparencia_rj_lancamentos
        WHERE valor IS NOT NULL AND documento IS NOT NULL
    """).fetchall()

    # índice: fornecedor_ni → lista de {documento, valor, data}
    empenhos_por_forn: dict[str, list[dict]] = {}
    for r in emp_rows:
        empenhos_por_forn.setdefault(r[0], []).append({
            "documento": r[1],
            "valor": float(r[2]),
            "data": r[3][:10] if r[3] else None,
        })

    # ── janela de cobertura dos empenhos ───────────────────────────────────
    # Só verifica `contrato_sem_empenho` para contratos assinados APÓS o
    # início da nossa cobertura de empenhos. Contratos anteriores não têm
    # dados suficientes para afirmar ausência de empenho.
    row_cob = conn.execute(
        "SELECT MIN(data_lancamento) FROM transparencia_rj_lancamentos"
    ).fetchone()
    cobertura_inicio: str = (row_cob[0] or "")[:10] if row_cob and row_cob[0] else ""

    # ── carrega contratos elegíveis ─────────────────────────────────────────
    contratos = conn.execute("""
        SELECT c.numero_controle_pncp, c.fornecedor_ni, c.valor_global,
               c.data_assinatura, c.objeto,
               COALESCE(f.razao_social, c.fornecedor_ni) AS nome_fornecedor
        FROM contratos c
        LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        WHERE c.valor_global >= ? AND c.data_assinatura IS NOT NULL
        ORDER BY c.valor_global DESC
    """, (_MIN_VALOR_CONTRATO,)).fetchall()

    for row in contratos:
        pncp      = row[0]
        ni        = row[1]
        valor     = float(row[2])
        data_ass  = row[3][:10]
        objeto    = (row[4] or "")[:80]
        nome      = row[5]

        try:
            dias_desde = (hoje - date.fromisoformat(data_ass)).days
        except ValueError:
            continue

        # empenhos desse fornecedor que referenciam este contrato
        emps_contrato = [
            e for e in empenhos_por_forn.get(ni, [])
            if e["documento"] == pncp
        ]

        # ── SINAL 1: contrato sem empenho ──────────────────────────────────
        # Restringe à janela de cobertura: só acusa se o contrato foi assinado
        # após o início dos dados de empenho — evita falsos positivos por dados
        # históricos ausentes.
        dentro_janela = cobertura_inicio and data_ass >= cobertura_inicio
        if not emps_contrato and dias_desde >= _DIAS_SEM_EMPENHO_MED and dentro_janela:
            if dias_desde >= _DIAS_SEM_EMPENHO_ALT:
                sev = "alta"
                score = round(min(0.9, 0.5 + valor / 200_000_000), 3)
            else:
                sev = "media"
                score = round(min(0.7, 0.3 + valor / 200_000_000), 3)

            resultados.append(AnomaliaResult(
                tipo="contrato_sem_empenho",
                severidade=sev,
                score=score,
                titulo=(
                    f"Contrato sem empenho há {dias_desde}d — "
                    f"{nome[:40]} R${valor/1e6:.1f}mi"
                ),
                descricao=(
                    f"{nome} possui contrato de R${valor:,.0f} assinado em "
                    f"{data_ass} ({dias_desde} dias atrás) sem nenhum empenho "
                    f"publicado no PNCP. Objeto: {objeto}"
                ),
                metodologia=(
                    f"Cruza contratos (valor ≥ R${_MIN_VALOR_CONTRATO:,.0f}) com "
                    f"transparencia_rj_lancamentos por numero_controle_pncp. "
                    f"Sem match há >{dias_desde} dias (limiar média: {_DIAS_SEM_EMPENHO_MED}d, "
                    f"alta: {_DIAS_SEM_EMPENHO_ALT}d)."
                ),
                contratos=[pncp],
                metricas={
                    "dias_desde_assinatura": dias_desde,
                    "valor_contrato": valor,
                    "n_empenhos": 0,
                },
                valor_referencia=valor,
            ))
            continue  # sinais 2 e 3 exigem empenhos — pula

        if not emps_contrato:
            continue

        total_emp = sum(e["valor"] for e in emps_contrato)

        # ── SINAL 2: 100% do valor empenho num dia único ───────────────────
        datas_emp = {e["data"] for e in emps_contrato if e["data"]}
        if len(datas_emp) == 1 and valor >= _MIN_VALOR_DIA_UNICO:
            ratio = total_emp / valor if valor else 0
            if ratio >= 0.95:  # ≥ 95% num dia = lote único
                score = round(min(0.95, 0.6 + valor / 100_000_000), 3)
                data_unica = next(iter(datas_emp))
                resultados.append(AnomaliaResult(
                    tipo="empenho_total_dia_unico",
                    severidade="alta",
                    score=score,
                    titulo=(
                        f"Empenho integral em dia único — "
                        f"{nome[:40]} R${valor/1e6:.1f}mi"
                    ),
                    descricao=(
                        f"{nome} teve R${total_emp:,.0f} ({ratio*100:.0f}% do contrato de "
                        f"R${valor:,.0f}) empenhado em lote único em {data_unica}. "
                        f"Pagamento integral antecipado sem execução parcelada. "
                        f"Objeto: {objeto}"
                    ),
                    metodologia=(
                        f"Agrupa empenhos por data de publicação para o mesmo contrato. "
                        f"Dispara quando ≥95% do valor contratual aparece em uma única data "
                        f"e valor ≥ R${_MIN_VALOR_DIA_UNICO:,.0f}."
                    ),
                    contratos=[pncp],
                    metricas={
                        "valor_contrato": valor,
                        "total_empenhado": round(total_emp, 2),
                        "ratio_empenho": round(ratio, 4),
                        "data_empenho": data_unica,
                        "n_empenhos": len(emps_contrato),
                    },
                    valor_referencia=total_emp,
                ))

        # ── SINAL 3: empenho acima do contrato ─────────────────────────────
        if total_emp > valor * _RATIO_SUPERFAT:
            excesso = total_emp - valor
            ratio = total_emp / valor
            score = round(min(0.98, 0.65 + excesso / 50_000_000), 3)
            resultados.append(AnomaliaResult(
                tipo="empenho_acima_contrato",
                severidade="alta",
                score=score,
                titulo=(
                    f"Empenhos {ratio*100:.0f}% do contrato — "
                    f"{nome[:40]} excesso R${excesso/1e6:.1f}mi"
                ),
                descricao=(
                    f"{nome}: soma dos empenhos R${total_emp:,.0f} supera "
                    f"{ratio*100:.1f}% do valor contratado R${valor:,.0f} "
                    f"(excesso de R${excesso:,.0f}). "
                    f"Indício de superfaturamento ou aditivos não publicados no PNCP. "
                    f"Objeto: {objeto}"
                ),
                metodologia=(
                    f"Soma todos os empenhos vinculados ao contrato por numero_controle_pncp. "
                    f"Dispara quando total_empenhos > {_RATIO_SUPERFAT*100:.0f}% do valor_global."
                ),
                contratos=[pncp],
                metricas={
                    "valor_contrato": valor,
                    "total_empenhado": round(total_emp, 2),
                    "ratio_empenho": round(ratio, 4),
                    "excesso": round(excesso, 2),
                    "n_empenhos": len(emps_contrato),
                },
                valor_referencia=total_emp,
            ))

    return resultados
