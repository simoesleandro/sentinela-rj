# Detectores de anomalia — Sentinela RJ

Este documento descreve **como cada detector funciona**: o que procura, o método
estatístico ou cadastral que usa, os **limiares reais** aplicados no código, como
calibra a severidade e qual o **fundamento legal** que motiva o sinal.

## Princípios

- **Indício, não acusação.** Nenhum detector afirma irregularidade. Todos apontam
  *padrões que merecem verificação humana*. Um contrato sinalizado pode ter
  justificativa legal completa.
- **Explicabilidade por construção.** Todo alerta carrega um campo `metodologia`
  preenchido pelo próprio detector, com os números que dispararam o sinal (limiar,
  z-score, janela, valores). O usuário sempre consegue reconstruir *por que* aquilo
  foi marcado.
- **Calibração empírica.** Os limiares foram ajustados contra dados reais do PNCP
  do município do Rio para reduzir falsos positivos (ex.: compras farmacêuticas
  rotineiras não sobem para "alta"; construtoras com poucos contratos de alto valor
  sobem).

Os detectores são registrados em [`analisador/engine.py`](../analisador/engine.py)
e executados em cascata. Cada um devolve `AnomaliaResult` com `tipo`, `severidade`
(`baixa`/`media`/`alta`), `score` (0–1), `metodologia`, `metricas` e `valor_referencia`.

### Severidade vs. score de priorização

Cada detector define uma **severidade** e um **score interno**. A ordenação da fila
de triagem, porém, usa um **score composto** unificado
([`analise/score_composto.py`](../analise/score_composto.py)):

```
score_composto = 0,35 × score_detector
               + peso_severidade (alta=0,40 · media=0,25 · baixa=0,10)
               + 0,25 × min(valor / R$ 50M, 1)
```

Assim, valor envolvido e severidade entram na priorização mesmo quando o score bruto
do detector é modesto.

---

## Visão geral

| # | Detector | Tipo(s) de alerta | Fonte de dados | Natureza |
|---|----------|-------------------|----------------|----------|
| 1 | Outlier de valor | `outlier_valor` | Contratos PNCP | Estatístico (IQR + Z) |
| 2 | Concentração de fornecedor | `concentracao_fornecedor` | Contratos PNCP | Temporal |
| 3 | Aceleração contratual | `evolucao_temporal_fornecedor` | Contratos PNCP | Temporal |
| 4 | Contratação sem licitação | `sem_licitacao_inexigibilidade` · `_emergencia` · `_dispensa` | Contratos PNCP | Textual (regex) |
| 5 | Fracionamento por AP | `fracionamento_ap` | Contratos PNCP | Agrupamento |
| 6 | Fracionamento de empenhos | `fracionamento_empenhos` | Transparência RJ | Temporal |
| 7 | Asfalto Fatiado | `asfalto_fatiado` | Contratos PNCP | Agrupamento |
| 8 | Risco de empenho | `contrato_sem_empenho` · `empenho_total_dia_unico` · `empenho_acima_contrato` | PNCP × Transparência RJ | Cruzamento |
| 9 | Anomalias cadastrais | `empresa_inativa` · `capital_social_baixo` · `empresa_jovem_contrato_grande` | BrasilAPI | Cadastral |
| 10 | Sócios em comum | `socio_compartilhado` | BrasilAPI (QSA) | Relacional |
| 11 | Competição fraca | `desconto_zero_licitacao` · `licitacao_itens_desertos` | Licitações PNCP | Estatístico |
| + | Watchlists | definido pelo usuário | Contratos PNCP | Regra manual |

> **Fundamento legal.** As referências abaixo (Lei 14.133/2021, Lei 4.320/1964 etc.)
> indicam o *contexto normativo* que torna cada padrão digno de atenção. Não são um
> enquadramento jurídico — a análise legal cabe aos órgãos de controle.

---

## 1. Outlier de valor — `outlier_valor`

**Arquivo:** [`analisador/outliers.py`](../analisador/outliers.py)

**O que detecta:** contratos com valor estatisticamente atípico *dentro da própria
categoria de processo* (evita comparar uma obra viária com a compra de material de
escritório).

