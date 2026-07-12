# Product

## Register

product

## Users

- **Primário — jornalista/cidadão**: visitante ocasional do dashboard público (sentinela-rj.fly.dev). Chega sem contexto técnico, precisa entender rápido o que é um alerta, por que um contrato é suspeito e qual a metodologia por trás. Lê no desktop e no celular.
- **Secundário — auditor/fiscal (admin logado)**: faz triagem de alertas (confirmar/descartar), dispara investigações de IA e gerencia casos. Valoriza densidade de informação e fluxo rápido de triagem.
- **Terciário — recrutador técnico**: avalia o projeto como portfólio em poucos minutos; a credibilidade do produto é o argumento.

## Product Purpose

O Sentinela RJ transforma contratos públicos do PNCP em alertas acionáveis: coleta, aplica detectores estatísticos/cadastrais, gera narrativas investigativas com IA e publica tudo em dashboard aberto com API pública. Não substitui o controle institucional — é uma camada de triagem que prioriza e explica indícios para investigação humana. Sucesso = um leitor leigo entende um alerta em segundos e um fiscal reduz pela metade o volume de revisão (precisão medida e publicada em `/precisao`).

## Brand Personality

**Sóbrio, rigoroso, confiável.** Tom institucional de auditoria: o produto afirma indícios, nunca conclusões; publica as próprias taxas de acerto inclusive quando baixas. A credibilidade é o ativo central — a interface deve parecer feita por quem leva evidência a sério.

## Anti-references

- **Painel gov.br burocrático**: portais públicos densos e cinzentos, jargão sem explicação, tabelas ilegíveis.
- **Dashboard SaaS genérico**: grids de cards idênticos, métricas hero com gradiente, cara de template de admin.
- **Sensacionalismo**: vermelhão, exclamações, tom de denúncia. Alarmismo mina a credibilidade dos indícios — severidade se comunica com hierarquia e dado, não com grito.

## Design Principles

1. **Indício, não veredito** — a UI sempre distingue sinal estatístico de conclusão; todo alerta mostra o "porquê" (detector, limiar, fonte) ao lado do "o quê".
2. **Transparência radical** — metodologia, precisão medida e limitações ficam à mostra (como já fazem `/precisao`, `/sobre` e `/dados`); nada de números sem procedência.
3. **Legível para leigo, denso para fiscal** — o caminho público explica; o fluxo de triagem logado prioriza velocidade e densidade sem sacrificar a clareza.
4. **Severidade com sobriedade** — a paleta de risco (vermelho/laranja/amarelo) é semântica e comedida; cor comunica prioridade, nunca drama.
5. **Dado com procedência** — todo valor exibido aponta para a fonte pública (PNCP, TSE, Diário Oficial); links e citações fazem parte do design, não são rodapé.

## Accessibility & Inclusion

- **WCAG AA**: contraste ≥ 4.5:1 no texto de corpo (atenção ao `--muted: #737373` sobre `#0f0f0f` — verificar em novos usos), ≥ 3:1 em texto grande.
- Navegação por teclado nos fluxos de triagem e formulários (login, admin de casos).
- `prefers-reduced-motion` respeitado em qualquer animação nova.
- Severidade nunca comunicada só por cor: sempre acompanhada de rótulo textual (alta/média/baixa).
- Site público lido em mobile: tabelas largas precisam de scroll próprio, nunca estourar o viewport.
