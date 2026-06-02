"""
Análise Exploratória — Sentinela RJ
Banco: data/sentinela_rj.db
"""

import sqlite3
import json
from collections import Counter

DB_PATH = r"C:\Users\Leand\.openclaw\workspace\data\sentinela_rj.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

SEP = "=" * 70

# ──────────────────────────────────────────────
# 1. VISÃO GERAL
# ──────────────────────────────────────────────
print(SEP)
print("1. VISÃO GERAL")
print(SEP)

c.execute("SELECT COUNT(*) FROM contratos")
total = c.fetchone()[0]

c.execute("SELECT SUM(valor_global), AVG(valor_global), MIN(valor_global), MAX(valor_global) FROM contratos WHERE valor_global > 0")
soma, media, minv, maxv = c.fetchone()

c.execute("SELECT COUNT(DISTINCT fornecedor_ni) FROM contratos")
n_fornecedores = c.fetchone()[0]

c.execute("SELECT COUNT(DISTINCT orgao_cnpj) FROM contratos")
n_orgaos = c.fetchone()[0]

print(f"Total de contratos : {total}")
print(f"Órgãos distintos   : {n_orgaos}")
print(f"Fornecedores dist. : {n_fornecedores}")
print(f"Valor global total : R$ {soma:,.2f}")
print(f"Valor médio        : R$ {media:,.2f}")
print(f"Menor contrato     : R$ {minv:,.2f}")
print(f"Maior contrato     : R$ {maxv:,.2f}")

# ──────────────────────────────────────────────
# 2. TOP 10 MAIORES CONTRATOS
# ──────────────────────────────────────────────
print(f"\n{SEP}")
print("2. TOP 10 MAIORES CONTRATOS")
print(SEP)

c.execute("""
    SELECT c.numero_controle_pncp,
           c.valor_global,
           c.objeto,
           c.data_assinatura,
           c.categoria_processo_nome,
           c.tipo_contrato_nome,
           f.razao_social as fornecedor,
           c.unidade_nome
    FROM contratos c
    LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
    WHERE c.valor_global > 0
    ORDER BY c.valor_global DESC
    LIMIT 10
""")

for i, row in enumerate(c.fetchall(), 1):
    print(f"\n#{i} — R$ {row['valor_global']:,.2f}")
    print(f"   Fornecedor  : {row['fornecedor'] or 'N/A'}")
    print(f"   Objeto      : {(row['objeto'] or 'N/A')[:120]}")
    print(f"   Órgão       : {row['unidade_nome'] or 'N/A'}")
    print(f"   Assinatura  : {row['data_assinatura']}")
    print(f"   Categoria   : {row['categoria_processo_nome'] or 'N/A'}")
    print(f"   Tipo        : {row['tipo_contrato_nome'] or 'N/A'}")
    print(f"   PNCP ID     : {row['numero_controle_pncp']}")

# ──────────────────────────────────────────────
# 3. FORNECEDORES MAIS FREQUENTES
# ──────────────────────────────────────────────
print(f"\n{SEP}")
print("3. FORNECEDORES MAIS FREQUENTES (TOP 15)")
print(SEP)

c.execute("""
    SELECT f.razao_social as nome, c.fornecedor_ni, COUNT(*) as qtd,
           SUM(c.valor_global) as total,
           AVG(c.valor_global) as media
    FROM contratos c
    LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
    GROUP BY c.fornecedor_ni
    ORDER BY qtd DESC, total DESC
    LIMIT 15
""")

for row in c.fetchall():
    print(f"  {row['qtd']:3d} contrato(s)  R$ {(row['total'] or 0):>15,.2f}  [{row['fornecedor_ni']}] {row['nome'] or 'N/A'}")

# ──────────────────────────────────────────────
# 4. DISTRIBUIÇÃO POR CATEGORIA DE PROCESSO
# ──────────────────────────────────────────────
print(f"\n{SEP}")
print("4. DISTRIBUIÇÃO POR MODALIDADE / CATEGORIA")
print(SEP)

c.execute("""
    SELECT categoria_processo_nome, COUNT(*) as qtd, SUM(valor_global) as total
    FROM contratos
    GROUP BY categoria_processo_nome
    ORDER BY qtd DESC
""")

for row in c.fetchall():
    nome = row['categoria_processo_nome'] or 'Não informado'
    print(f"  {row['qtd']:4d}x  R$ {(row['total'] or 0):>16,.2f}  {nome}")

# ──────────────────────────────────────────────
# 5. CONTRATOS SEM LICITAÇÃO (DISPENSA / INEXIGIBILIDADE)
# ──────────────────────────────────────────────
print(f"\n{SEP}")
print("5. CONTRATOS SEM LICITAÇÃO — DISPENSA / INEXIGIBILIDADE")
print(SEP)

# Buscar por categoria que indique dispensa/inexigibilidade
c.execute("""
    SELECT categoria_processo_nome, COUNT(*) as qtd, SUM(valor_global) as total
    FROM contratos
    WHERE UPPER(categoria_processo_nome) LIKE '%DISPENSA%'
       OR UPPER(categoria_processo_nome) LIKE '%INEXIG%'
       OR UPPER(categoria_processo_nome) LIKE '%EMERGENC%'
       OR UPPER(categoria_processo_id) IN ('2','3','4')
    GROUP BY categoria_processo_nome
    ORDER BY total DESC
""")
rows_sem_lic = c.fetchall()

if rows_sem_lic:
    for row in rows_sem_lic:
        print(f"  {row['qtd']:4d}x  R$ {(row['total'] or 0):>16,.2f}  {row['categoria_processo_nome'] or 'N/A'}")