**Método:** IQR de Tukey por `categoria_processo_nome`. Para categorias com menos de
**4 contratos** (`_MIN_AMOSTRA`), usa o IQR global como fallback. Um contrato só é
sinalizado se passar por **dupla confirmação**:

1. valor acima da cerca superior: `valor > Q3 + 1,5 × IQR`;
2. `z-score > 1,0` — porque em distribuições muito assimétricas a média é puxada
   pelos próprios outliers e a cerca sozinha geraria falsos positivos.

**Severidade:** `z ≥ 5` → alta · `z ≥ 3` → média · demais → baixa.

**Base para o "caso real":** o contrato MJRE (R$ 315,9M) foi detectado aqui como
outlier de ~13 desvios-padrão acima da média da categoria.

**Limitações:** depende da qualidade do preenchimento da categoria; categorias muito
pequenas caem no fallback global, menos preciso.

---

## 2. Concentração de fornecedor — `concentracao_fornecedor`

**Arquivo:** [`analisador/concentracao.py`](../analisador/concentracao.py)

**O que detecta:** um fornecedor recebendo muitos contratos, ou muito valor, numa
janela curta.

**Método:** janela deslizante de **90 dias** por fornecedor; procura a janela de
maior score. Filtros mínimos: **≥ 3 contratos** e **total ≥ R$ 1 milhão** (para não
sinalizar compras rotineiras de baixo valor).

```
score = 0,30 × min(qtd/10, 1) + 0,70 × min(total/R$50M, 1)
```

**Severidade:** `score ≥ 0,65` → alta · `≥ 0,35` → média · demais → baixa.

**Limitações:** concentração pode ser legítima (fornecedor único de um insumo
especializado). É um sinal de *volume*, não de irregularidade.

---

## 3. Aceleração contratual — `evolucao_temporal_fornecedor`

**Arquivo:** [`analisador/evolucao_temporal.py`](../analisador/evolucao_temporal.py)

**O que detecta:** fornecedor cuja quantidade de contratos *disparou* na janela
recente comparada ao período anterior equivalente.

**Método:** compara os **90 dias recentes** contra os **90 dias anteriores**.
Dispara com **≥ 4 contratos recentes** (`_MIN_RECENTE`), aumento de **+3 contratos**
(`_MIN_AUMENTO`) e **razão ≥ 2,0** (`_MIN_RAZAO`) entre os períodos.

**Severidade:** `recente ≥ 8 e razão ≥ 3` → alta · `recente ≥ 6 ou razão ≥ 2,5` →
média · demais → baixa.

**Limitações:** crescimento pode refletir sazonalidade ou uma nova frente de trabalho
legítima. Sinaliza *mudança de ritmo*, não causa.

---

## 4. Contratação sem licitação — `sem_licitacao_*`

**Arquivo:** [`analisador/licitacao.py`](../analisador/licitacao.py)

**O que detecta:** contratos firmados sem licitação competitiva, classificados em
três modalidades pelo texto de `informacao_complementar` + `objeto`.

**Método:** casamento por expressões regulares. A ordem importa (emergência é
subconjunto de dispensa e é testada antes):

| Tipo | Fundamento (Lei 14.133/2021) | Limiar alta | Limiar média |
|------|------------------------------|-------------|--------------|
| `inexigibilidade` | Art. 74 — inviabilidade de competição | ≥ R$ 10M | ≥ R$ 1M |
| `emergencia` | Art. 75, VIII — urgência/calamidade | ≥ R$ 5M | ≥ R$ 500K |
| `dispensa` | Art. 75 — dispensa de licitação | ≥ R$ 1M | ≥ R$ 200K |

```
score = base_por_severidade + min(0,25, log10(valor)/40)
```

**Por que importa:** contratação direta é legal e comum, mas concentra risco — é o
caminho por onde passam sobrepreços e direcionamentos quando mal utilizada. O
detector prioriza os casos de **maior valor** dentro de cada modalidade.

**Limitações:** depende de o órgão descrever a modalidade no texto livre; contratos
mal preenchidos podem escapar (falso negativo).

