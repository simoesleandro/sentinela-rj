"""Envio de emails transacionais via Brevo (API HTTP).

Usado para confirmação de cadastro. Em desenvolvimento, se BREVO_API_KEY não
estiver definida, apenas registra o link no console (não envia nada).

Variáveis de ambiente:
- BREVO_API_KEY        — chave da API Brevo (obrigatória em produção).
- EMAIL_REMETENTE      — email remetente VERIFICADO no Brevo (ex.: seu Gmail).
- EMAIL_REMETENTE_NOME — nome de exibição (default: "Sentinela RJ").
"""
import logging
import os

import requests

logger = logging.getLogger(__name__)

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class EmailError(Exception):
    """Falha ao enviar email."""


def email_configurado() -> bool:
    return bool(os.getenv("BREVO_API_KEY", "").strip())


def _remetente() -> dict:
    return {
        "name": os.getenv("EMAIL_REMETENTE_NOME", "Sentinela RJ"),
        "email": os.getenv("EMAIL_REMETENTE", "").strip(),
    }


def enviar_confirmacao(destinatario: str, nome: str | None, link: str) -> bool:
    """Envia o email de confirmação de cadastro. Retorna True se enviado.

    Sem BREVO_API_KEY (dev), loga o link e retorna False (não enviado).
    """
    nome = nome or destinatario
    if not email_configurado():
        logger.warning(
            "BREVO_API_KEY ausente — email NÃO enviado. "
            "Link de confirmação para %s: %s",
            destinatario,
            link,
        )
        print(f"[email] (dev) Link de confirmação p/ {destinatario}: {link}", flush=True)
        return False

    remetente = _remetente()
    if not remetente["email"]:
        raise EmailError(
            "EMAIL_REMETENTE não definido (precisa ser um remetente verificado no Brevo)."
        )

    html = f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:480px;margin:auto">
      <h2 style="color:#2563eb">🛰️ Sentinela RJ</h2>
      <p>Olá, {nome}!</p>
      <p>Confirme seu email para liberar as investigações por IA no Sentinela RJ.</p>
      <p style="margin:24px 0">
        <a href="{link}" style="background:#2563eb;color:#fff;padding:12px 22px;
           border-radius:8px;text-decoration:none;font-weight:600">
          Confirmar meu email
        </a>
      </p>
      <p style="color:#666;font-size:13px">
        Ou copie e cole este link no navegador:<br>{link}
      </p>
      <p style="color:#999;font-size:12px">O link expira em 24 horas.</p>
    </div>
    """
    payload = {
        "sender": remetente,
        "to": [{"email": destinatario, "name": nome}],
        "subject": "Confirme seu cadastro no Sentinela RJ",
        "htmlContent": html,
    }
    headers = {
        "api-key": os.getenv("BREVO_API_KEY", "").strip(),
        "content-type": "application/json",
        "accept": "application/json",
    }
    try:
        resp = requests.post(_BREVO_URL, json=payload, headers=headers, timeout=15)
    except requests.RequestException as exc:
        raise EmailError(f"Falha de conexão com o Brevo: {exc}") from exc
    if resp.status_code >= 300:
        raise EmailError(
            f"Brevo respondeu {resp.status_code}: {resp.text[:300]}"
        )
    logger.info("Email de confirmação enviado para %s", destinatario)
    return True
