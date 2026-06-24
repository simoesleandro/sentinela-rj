"""
Detector "Asfalto Fatiado" — Sentinela RJ.

Padrão: múltiplas empresas distintas ganham contratos com objetos similares
(mesmo tipo de obra/serviço) para Áreas de Planejamento diferentes (AP1-AP5)
no mesmo período. Sinal clássico de fracionamento geográfico que dilui o valor
total abaixo dos limiares de licitação por empresa, mas que em conjunto
superaria a obrigatoriedade de concorrência pública.

Diferente de fracionamento.py: gera UM alerta por grupo (não por contrato)
e exige explicitamente múltiplos fornecedores em APs distintas.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import date, timedelta

from analisador.engine import AnomaliaResult

_AP_RE = re.compile(r'\bAP\s*([1-5])\b', re.IGNORECASE)

_STOP_WORDS = frozenset({
    'a', 'ao', 'aos', 'as', 'com', 'da', 'das', 'de', 'do', 'dos',
    'e', 'em', 'na', 'nas', 'no', 'nos', 'o', 'os', 'ou', 'para',
    'por', 'se', 'um', 'uma',
    # termos de área/localização removidos junto com APs
    'area', 'areas', 'ap', 'zona', 'regiao',
    # termos burocráticos que não diferenciam o serviço
    'contrato', 'servico', 'servicos', 'execucao', 'prestacao',
})

_JANELA_DIAS      = 730
_MIN_FORNECEDORES = 2
_MIN_APS          = 2
_MIN_VALOR        = 10_000_000   # R$ 10M

# palavras-chave que indicam obra de pavimentação — usadas para detectar
# grupos com objetos reformulados cobrindo as mesmas APs
_KW_PAVIMENTACAO = frozenset({
    'recapeamento', 'pavimentacao', 'asfaltica', 'asfaltico', 'asfalto',
    'fresagem', 'pavimento', 'recape', 'tapa-buraco', 'tapaburaco',
})


def _normalizar(texto: str) -> str:
    """Remove APs, números e stop words; retorna fingerprint do serviço."""
    t = texto.lower()
    t = _AP_RE.sub('', t)
    t = re.sub(r'\d+', '', t)
    palavras = [p for p in re.split(r'\W+', t) if len(p) > 2 and p not in _STOP_WORDS]
    return ' '.join(palavras[:10]).strip()


def _extrair_aps(objeto: str) -> list[str]:
    return sorted({f"AP{m.group(1)}" for m in _AP_RE.finditer(objeto)})


def _dentro_da_janela(datas: list[date]) -> bool:
    if len(datas) < 2:
        return True
    return (max(datas) - min(datas)).days <= _JANELA_DIAS


def detectar(conn: sqlite3.Connection) -> list[AnomaliaResult]:
    c = conn.cursor()
    c.execute("""
        SELECT c.numero_controle_pncp, c.objeto, c.valor_global,
               c.fornecedor_ni, c.data_assinatura, c.unidade_nome,
               COALESCE(f.razao_social, c.fornecedor_ni) AS nome_fornecedor
        FROM contratos c
        LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        WHERE c.valor_global > 0
          AND c.objeto IS NOT NULL
          AND c.objeto GLOB '*AP*'
    """)
    rows = [dict(r) for r in c.fetchall()]

    # filtra linhas com ao menos uma AP válida
    rows = [r for r in rows if _extrair_aps(r['objeto'])]

    # agrupa por fingerprint
    grupos: dict[str, list[dict]] = {}
    for r in rows:
        fp = _normalizar(r['objeto'])
        if fp:
            grupos.setdefault(fp, []).append(r)

    resultados: list[AnomaliaResult] = []

    for fingerprint, contratos in grupos.items():
        # filtra pela janela temporal
        datas_validas: list[date] = []
        for c_row in contratos:
            try:
                datas_validas.append(date.fromisoformat(c_row['data_assinatura']))
            except (TypeError, ValueError):
                datas_validas.append(None)

        # usa só contratos com data válida para checar janela
        datas_com_valor = [d for d in datas_validas if d is not None]
        if datas_com_valor and not _dentro_da_janela(datas_com_valor):
            # janela excedida: tenta subgrupos dentro de 365 dias
            contratos = _melhor_subgrupo(contratos, datas_com_valor)
            if not contratos:
                continue

        # métricas do grupo
        distinct_forn: dict[str, str] = {}   # ni → nome
        aps_por_forn:  dict[str, set[str]] = {}
        total_valor = 0.0
        todas_aps:  set[str] = set()
        pncp_ids:   list[str] = []

        for row in contratos:
            ni   = row['fornecedor_ni']
            nome = row['nome_fornecedor']
            aps  = _extrair_aps(row['objeto'])
            distinct_forn[ni] = nome
            aps_por_forn.setdefault(ni, set()).update(aps)
            todas_aps.update(aps)
            total_valor += row['valor_global']
            pncp_ids.append(row['numero_controle_pncp'])

        n_fornec = len(distinct_forn)
        n_aps    = len(todas_aps)

        if n_fornec < _MIN_FORNECEDORES or n_aps < _MIN_APS or total_valor < _MIN_VALOR:
            continue

        # score composto
        score_valor  = min(total_valor / 500_000_000, 1.0)   # R$500M = 1.0
        score_aps    = min(n_aps / 5, 1.0)                    # 5 APs = 1.0
        score_frag   = min(n_fornec / 5, 1.0)                 # 5 fornecedores = 1.0
        score = round(0.50 * score_valor + 0.30 * score_aps + 0.20 * score_frag, 3)

        if total_valor >= 50_000_000 and n_fornec >= 3:
            severidade = 'alta'
        elif total_valor >= 10_000_000:
            severidade = 'media'
        else:
            severidade = 'baixa'

        # breakdown por fornecedor para a descrição
        linhas_bd = []
        for ni, nome in sorted(distinct_forn.items(), key=lambda x: -sum(
            r['valor_global'] for r in contratos if r['fornecedor_ni'] == x[0]
        )):
            aps_str    = '+'.join(sorted(aps_por_forn[ni]))
            valor_forn = sum(r['valor_global'] for r in contratos if r['fornecedor_ni'] == ni)
            linhas_bd.append(f"  • {nome[:40]}: {aps_str}  R${valor_forn:,.0f}")

        aps_lista = ', '.join(sorted(todas_aps))
        descricao = (
            f"Asfalto Fatiado: {n_fornec} fornecedores dividiram R${total_valor:,.0f} "
            f"em contratos de '{fingerprint[:60]}' nas {aps_lista}.\n"
            + '\n'.join(linhas_bd)
        )
        metodologia = (
            f"Agrupamento por fingerprint de objeto (APs e números removidos). "
            f"Janela temporal: {_JANELA_DIAS} dias. "
            f"Score = 0,50×(valor/R$500M) + 0,30×(APs/5) + 0,20×(fornec/5). "
            f"Filtros: ≥{_MIN_FORNECEDORES} fornecedores, ≥{_MIN_APS} APs distintas, "
            f"total ≥ R${_MIN_VALOR:,.0f}."
        )
        titulo = (
            f"Asfalto Fatiado: {n_fornec} empresas, {aps_lista} — "
            f"R${total_valor/1_000_000:.0f}M"
        )

        resultados.append(AnomaliaResult(
            tipo='asfalto_fatiado',
            severidade=severidade,
            score=score,
            titulo=titulo,
            descricao=descricao,
            metodologia=metodologia,
            contratos=pncp_ids,
            metricas={
                'n_fornecedores': n_fornec,
                'n_aps': n_aps,
                'aps_cobertas': sorted(todas_aps),
                'total_valor': round(total_valor, 2),
                'n_contratos': len(contratos),
                'fingerprint': fingerprint,
                'score_valor': round(score_valor, 3),
                'score_aps': round(score_aps, 3),
                'score_fragmentacao': round(score_frag, 3),
            },
            valor_referencia=total_valor,
        ))

    _marcar_sobreposicao_reformulada(resultados)
    return resultados


def _sem_acento(s: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )


def _kw_pavimentacao(fingerprint: str) -> set[str]:
    """Retorna quais palavras-chave de pavimentação aparecem no fingerprint."""
    palavras = {_sem_acento(p) for p in re.split(r'\W+', fingerprint.lower())}
    return palavras & _KW_PAVIMENTACAO


def _marcar_sobreposicao_reformulada(resultados: list[AnomaliaResult]) -> None:
    """
    Compara pares de grupos: se compartilham ≥1 AP e ≥1 palavra-chave de
    pavimentação, ambos recebem aviso de possível fragmentação por reformulação.
    Muta metodologia in-place (AnomaliaResult é dataclass não-frozen).
    """
    aviso = (
        "⚠️ Possível fragmentação por reformulação de objeto — "
        "grupos distintos cobrem as mesmas APs com descrições diferentes."
    )
    n = len(resultados)
    marcados: set[int] = set()

    for i in range(n):
        for j in range(i + 1, n):
            aps_i = set(resultados[i].metricas.get('aps_cobertas', []))
            aps_j = set(resultados[j].metricas.get('aps_cobertas', []))
            if not aps_i & aps_j:
                continue

            # basta que AMBOS os grupos sejam de pavimentação (≥1 keyword cada),
            # não é necessário compartilharem a keyword exata — objetos distintos
            # usam termos como "recapeamento" vs "pavimento" para o mesmo serviço
            kw_i = _kw_pavimentacao(resultados[i].metricas.get('fingerprint', ''))
            kw_j = _kw_pavimentacao(resultados[j].metricas.get('fingerprint', ''))
            if not kw_i or not kw_j:
                continue

            marcados.add(i)
            marcados.add(j)

    for idx in marcados:
        r = resultados[idx]
        if aviso not in r.metodologia:
            r.metodologia = r.metodologia + " " + aviso


def _melhor_subgrupo(contratos: list[dict], datas: list[date]) -> list[dict]:
    """Quando o grupo excede a janela, encontra o subgrupo mais valioso dentro de 365 dias."""
    melhor: list[dict] = []
    melhor_valor = 0.0

    for i, ancora in enumerate(datas):
        limite = ancora + timedelta(days=_JANELA_DIAS)
        sub = [c for c, d in zip(contratos, datas) if d is not None and ancora <= d <= limite]
        if len(sub) < 2:
            continue
        valor = sum(r['valor_global'] for r in sub)
        if valor > melhor_valor:
            melhor_valor = valor
            melhor = sub

    return melhor
