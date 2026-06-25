"""Agente investigador ReAct para análise profunda de alertas."""
from __future__ import annotations

import logging
import re
from typing import Any

from .ferramentas.brasilapi_enriquecido import buscar_cadastro_completo
from .ferramentas.pncp_historico import buscar_historico_fornecedor
from .ferramentas.pncp_orgao import buscar_historico_orgao
from .ferramentas.tcm import buscar_decisoes_tcm
from .ferramentas.tjrj import buscar_processos_tjrj
from .resultado import ResultadoInvestigacaoProfunda

logger = logging.getLogger(__name__)

_PROMPT_SINTESE = """Você é um auditor investigativo sênior de contratos públicos.

Receberá dados coletados automaticamente sobre um alerta de anomalia.
Sua tarefa: sintetizar as evidências e emitir uma conclusão objetiva.

DADOS DO ALERTA:
{dados_alerta}

HISTÓRICO DO FORNECEDOR (PNCP):
{historico_fornecedor}

CADASTRO COMPLETO (BrasilAPI):
{cadastro}

HISTÓRICO DO ÓRGÃO (PNCP):
{historico_orgao}

PROCESSOS JUDICIAIS (TJRJ via DataJud):
{processos_tjrj}

DECISÕES TCM-RJ:
{decisoes_tcm}

Com base nesses dados, responda APENAS com o bloco abaixo:

**[Síntese Investigativa]**
<2-4 frases diretas sobre o que os dados revelam>

**[Conclusão]**
Status: <confirmar | arquivar | escalar | inconclusivo>
Grau de confiança: <alto | medio | baixo>
Recomendação: <ação concreta em 1-2 frases>
"""


class AgenteInvestigador:
    """Agente ReAct para investigação profunda de alertas."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def investigar(
        self,
        alerta_id: int,
        dados_alerta: dict[str, Any],
    ) -> ResultadoInvestigacaoProfunda:
        resultado = ResultadoInvestigacaoProfunda(
            alerta_id=alerta_id,
            status="rodando",
        )

        fornecedor_ni = dados_alerta.get("fornecedor_ni") or dados_alerta.get("ni")
        orgao_cnpj = dados_alerta.get("orgao_cnpj")

        print(f"  [Agente] Coletando dados — fornecedor {fornecedor_ni}")

        cadastro: dict[str, Any] = {}
        if fornecedor_ni:
            print("  [Agente] BrasilAPI — cadastro completo...")
            cadastro = buscar_cadastro_completo(fornecedor_ni)
            resultado.evidencias["cadastro"] = cadastro

        historico_fornecedor: dict[str, Any] = {}
        if fornecedor_ni:
            print("  [Agente] PNCP — histórico do fornecedor...")
            historico_fornecedor = buscar_historico_fornecedor(fornecedor_ni)
            resultado.evidencias["historico_fornecedor"] = historico_fornecedor

        historico_orgao: dict[str, Any] = {}
        if orgao_cnpj:
            print("  [Agente] PNCP — histórico do órgão...")
            historico_orgao = buscar_historico_orgao(orgao_cnpj)
            resultado.evidencias["historico_orgao"] = historico_orgao

        processos_tjrj: dict[str, Any] = {}
        if fornecedor_ni:
            print("  [Agente] TJRJ — verificando processos (stub)...")
            fornecedor_nome_busca = (
                dados_alerta.get("fornecedor_nome")
                or dados_alerta.get("razao_social")
                or ""
            )
            processos_tjrj = buscar_processos_tjrj(
                cnpj=fornecedor_ni,
                nome_empresa=fornecedor_nome_busca,
            )
            resultado.evidencias["processos_tjrj"] = processos_tjrj

        decisoes_tcm: dict[str, Any] = {}
        orgao_nome = dados_alerta.get("orgao_nome", "")
        fornecedor_nome_str = (
            dados_alerta.get("fornecedor_nome", "")
            or dados_alerta.get("razao_social", "")
        )
        if fornecedor_nome_str or orgao_nome:
            print("  [Agente] TCM-RJ — decisões de auditoria...")
            decisoes_tcm = buscar_decisoes_tcm(
                orgao_nome=orgao_nome,
                fornecedor_nome=fornecedor_nome_str,
            )
            resultado.evidencias["decisoes_tcm"] = decisoes_tcm

        print("  [Agente] Sintetizando evidências (IA em nuvem: Gemini → Groq)...")
        try:
            from analise.motor_ia import _limpar_latex, gerar_texto

            prompt = _PROMPT_SINTESE.format(
                dados_alerta=str(dados_alerta),
                historico_fornecedor=historico_fornecedor.get("resumo", "Sem dados"),
                cadastro=cadastro.get("resumo", "Sem dados"),
                historico_orgao=historico_orgao.get("resumo", "Sem dados"),
                processos_tjrj=processos_tjrj.get("resumo", "Sem dados"),
                decisoes_tcm=decisoes_tcm.get("resumo", "Sem dados"),
            )
            sintese_raw, prov = gerar_texto(prompt)
            print(f"  [Agente] Síntese gerada por {prov}.")
            resultado.sintese = _limpar_latex(sintese_raw)

            status_match = re.search(
                r"Status:\s*(confirmar|arquivar|escalar|inconclusivo)",
                sintese_raw,
                re.IGNORECASE,
            )
            confianca_match = re.search(
                r"Grau de confiança:\s*(alto|medio|baixo)",
                sintese_raw,
                re.IGNORECASE,
            )
            rec_match = re.search(
                r"Recomendação:\s*(.+?)(?:\n|$)",
                sintese_raw,
                re.IGNORECASE | re.DOTALL,
            )
            resultado.conclusao = (
                status_match.group(1).lower() if status_match else "inconclusivo"
            )
            resultado.grau_confianca = (
                confianca_match.group(1).lower() if confianca_match else "baixo"
            )
            resultado.recomendacao = rec_match.group(1).strip() if rec_match else ""
            resultado.status = "concluida"

        except Exception as exc:
            logger.error("Síntese Gemma4 falhou: %s", exc)
            resultado.status = "erro"
            resultado.erro = str(exc)

        return resultado