---

## 5. Fracionamento por AP — `fracionamento_ap`

**Arquivo:** [`analisador/fracionamento.py`](../analisador/fracionamento.py)

**O que detecta:** um mesmo serviço dividido entre fornecedores distintos por Áreas
de Planejamento (AP1–AP5) — indício de fracionamento para contornar limites de
licitação.

**Método:** gera um *fingerprint* do objeto (remove menções a "AP", números e stop
words) e agrupa contratos com objeto equivalente. Filtros: **≥ 2 contratos no grupo**,
**≥ 2 fornecedores distintos** e **total ≥ R$ 5 milhões**.

**Severidade:** `total ≥ R$ 50M e ≥ 3 fornecedores` → alta · `total ≥ R$ 10M` →
média · demais → baixa. Gera **um alerta por contrato** do grupo.

**Fundamento:** a Lei 14.133/2021 veda o fracionamento de despesa para fugir da
modalidade licitatória cabível (relacionado ao Art. 75, §1º).

---

## 6. Fracionamento de empenhos — `fracionamento_empenhos`

**Arquivo:** [`analisador/fracionamento_empenhos.py`](../analisador/fracionamento_empenhos.py)

**O que detecta:** um fornecedor recebendo muitos **empenhos pequenos em sequência**
— padrão clássico de fracionamento para driblar tetos de modalidade.

**Método:** janela deslizante de **30 dias** sobre `transparencia_rj_lancamentos`.
Filtros: **≥ 3 empenhos**, **valor médio < R$ 50 mil** (empenhos "pequenos") e
**total ≥ R$ 50 mil**.

```
score = 0,40 × min(qtd/10, 1) + 0,60 × (1 − valor_médio/R$50k)
```

**Severidade:** `score ≥ 0,65` → alta · `≥ 0,35` → média · demais → baixa.

**Diferença para o detector 5:** aqui a evidência vem da **execução orçamentária**
(empenhos na Transparência RJ), não do texto do contrato no PNCP.

---

## 7. Asfalto Fatiado — `asfalto_fatiado`

**Arquivo:** [`analisador/asfalto_fatiado.py`](../analisador/asfalto_fatiado.py)

**O que detecta:** múltiplas empresas ganhando contratos de objeto similar (mesma
obra/serviço) para **APs diferentes no mesmo período** — fracionamento *geográfico*
que dilui o valor por empresa mas que, somado, superaria a obrigatoriedade de
concorrência.

**Método:** agrupa por fingerprint de objeto (APs e números removidos), dentro de uma
janela de **730 dias** (com busca de subgrupo se a janela for excedida). Filtros:
**≥ 2 fornecedores distintos**, **≥ 2 APs distintas** e **total ≥ R$ 10 milhões**.

```
score = 0,50 × min(total/R$500M, 1) + 0,30 × min(APs/5, 1) + 0,20 × min(fornec/5, 1)
```

**Severidade:** `total ≥ R$ 50M e ≥ 3 fornecedores` → alta · `total ≥ R$ 10M` →
média · demais → baixa. Gera **um alerta por grupo** (não por contrato).

**Refinamento:** grupos distintos que cobrem as mesmas APs com descrições de
pavimentação diferentes (ex.: "recapeamento" vs. "pavimento") recebem um aviso extra
de *possível fragmentação por reformulação de objeto*.

**Diferença para o detector 5:** o Asfalto Fatiado exige explicitamente múltiplos
fornecedores em APs distintas e consolida em um único alerta de grupo.

---

## 8. Risco de empenho — `contrato_sem_empenho` · `empenho_total_dia_unico` · `empenho_acima_contrato`

**Arquivo:** [`analisador/empenhos_risk.py`](../analisador/empenhos_risk.py)

Cruza contratos do PNCP com a execução orçamentária (`transparencia_rj_lancamentos`),
casando por `numero_controle_pncp`. São três sinais:

