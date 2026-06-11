"""Motivos estruturados ao descartar alertas (feedback de falso positivo)."""
from __future__ import annotations

import re

MOTIVOS_FALSO_POSITIVO: dict[str, str] = {
    "valor_rotineiro": "Valor rotineiro para a categoria",
    "categoria_diferente": "Categoria/objeto não se aplica ao detector",
    "dados_incompletos": "Dados insuficientes ou inconsistentes",
    "duplicado": "Alerta duplicado ou já investigado",
    "outro": "Outro motivo",
}

_MOTIVO_RE = re.compile(r"\[FP:([a-z_]+)\]")


def formatar_nota_descarte(motivo: str, nota: str | None = None) -> str:
    """Prefixa nota com código estruturado do motivo."""
    codigo = motivo.strip().lower()
    if codigo not in MOTIVOS_FALSO_POSITIVO:
        raise ValueError(f"Motivo de descarte inválido: '{motivo}'.")
    texto = (nota or "").strip()
    prefixo = f"[FP:{codigo}]"
    return f"{prefixo} {texto}".strip() if texto else prefixo


def extrair_motivo_descarte(nota: str | None) -> str | None:
    """Extrai código do motivo de uma nota de histórico."""
    if not nota:
        return None
    match = _MOTIVO_RE.search(nota)
    return match.group(1) if match else None
