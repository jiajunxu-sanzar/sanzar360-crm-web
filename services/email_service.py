from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage

from config.settings import CONFIG, TEMPLATE_LABEL_ALIASES

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


def send_email(to: str, subject: str, body: str, *, config=CONFIG) -> None:
    if not config.smtp_host or not config.smtp_user:
        raise RuntimeError("SMTP no está configurado.")
    msg = EmailMessage()
    msg["From"] = config.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(config.smtp_host, config.smtp_port) as smtp:
        if config.smtp_use_tls:
            smtp.starttls()
        if config.smtp_password:
            smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(msg)