**8.1 `contrato_sem_empenho`** — contrato **≥ R$ 1M** assinado há mais de **60 dias**
(média) ou **180 dias** (alta) sem nenhum empenho publicado. Só dispara para contratos
assinados **dentro da janela de cobertura** dos dados de empenho, para não acusar
ausência por falta de dado histórico. *Indício de obra parada, contrato fantasma ou
suspensão não registrada.* (Exemplo real: MJRE, R$ 315,9M, suspenso judicialmente.)

**8.2 `empenho_total_dia_unico`** — **≥ 95%** do valor contratual empenhado num
**único dia**, para contratos **≥ R$ 10M**. Severidade sempre **alta**. *Pagamento
integral antecipado sem execução parcelada.* (Exemplo real: Bonus Track, R$ 45M.)

**8.3 `empenho_acima_contrato`** — soma dos empenhos **> 110%** do valor contratado.
Severidade sempre **alta**. *Indício de superfaturamento ou aditivos não publicados
no PNCP.*

**Fundamento:** o empenho é a etapa orçamentária que reserva o crédito para a despesa
(Lei 4.320/1964, arts. 58–60), e não pode exceder o valor contratado. Divergências
entre contrato e empenho são o tipo de inconsistência que auditorias procuram.

---

## 9. Anomalias cadastrais — `empresa_inativa` · `capital_social_baixo` · `empresa_jovem_contrato_grande`

**Arquivo:** [`analisador/sancoes.py`](../analisador/sancoes.py)
*(o nome do arquivo é histórico; o conteúdo são os detectores cadastrais)*

Cruza os dados cadastrais da BrasilAPI (`fornecedor_cadastro`) com os contratos:

**9.1 `empresa_inativa`** — fornecedor com situação cadastral **diferente de ATIVA**
(código 2 na Receita) e contratos vigentes. Severidade **alta**, score **1,0** —
contratar com empresa inapta/baixada é o sinal cadastral mais grave.

**9.2 `capital_social_baixo`** — capital social **< 5%** do volume total contratado.
Severidade **média**. Empresa com capital muito abaixo do que movimenta em contratos
públicos merece verificação de capacidade econômica.

**9.3 `empresa_jovem_contrato_grande`** — empresa com **menos de 2 anos** de abertura
na data do primeiro contrato **e volume total > R$ 5 milhões**. Severidade **média**.

**Limitações:** todos dependem da disponibilidade e atualidade do cadastro na
BrasilAPI. Capital baixo e empresa jovem têm explicações legítimas frequentes — são
sinais de *contexto*, de baixa a média prioridade.

---

## 10. Sócios em comum — `socio_compartilhado`

**Arquivo:** [`analisador/socios.py`](../analisador/socios.py)

**O que detecta:** uma mesma pessoa física figurando como sócia em **2 ou mais
fornecedores** contratados — indício de competição aparente entre empresas ligadas.

**Método:** cruza o quadro societário (campo `qsa`/`socios` da BrasilAPI) entre
fornecedores com contratos. Filtra sócios pessoa jurídica (documento com 14 dígitos)
e nomes inválidos. Filtro de valor: **total ≥ R$ 1 milhão**.

**Severidade:** `total ≥ R$ 10M` → alta · demais → média.

**Limitações:** baseado em nome do sócio conforme o cadastro; sócios homônimos
existem. É um ponto de partida para investigar vínculos, não uma prova de conluio.

> **Relacionado, mas separado:** o módulo `conflito_interesse/` cruza sócios de
> fornecedores com **servidores públicos** por nome — ver a
> [tela de Conflito de Interesse](../templates/conflitos_interesse.html), que traz seu
> próprio aviso sobre homônimos.

---

## 11. Competição fraca — `desconto_zero_licitacao` · `licitacao_itens_desertos`

**Arquivo:** [`analisador/competicao.py`](../analisador/competicao.py) ·
**Fonte:** [`extrator/licitacoes.py`](../extrator/licitacoes.py) (certames do PNCP,
modalidades competitivas: pregões e concorrências)

Enquanto os demais detectores olham o contrato assinado, este olha o **certame**:
valor estimado vs. homologado e a situação dos itens.