else:
    print("  Nenhum registro encontrado com termos padrão. Exibindo todas as categorias distintas:")
    c.execute("SELECT DISTINCT categoria_processo_id, categoria_processo_nome FROM contratos ORDER BY categoria_processo_id")
    for row in c.fetchall():
        print(f"    ID={row['categoria_processo_id']}  |  {row['categoria_processo_nome']}")

# ──────────────────────────────────────────────
# 6. OUTLIERS DE VALOR (ANÁLISE ESTATÍSTICA)
# ──────────────────────────────────────────────
print(f"\n{SEP}")
print("6. OUTLIERS DE VALOR (> média + 3× desvio padrão)")
print(SEP)

c.execute("""
    SELECT valor_global FROM contratos WHERE valor_global > 0
""")
valores = [row[0] for row in c.fetchall()]

if valores:
    n = len(valores)
    media_v = sum(valores) / n
    variancia = sum((v - media_v) ** 2 for v in valores) / n
    desvio = variancia ** 0.5
    limiar = media_v + 3 * desvio

    print(f"  Média          : R$ {media_v:,.2f}")
    print(f"  Desvio padrão  : R$ {desvio:,.2f}")
    print(f"  Limiar outlier : R$ {limiar:,.2f}")
    print()

    c.execute("""
        SELECT c.numero_controle_pncp, c.valor_global, c.objeto, c.data_assinatura,
               c.categoria_processo_nome, f.razao_social as fornecedor, c.unidade_nome
        FROM contratos c
        LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
        WHERE c.valor_global > ?
        ORDER BY c.valor_global DESC
    """, (limiar,))

    outliers = c.fetchall()
    print(f"  {len(outliers)} outlier(s) acima do limiar:")
    for row in outliers:
        print(f"\n  [OUTLIER] R$ {row['valor_global']:,.2f}")
        print(f"     Fornecedor : {row['fornecedor'] or 'N/A'}")
        print(f"     Objeto     : {(row['objeto'] or '')[:120]}")
        print(f"     Órgão      : {row['unidade_nome'] or 'N/A'}")
        print(f"     Assinatura : {row['data_assinatura']}")
        print(f"     Categoria  : {row['categoria_processo_nome'] or 'N/A'}")
        print(f"     PNCP ID    : {row['numero_controle_pncp']}")

# ──────────────────────────────────────────────
# 7. MESMO FORNECEDOR — MÚLTIPLOS CONTRATOS
# ──────────────────────────────────────────────
print(f"\n{SEP}")
print("7. CONCENTRAÇÃO — FORNECEDORES COM 3+ CONTRATOS")
print(SEP)

c.execute("""
    SELECT f.razao_social as nome, c.fornecedor_ni, COUNT(*) as qtd,
           SUM(c.valor_global) as total,
           MIN(c.data_assinatura) as primeiro,
           MAX(c.data_assinatura) as ultimo,
           GROUP_CONCAT(DISTINCT c.categoria_processo_nome) as modalidades
    FROM contratos c
    LEFT JOIN fornecedores f ON f.ni = c.fornecedor_ni
    GROUP BY c.fornecedor_ni
    HAVING qtd >= 3
    ORDER BY total DESC
""")

concentrados = c.fetchall()
if concentrados:
    for row in concentrados:
        print(f"\n  [CONCENTRADO] {row['nome'] or 'N/A'}  [{row['fornecedor_ni']}]")
        print(f"     Contratos  : {row['qtd']}  |  Total: R$ {(row['total'] or 0):,.2f}")
        print(f"     Período    : {row['primeiro']} → {row['ultimo']}")
        print(f"     Modalidades: {row['modalidades'] or 'N/A'}")
else:
    print("  Nenhum fornecedor com 3+ contratos.")

# ──────────────────────────────────────────────
# 8. CONTRATOS POR ANO
# ──────────────────────────────────────────────
print(f"\n{SEP}")
print("8. EVOLUÇÃO ANUAL DE CONTRATOS")
print(SEP)

c.execute("""
    SELECT SUBSTR(data_assinatura, 1, 4) as ano,
           COUNT(*) as qtd,
           SUM(valor_global) as total
    FROM contratos
    WHERE data_assinatura IS NOT NULL
    GROUP BY ano
    ORDER BY ano
""")
for row in c.fetchall():
    print(f"  {row['ano']}  |  {row['qtd']:4d} contratos  |  R$ {(row['total'] or 0):>16,.2f}")

# ──────────────────────────────────────────────
# 9. CONTRATOS COM VIGÊNCIA EXPIRADA SEM ENCERRAMENTO
# ──────────────────────────────────────────────
print(f"\n{SEP}")
print("9. CONTRATOS COM VIGÊNCIA JÁ EXPIRADA (mas ainda no banco)")
print(SEP)

c.execute("""
    SELECT COUNT(*) as qtd, SUM(valor_global) as total
    FROM contratos
    WHERE data_vigencia_fim < date('now')
      AND data_vigencia_fim IS NOT NULL
""")
row = c.fetchone()
print(f"  Contratos expirados : {row['qtd']}  |  Valor total: R$ {(row['total'] or 0):,.2f}")

c.execute("""
    SELECT COUNT(*) as qtd, SUM(valor_global) as total
    FROM contratos
    WHERE data_vigencia_fim >= date('now')
      AND data_vigencia_fim IS NOT NULL
""")
row = c.fetchone()
print(f"  Contratos vigentes  : {row['qtd']}  |  Valor total: R$ {(row['total'] or 0):,.2f}")

conn.close()
print(f"\n{SEP}")
print("FIM DA ANÁLISE")
print(SEP)
