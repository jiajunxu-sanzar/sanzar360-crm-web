"""Lógica de la newsletter: suscripción, token de baja firmado, y plantilla HTML.

La newsletter reutiliza el motor de envío de ``services/email_service.py``
(``send_html_email``) y el registro de históricos vive en
``services/blogs_service.py`` (``log_newsletter_send`` /
``record_newsletter_unsubscribe``). Este módulo se centra en:

- decidir si un contacto está suscrito (columna ``newsletter_suscrito``);
- generar y verificar el token firmado que va en el enlace de baja público;
- construir el HTML final (logo + imagen + título + párrafo + botón con
  enlace + botón de baja) con las imágenes referenciadas por CID.
"""
from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import html as html_escape
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from config.settings import (
    NEWSLETTER_PUBLIC_BASE_URL,
    NEWSLETTER_SUSCRITO_NO,
    NEWSLETTER_UNSUB_SECRET,
    NO_RECIBIR_EMAILS_SI,
    PROJECT_ROOT,
)

BRANDING_DIR = PROJECT_ROOT / "assets" / "branding"
LOGO_PATH = BRANDING_DIR / "SANZAR_LOGO VERDE.png"
ICON_WEB_PATH = BRANDING_DIR / "icon_web.png"
ICON_LINKEDIN_PATH = BRANDING_DIR / "icon_linkedin.png"

SANZAR_WEB_URL = "https://www.sanzar-group.com/"
SANZAR_LINKEDIN_URL = "https://www.linkedin.com/company/sanzargroup/"


@functools.lru_cache(maxsize=1)
def load_logo_bytes() -> bytes:
    """Bytes del logo de Sanzar (``assets/branding/SANZAR_LOGO VERDE.png``), cacheados."""
    return Path(LOGO_PATH).read_bytes()


@functools.lru_cache(maxsize=1)
def load_web_icon_bytes() -> bytes:
    """Icono web del footer (``assets/branding/icon_web.png``)."""
    return Path(ICON_WEB_PATH).read_bytes()


@functools.lru_cache(maxsize=1)
def load_linkedin_icon_bytes() -> bytes:
    """Icono LinkedIn del footer (``assets/branding/icon_linkedin.png``)."""
    return Path(ICON_LINKEDIN_PATH).read_bytes()


def image_mime_subtype(filename: str, fallback: str = "png") -> str:
    """Subtipo MIME (para ``inline_images`` / data URIs) a partir del nombre de archivo."""
    ext = Path(filename or "").suffix.lower().lstrip(".")
    if ext in {"jpg", "jpeg"}:
        return "jpeg"
    if ext in {"png", "gif", "webp"}:
        return ext
    return fallback


def data_uri(data: bytes, subtype: str) -> str:
    """``data:`` URI para previsualizar imágenes dentro de la app (no vale para
    correos reales de producción: ahí se usan referencias ``cid:`` embebidas)."""
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/{subtype};base64,{encoded}"

# contact_id / newsletter_id usados para los envíos de prueba: nunca deben
# coincidir con un id real, así que un clic accidental en el botón de baja de
# un correo de prueba no puede dar de baja a nadie ni tocar Blogs.
TEST_CONTACT_ID = "__test__"
TEST_NEWSLETTER_ID = "__test__"

SANZAR_GREEN = "#2D6A4F"


def is_newsletter_subscribed(contact_row: dict[str, str]) -> bool:
    """True salvo que el contacto se haya dado de baja explícitamente.

    Por diseño: celda vacía (contactos creados antes de esta columna) o
    cualquier valor distinto de "no" cuenta como suscrito.
    """
    value = str(contact_row.get("newsletter_suscrito", "") or "").strip().lower()
    return value != NEWSLETTER_SUSCRITO_NO.lower()


def allows_crm_email(contact_row: dict[str, str]) -> bool:
    """False solo si ``no_recibir_emails`` es ``sí`` (opt-out amplio).

    Bloquea correo individual y newsletter. Vacío / ``no`` / otros valores
    permiten envío (contactos antiguos sin la columna).
    """
    value = str(contact_row.get("no_recibir_emails", "") or "").strip().lower()
    return value not in {NO_RECIBIR_EMAILS_SI.lower(), "si", "yes", "true", "1"}


