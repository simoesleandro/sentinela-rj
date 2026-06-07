from db.conexao import get_conn
from analisador import socios
import json

conn = get_conn()

# Testar o filtro PF/PJ manualmente
rows = conn.execute(
    "SELECT fc.fornecedor_ni, fc.socios FROM fornecedor_cadastro fc "
    "JOIN contratos c ON c.fornecedor_ni = fc.fornecedor_ni "
    "WHERE fc.socios IS NOT NULL AND fc.socios != '[]' "
    "GROUP BY fc.fornecedor_ni"
).fetchall()

nome_para_fornecedores = {}
for row in rows:
    ni = row[0]
    lista = json.loads(row[1])
    for s in lista:
        nome = (s.get('nome_socio') or '').strip()
        cpf_raw = str(s.get('cnpj_cpf_do_socio') or '')
        digitos = ''.join(c for c in cpf_raw if c.isdigit())
        is_pj = len(digitos) == 14
        if not nome or len(nome) < 5 or is_pj:
            continue
        if nome not in nome_para_fornecedores:
            nome_para_fornecedores[nome] = []
        if ni not in nome_para_fornecedores[nome]:
            nome_para_fornecedores[nome].append(ni)

compartilhados = {n: v for n, v in nome_para_fornecedores.items() if len(v) >= 2}
print(f"Nomes em 2+ fornecedores: {len(compartilhados)}")
for nome, nis in list(compartilhados.items())[:10]:
    print(f"  {nome}: {nis}")

conn.close()
