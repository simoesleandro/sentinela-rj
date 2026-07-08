# ADR 001 — SQLite no núcleo, Postgres (Supabase) nos domínios de folha e conflito

**Status:** aceita · **Data:** julho/2026

## Contexto

O Sentinela RJ tem dois grupos de dados com perfis muito diferentes:

1. **Núcleo público** — contratos do PNCP, alertas, triagem, watchlists, casos e
   usuários. ~5 mil contratos, escrita concentrada no pipeline agendado
   (1 processo), leitura pelo dashboard público. Deploy no Fly.io.
2. **Folha de pagamento + conflito de interesse** — ~286 mil servidores ativos
   da PCRJ por competência mensal, cruzados com o quadro societário dos
   fornecedores para gerar candidatos a conflito de interesse.

## Decisão

- O **núcleo continua em SQLite** (`data/sentinela_rj.db`), persistido em um
  volume de 1 GB no Fly.io.
- **Folha e conflito de interesse vivem num Postgres gerenciado (Supabase)**,
  separado, acessado via `psycopg2` (`CONFLITO_INTERESSE_DATABASE_URL`).

## Justificativa

**Por que SQLite no núcleo:**

- O padrão de acesso é *um escritor* (pipeline agendado) e *muitos leitores*
  (dashboard) — exatamente o caso de uso em que SQLite é sólido.
- Zero custo, zero operação: backup é copiar um arquivo (`fly sftp`), não há
  servidor de banco para manter, e o deploy inteiro cabe num container + volume.
- O volume de dados (milhares de contratos, não milhões) está ordens de
  grandeza abaixo de qualquer limite prático do SQLite.

**Por que Postgres para folha/conflito:**

- **Escala e carga**: a folha importa centenas de milhares de linhas por
  competência, em lote (`execute_values`) — pesado demais para conviver com o
  SQLite do dashboard num volume de 1 GB.
- **Ciclo de vida próprio**: a importação da folha e o matcher rodam na máquina
  local (CLI `import_folha.py` / `run_matcher.py`), fora do deploy web. Um banco
  gerenciado dá um ponto de encontro entre o ambiente local e o dashboard.
- **Isolamento**: dados nominais de servidores públicos ficam num banco
  separado do banco que alimenta o dashboard aberto — a aplicação web só lê a
  tabela derivada `candidatos_conflito_interesse`.

## Consequências

- Duas conexões e duas variáveis de ambiente (`DB_PATH` e
  `CONFLITO_INTERESSE_DATABASE_URL`).
- A seção de conflitos no dossiê do fornecedor é **best-effort**: se o Postgres
  não estiver configurado/acessível, a página degrada graciosamente sem a seção
  (ver `routes/fornecedores.py`), e `/conflitos-interesse` reporta o erro.
- Testes do domínio conflito usam fakes/SQLite em memória — a suíte não depende
  de Postgres (roda no CI sem segredos).
- Se um dia o dashboard precisar de escrita concorrente ou consultas pesadas no
  núcleo, a migração natural é consolidar tudo no Postgres — decisão adiada de
  propósito até haver necessidade real (ver alertas de overengineering no
  histórico do projeto).