def _sign(contact_id: str, newsletter_id: str) -> str:
    payload = f"{contact_id}:{newsletter_id}".encode("utf-8")
    secret = (NEWSLETTER_UNSUB_SECRET or "sanzar-newsletter-dev-secret").encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()[:24]


def verify_unsubscribe_token(contact_id: str, newsletter_id: str, token: str) -> bool:
    expected = _sign(str(contact_id or ""), str(newsletter_id or ""))
    return hmac.compare_digest(expected, str(token or ""))


def public_base_url_configured() -> bool:
    return bool(NEWSLETTER_PUBLIC_BASE_URL)


def build_unsubscribe_url(contact_id: str, newsletter_id: str) -> str | None:
    """URL pública (sin login) para darse de baja, o ``None`` si falta configurar
    ``APP_PUBLIC_URL`` (la URL pública de la app desplegada)."""
    if not NEWSLETTER_PUBLIC_BASE_URL:
        return None
    token = _sign(contact_id, newsletter_id)
    params = urlencode(
        {
            "newsletter_unsub": "1",
            "cid": contact_id,
            "nid": newsletter_id,
            "t": token,
        }
    )
    return f"{NEWSLETTER_PUBLIC_BASE_URL}/?{params}"


@dataclass(frozen=True)
class NewsletterContent:
    """Contenido de la newsletter.

    ``asunto``: Subject SMTP (bandeja de entrada).
    ``titulo``: H1 visible en el cuerpo HTML.
    """

    asunto: str
    titulo: str
    parrafo: str
    cta_texto: str
    cta_url: str


def newsletter_content_from_historial_row(row: dict[str, str]) -> NewsletterContent:
    """Reconstruye ``NewsletterContent`` desde una fila de HistorialBlog."""
    cta_texto = str(row.get("newsletter_cta_texto", "") or "").strip()
    cta_url = str(row.get("link_boton_newsletter", "") or "").strip()
    boton = str(row.get("boton_newsletter", "") or "").strip().lower()
    if boton in {"no", "n", "0", "false"}:
        cta_texto, cta_url = "", ""
    return NewsletterContent(
        asunto=str(row.get("newsletter_asunto", "") or "").strip(),
        titulo=str(row.get("titulo", "") or "").strip(),
        parrafo=str(row.get("newsletter_texto", "") or row.get("notas", "") or "").strip(),
        cta_texto=cta_texto,
        cta_url=cta_url,
    )


def row_had_newsletter_image(row: dict[str, str]) -> bool:
    return str(row.get("imagen", "") or "").strip().lower() in {"sí", "si", "yes", "y", "1", "true"}


_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_UNDERLINE_RE = re.compile(r"\+\+(.+?)\+\+")


def _paragraph_to_html(parrafo: str) -> str:
    """Convierte Markdown ligero seguro a HTML de correo (sin HTML libre).

    Soporta ``**negrita**``, ``++subrayado++``, ``[texto](https://...)``
    (solo http/https) y saltos de línea → ``<br>``.
    """
    escaped = html_escape.escape(parrafo or "")

    def _link(match: re.Match[str]) -> str:
        # label/url ya vienen escapados del texto completo (evitar doble escape).
        label, url = match.group(1), match.group(2)
        return (
            f'<a href="{url}" style="color:{SANZAR_GREEN};text-decoration:underline;">'
            f"{label}</a>"
        )

    escaped = _LINK_RE.sub(_link, escaped)
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = _UNDERLINE_RE.sub(r"<u>\1</u>", escaped)
    return escaped.replace("\n", "<br>")


