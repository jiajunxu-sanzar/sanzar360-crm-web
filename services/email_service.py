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


def _deliver_smtp_message(msg: EmailMessage, cfg: SmtpDeliveryConfig) -> None:
    with smtplib.SMTP(cfg.host, cfg.port) as smtp:
        if cfg.use_tls:
            smtp.starttls()
        if cfg.password:
            smtp.login(cfg.user, cfg.password)
        smtp.send_message(msg)


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
    _deliver_smtp_message(msg, cfg)


def send_html_email(
    to: str,
    subject: str,
    html: str,
    *,
    plain_fallback: str = "",
    inline_images: dict[str, tuple[bytes, str]] | None = None,
    delivery: SmtpDeliveryConfig | None = None,
) -> None:
    """Envía un correo HTML (con texto plano de respaldo) y opcionalmente
    imágenes incrustadas dentro del propio correo (no enlaces externos).

    ``inline_images`` es un dict ``{cid: (bytes, subtipo_mime)}`` (p. ej.
    ``{"logo": (b"...", "png")}``); el HTML debe referenciarlas como
    ``<img src="cid:logo">``. Usado por la newsletter; ``send_email`` (texto
    plano) sigue igual para el envío individual existente.
    """
    cfg = delivery or default_smtp_from_config()
    if not cfg.host or not cfg.user:
        raise RuntimeError("SMTP no está configurado.")
    msg = EmailMessage()
    msg["From"] = cfg.user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(
        plain_fallback or "Este correo contiene contenido HTML. Ábrelo con un cliente de correo compatible."
    )
    msg.add_alternative(html, subtype="html")
    if inline_images:
        html_part = msg.get_payload()[-1]
        for cid, (data, subtype) in inline_images.items():
            html_part.add_related(data, maintype="image", subtype=subtype, cid=f"<{cid}>")
    _deliver_smtp_message(msg, cfg)
