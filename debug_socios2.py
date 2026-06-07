from db.conexao import get_conn
import json

conn = get_conn()
conn.row_factory = __import__('sqlite3').Row

rows = conn.execute("""
    SELECT fc.fornecedor_ni, fc.socios, f.razao_social,
           COUNT(c.numero_controle_pncp) as total_contratos,
           COALESCE(SUM(c.valor_global), 0) as valor_total
    FROM fornecedor_cadastro fc
    JOIN fornecedores f ON f.ni = fc.fornecedor_ni
    JOIN contratos c ON c.fornecedor_ni = fc.fornecedor_ni
    WHERE fc.socios IS NOT NULL AND fc.socios != '[]'
    GROUP BY fc.fornecedor_ni
""").fetchall()

print(f"Rows retornadas: {len(rows)}")

nome_map = {}
for row in rows:
    ni = row["fornecedor_ni"]
    razao = row["razao_social"] or ni
    valor = row["valor_total"] or 0
    try:
        lista = json.loads(row["socios"])
    except Exception as e:
        print(f"JSON error {ni}: {e}")
        continue
    vistos = set()
    for s in lista:
        nome = (s.get("nome_socio") or "").strip()
        cpf_raw = str(s.get("cnpj_cpf_do_socio") or "")
        digitos = "".join(c for c in cpf_raw if c.isdigit())
        if not nome or len(nome) < 5 or len(digitos) == 14:
            continue
        if ni in vistos:
            continue
        vistos.add(ni)
        if nome not in nome_map:
            nome_map[nome] = []
        nome_map[nome].append({"ni": ni, "razao_social": razao, "valor_total": valor})

compartilhados = {n: v for n, v in nome_map.items() if len(v) >= 2}
print(f"Socios compartilhados antes do filtro valor: {len(compartilhados)}")
for nome, forn in compartilhados.items():
    vt = sum(f["valor_total"] for f in forn)
    print(f"  {nome}: {len(forn)} empresas, R$ {vt:,.0f}")

conn.close()
