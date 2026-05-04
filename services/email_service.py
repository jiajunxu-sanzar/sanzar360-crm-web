from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage

from app.smtp_profiles import SmtpDeliveryConfig, default_smtp_from_config
from config.settings import TEMPLATE_LABEL_ALIASES

PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


def placeholders(text: str) -> set[str]:
    return {match.group(1).strip() for match in PLACEHOLDER_RE.finditer(text or "")}


def validate_placeholders(text: str) -> list[str]:
    return sorted([name for name in placeholders(text) if name not in TEMPLATE_LABEL_ALIASES])


def render_template(text: str, contact: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        column = TEMPLATE_LABEL_ALIASES.get(label, label)
        return str(contact.get(column, ""))

    return PLACEHOLDER_RE.sub(repl, text or "")


def smtp_exception_user_message(exc: BaseException, *, routed_profile_slug: str | None) -> str:
    """Mensaje en castellano para fallos SMTP (autenticación, red, etc.)."""
    perfil = (
        f"El perfil SMTP «{routed_profile_slug}» (p. ej. cuenta de Jiajun o Kabir)"
        if routed_profile_slug
        else "La cuenta SMTP configurada para esta app"
    )
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return (
            f"{perfil} no pudo autenticarse: el servidor rechazó usuario o contraseña. "
            "Revisa la contraseña de aplicación del proveedor (en Gmail, no uses la contraseña normal de la cuenta). "
            "Si el error persiste, comprueba en secrets / .env que host, puerto y TLS coincidan con tu proveedor."
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return f"{perfil} rechazó el destinatario. Comprueba que la dirección de correo del contacto sea válida."
    if isinstance(exc, smtplib.SMTPException):
        return f"{perfil} devolvió un error al enviar: {exc}"
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return (
            f"No hubo conexión con el servidor SMTP de {perfil}. "
            "Comprueba host, puerto, firewall y que el servicio de correo permita SMTP."
        )
    if isinstance(exc, ssl.SSLError):
        return f"Error de cifrado (TLS/SSL) con el servidor SMTP. {perfil}: revisa use_tls / puerto."
    return f"{perfil} — error al enviar: {exc}"


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    delivery: SmtpDeliveryConfig | None = None,
) -> None:
    cfg = delivery or default_smtp_from_config()
    if not cfg.host or not cfg.user:
        raise RuntimeError("SMTP no está configurado.")
    msg = EmailMessage()
    msg["From"] = cfg.user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(cfg.host, cfg.port) as smtp:
        if cfg.use_tls:
            smtp.starttls()
        if cfg.password:
            smtp.login(cfg.user, cfg.password)
        smtp.send_message(msg)
