"""Página pública de baja de newsletter — sin login, fuera de la puerta de auth.

Se comprueba desde ``streamlit_app.py`` ANTES del gate de login: si la URL
trae ``?newsletter_unsub=1&cid=...&nid=...&t=...`` con un token válido, se
renderiza esta página mínima y se detiene la ejecución normal de la app.

Al confirmarse la baja:
1. se marca ``newsletter_suscrito=no`` en la fila de ese contacto (Contactos);
2. se anota la baja en la fila de Blogs de ese envío concreto de newsletter;
3. se manda un aviso a ``NEWSLETTER_NOTIFY_EMAIL`` (info@sanzar-group.com) para
   que quede constancia, aunque el punto 1 ya se hace solo (no hace falta que
   nadie lo marque a mano).

Los pasos 2 y 3 son best-effort: si fallan, la baja del punto 1 ya ha quedado
aplicada y el contacto no volverá a salir seleccionable en la newsletter.
"""
from __future__ import annotations

import streamlit as st

from app.cache import blogs_service, sheets_service
from config.settings import NEWSLETTER_NOTIFY_EMAIL, NEWSLETTER_SUSCRITO_NO
from services.email_service import send_email
from services.newsletter_service import (
    TEST_CONTACT_ID,
    TEST_NEWSLETTER_ID,
    verify_unsubscribe_token,
)


def _query_param(name: str) -> str:
    try:
        value = st.query_params.get(name, "")
    except Exception:
        return ""
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def is_unsubscribe_request() -> bool:
    """True si la URL actual es un enlace de baja de newsletter."""
    return _query_param("newsletter_unsub") == "1"


_BOX_COLORS = {
    "error": ("#fef2f2", "#fecaca", "#991b1b"),
    "info": ("#eff6ff", "#bfdbfe", "#1e40af"),
    "success": ("#ecfdf5", "#86efac", "#166534"),
}


def _render_box(message: str, *, kind: str = "info") -> None:
    bg, border, fg = _BOX_COLORS.get(kind, _BOX_COLORS["info"])
    st.markdown(
        "<div style=\"max-width:480px;margin:64px auto;padding:32px 36px;"
        "background:#ffffff;border-radius:12px;border:1px solid #e4e4e7;"
        "font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;text-align:center;\">"
        "<p style='margin:0 0 16px 0;font-weight:700;color:#2D6A4F;font-size:15px;'>Sanzar</p>"
        f"<div style='background:{bg};border:1px solid {border};color:{fg};"
        "border-radius:8px;padding:14px 16px;font-size:14px;line-height:1.5;'>"
        f"{message}"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_unsubscribe_page() -> None:
    contact_id = _query_param("cid").strip()
    newsletter_id = _query_param("nid").strip()
    token = _query_param("t").strip()

    if not contact_id or not newsletter_id or not token:
        _render_box("Enlace de baja incompleto o no válido.", kind="error")
        return

    if not verify_unsubscribe_token(contact_id, newsletter_id, token):
        _render_box("Enlace de baja no válido.", kind="error")
        return

    if contact_id == TEST_CONTACT_ID or newsletter_id == TEST_NEWSLETTER_ID:
        _render_box(
            "Este es un enlace de baja de un envío de prueba: no afecta a ningún contacto real.",
            kind="info",
        )
        return

    done_key = f"_newsletter_unsub_done_{contact_id}_{newsletter_id}"
    if st.session_state.get(done_key):
        _render_box("Ya te habías dado de baja. No recibirás más newsletters de Sanzar.", kind="success")
        return

    sheets = sheets_service()
    contact_row = sheets.get_contact_row_by_id(contact_id) or {}
    nombre = str(contact_row.get("nombre", "") or "").strip() or "Contacto"

    try:
        updated = sheets.update_contact_field(contact_id, "newsletter_suscrito", NEWSLETTER_SUSCRITO_NO)
    except Exception:
        updated = False

    if not updated:
        _render_box(
            "No hemos podido procesar la baja automáticamente. Escríbenos a "
            f"{NEWSLETTER_NOTIFY_EMAIL} indicando tu correo y te quitaremos de la lista a mano.",
            kind="error",
        )
        return

    try:
        blogs_service().record_newsletter_unsubscribe(
            newsletter_id=newsletter_id, contact_id=contact_id, nombre=nombre
        )
    except Exception:
        pass  # registro en Blogs es best-effort; la baja ya está aplicada.

    try:
        send_email(
            NEWSLETTER_NOTIFY_EMAIL,
            f"Baja de newsletter: {nombre}",
            (
                f"{nombre} (contact_id={contact_id}) se ha dado de baja de la newsletter "
                f"(envío {newsletter_id}).\n\n"
                "Se ha marcado automáticamente como 'no suscrito' en la hoja de Contactos; "
                "no hace falta ninguna acción manual."
            ),
        )
    except Exception:
        pass  # aviso best-effort; la baja ya está aplicada aunque el correo falle.

    st.session_state[done_key] = True
    _render_box(f"{nombre}, te hemos dado de baja. No recibirás más newsletters de Sanzar.", kind="success")