**11.1 `desconto_zero_licitacao`** — certame competitivo homologado praticamente
no valor estimado. **Calibração empírica (jul/2026, 230 pregões homologados da
PCRJ):** o desconto mediano é **22,6%**; desconto ≤ 0,5% ocorre em só **10%** dos
certames. Dispara com desconto ≤ 0,5% e homologado ≥ R$ 500 mil.
Severidade: ≥ R$ 5M → alta · ≥ R$ 1M → média · demais → baixa.
*É o indicador de "desconto zero" dos painéis do TCU — sugere combinação de
preços ou orçamento direcionado.* (Caso real da calibração: R$ 9,26M em pneus
homologado no centavo exato do estimado.)

**11.2 `licitacao_itens_desertos`** — a **maioria** dos itens do certame deserta
ou fracassada. Calibração: ter *algum* item fracassado é comum (35% das compras
da amostra) — só dispara com proporção ≥ 50%, ≥ 4 itens e estimado ≥ R$ 500 mil.
Severidade alta com proporção ≥ 80% e valor ≥ R$ 5M. *Sugere edital mal
dimensionado, exigência restritiva ou afastamento de competidores — e costuma
preceder contratação direta.*

**Limitação documentada:** a API de consulta do PNCP **não expõe a quantidade de
propostas** recebidas (a lista de licitantes fica no sistema de origem), então
"licitante único" literal não é computável por esta fonte — estes dois sinais são
os proxies disponíveis de ausência de disputa.

---

## Sanções federais — fonte de enriquecimento (CEIS/CNEP)

**Arquivo:** [`extrator/sancoes_api.py`](../extrator/sancoes_api.py) ·
**CLI:** `python __main__.py sancoes-api`

Não é um detector, é uma **fonte de enriquecimento**: alimenta o sinal
`tem_sancao` do fornecedor, que aparece como evidência na triagem, na priorização
de conflito de interesse e reforça os detectores cadastrais.

Consulta a **API do Portal da Transparência** por CNPJ, nos cadastros **CEIS**
(empresas inidôneas e suspensas) e **CNEP** (empresas punidas), usando o filtro
`codigoSancionado`. Pega punições de **qualquer esfera** — federal, estadual ou
municipal — que atinjam um fornecedor que contrata no nosso município (validado
em jul/2026: um fornecedor com impedimento aplicado por prefeitura de outro estado
aparece corretamente).

- **Incremental e resumível**: cada execução checa os N fornecedores verificados
  há mais tempo (coluna `fornecedores.sancoes_verificado_em`); `--limite` e
  `--pausa` controlam o volume e o respeito ao rate limit (~90 req/min).
- **Complementa** o `extrator/sancoes_ingestao.py` (que carrega o CSV nacional
  inteiro): a API é sempre atual, sem hospedar arquivos gigantes, e mira só os
  nossos fornecedores.
- **Requer chave** gratuita (`TRANSPARENCIA_API_KEY`, cadastro em
  portaldatransparencia.gov.br/api-de-dados).

**Limitação documentada:** a página da API é fixa em 15 registros (não dá para
baixar a base nacional de uma vez), por isso a consulta é por CNPJ; e só CNPJs são
checados (CPF sancionado é outra base). CEPIM (empresas impedidas) fica como
extensão futura.

---

## Watchlists — regras definidas pelo usuário

Além dos detectores estatísticos, o usuário pode cadastrar **watchlists** (por
fornecedor, órgão ou palavra-chave no objeto) que geram alertas quando há
correspondência. Não são heurísticas: são regras de vigilância manual, executadas
após a sincronização dos detectores automáticos.

---

## Como um alerta chega à triagem

```
Contrato/empenho/cadastro
        ↓
Detector (este documento) → AnomaliaResult (severidade, score, metodologia)
        ↓
Sincronização de alertas (db/alertas_sync.py)
        ↓
Score composto (analise/score_composto.py) ordena a fila
        ↓
Dashboard → auditor humano decide (confirmar / arquivar / investigar)
```

O detector **nunca** conclui. Ele prepara a evidência, mostra os números que a
sustentam e deixa a decisão para a análise humana.