def render_newsletter_html(
    content: NewsletterContent,
    *,
    logo_src: str,
    hero_src: str | None,
    unsubscribe_url: str | None,
    icon_web_src: str,
    icon_linkedin_src: str,
) -> str:
    """HTML autocontenido (tablas + estilos inline) para máxima compatibilidad
    con clientes de correo.

    ``logo_src`` / ``hero_src`` / iconos son el atributo ``src`` completo de cada
    imagen: al enviar el correo real se pasan referencias ``cid:...`` (la
    imagen va incrustada en el propio correo, no depende de hosting externo);
    para la vista previa dentro de la app se pasan ``data:`` URIs, ya que un
    iframe de previsualización no tiene forma de resolver un ``cid:``.
    """
    titulo = html_escape.escape(content.titulo or "")
    parrafo_html = _paragraph_to_html(content.parrafo)
    cta_texto = html_escape.escape(content.cta_texto or "")
    cta_url = html_escape.escape(content.cta_url or "", quote=True)
    web_href = html_escape.escape(SANZAR_WEB_URL, quote=True)
    linkedin_href = html_escape.escape(SANZAR_LINKEDIN_URL, quote=True)

    hero_html = (
        f"""
        <tr>
          <td style="padding:0;">
            <img src="{hero_src}" alt="" width="400"
                 style="width:100%;max-width:400px;display:block;border:0;" />
          </td>
        </tr>
        """
        if hero_src
        else ""
    )

    cta_html = (
        f"""
        <tr>
          <td style="padding:8px 32px 32px 32px;">
            <a href="{cta_url}"
               style="display:inline-block;background:{SANZAR_GREEN};color:#ffffff;
                      text-decoration:none;font-weight:600;font-size:15px;
                      padding:12px 26px;border-radius:8px;">
              {cta_texto}
            </a>
          </td>
        </tr>
        """
        if content.cta_texto.strip() and content.cta_url.strip()
        else ""
    )

    if unsubscribe_url:
        unsub_html = (
            f'<a href="{html_escape.escape(unsubscribe_url, quote=True)}" '
            f'style="color:#8a8f98;text-decoration:underline;">Darse de baja</a>'
        )
    else:
        unsub_html = (
            "Para dejar de recibir estos correos, escríbenos a "
            "<a href=\"mailto:info@sanzar-group.com\" style=\"color:#8a8f98;\">info@sanzar-group.com</a>."
        )

    return f"""\
<!DOCTYPE html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{titulo}</title>
  </head>
  <body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="400" cellpadding="0" cellspacing="0"
                 style="background:#ffffff;border-radius:12px;max-width:400px;width:100%;border-collapse:separate;">
            <tr>
              <td style="padding:16px 24px 10px 24px;text-align:center;">
                <img src="{logo_src}" alt="Sanzar" height="50"
                     style="height:50px;width:auto;max-width:120px;display:inline-block;border:0;" />
              </td>
            </tr>
            {hero_html}
            <tr>
              <td style="padding:28px 32px 8px 32px;">
                <h1 style="margin:0;font-size:22px;line-height:1.3;color:#18181b;">{titulo}</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:8px 32px 0 32px;font-size:15px;line-height:1.6;color:#3f3f46;">
                {parrafo_html}
              </td>
            </tr>
            {cta_html}
            <tr>
              <td style="padding:24px 32px 28px 32px;border-top:1px solid #e4e4e7;">
                <p style="margin:0 0 16px 0;font-size:12px;line-height:1.6;color:#8a8f98;">
                  Recibes este correo porque eres un contacto de Sanzar. {unsub_html}
                </p>
                <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;">
                  <tr>
                    <td style="padding:0 8px;">
                      <a href="{web_href}" style="text-decoration:none;">
                        <img src="{icon_web_src}" alt="Web Sanzar" width="28" height="28"
                             style="width:28px;height:28px;display:block;border:0;" />
                      </a>
                    </td>
                    <td style="padding:0 8px;">
                      <a href="{linkedin_href}" style="text-decoration:none;">
                        <img src="{icon_linkedin_src}" alt="LinkedIn Sanzar" width="28" height="28"
                             style="width:28px;height:28px;display:block;border:0;" />
                      </a>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
