"""Operational header for the contact detail (ficha) — single entry-point layout.

Keeps markup and structure in one place so pages/contacts stays thin."""
from __future__ import annotations

import html

import streamlit as st

from ui.components.cards import chip
from ui.palette import (
    contact_status_style,
    incident_status_style,
    next_action_style,
    subscription_status_style,
    valor_oportunidad_style,
)


def _esc(x: object) -> str:
    return html.escape(str(x or "").strip())


def _short_detail(text: str, max_chars: int = 140) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def render_contact_detail_header(
    *,
    contact: dict[str, str],
    contact_id: str,
    subscription_status: str,
    open_incidents: bool,
) -> None:
    """Render the sticky-ish operational header card (nombre, estado, próxima acción, alertas, contacto)."""
    cid_full = _esc(contact_id)
    nombre = contact.get("nombre", "") or "Sin nombre"
    estado = contact.get("estado", "") or "Sin estado"
    prox_f = contact.get("proxima_accion_fecha", "")
    prox_p = contact.get("persona_proxima_accion", "")
    prox_d = contact.get("proxima_accion_detalle", "")
    mun = contact.get("municipio", "")
    prov = contact.get("provincia", "")
    tel = contact.get("telefono", "")
    mail = contact.get("correo", "")
    valor = contact.get("valor", "")

    ubic = ", ".join(p for p in (mun.strip(), prov.strip()) if p)
    if not ubic:
        ubic = "Sin ubicación"

    estado_chip = chip(estado, contact_status_style(estado))
    fecha_label = prox_f.strip() or "Sin fecha"
    next_chip = chip(f"{fecha_label}", next_action_style(prox_f))
    subs_chip = chip(f"Suscripción · {subscription_status}", subscription_status_style(subscription_status))
    inc_chip = chip(
        "Incidencias abiertas" if open_incidents else "Sin incidencias abiertas",
        incident_status_style("abierta" if open_incidents else "cerrada"),
    )
    valor_row = ""
    if (valor or "").strip():
        valor_row = (
            '<span class="sanzar-detail-valor-chip">'
            + chip(f"Oportunidad · {_esc(valor)}", valor_oportunidad_style(valor))
            + "</span>"
        )

    persona_line = _esc(prox_p) if prox_p.strip() else "—"
    detalle_vis = _esc(_short_detail(prox_d)) if prox_d.strip() else "Sin detalle de próxima acción."

    contact_line_parts: list[str] = []
    if tel.strip():
        contact_line_parts.append(
            f'<span class="sanzar-detail-contact-item"><span class="sanzar-muted">Tel</span> {_esc(tel)}</span>'
        )
    if mail.strip():
        contact_line_parts.append(
            f'<span class="sanzar-detail-contact-item"><span class="sanzar-muted">Email</span> {_esc(mail)}</span>'
        )
    contact_block = ""
    if contact_line_parts:
        contact_block = (
            '<div class="sanzar-detail-contact-line">' + " · ".join(contact_line_parts) + "</div>"
        )

    st.markdown(
        f"""
<section class="sanzar-detail-header" aria-label="Cabecera del contacto">
  <div class="sanzar-detail-header-top">
    <div class="sanzar-detail-title-block">
      <h2 class="sanzar-detail-title">{_esc(nombre)}</h2>
      <p class="sanzar-detail-subline">{_esc(ubic)} · <code class="sanzar-detail-id">{cid_full}</code></p>
    </div>
    <div class="sanzar-detail-chips-primary">{estado_chip}{valor_row}</div>
  </div>
  <div class="sanzar-detail-next">
    <div class="sanzar-detail-next-label">Próxima acción</div>
    <div class="sanzar-detail-next-row">
      {next_chip}
      <span class="sanzar-detail-persona">{persona_line}</span>
    </div>
    <p class="sanzar-detail-next-detail">{detalle_vis}</p>
  </div>
  <div class="sanzar-detail-footer-row">
    <div class="sanzar-detail-chips-secondary">{subs_chip}{inc_chip}</div>
    {contact_block}
  </div>
</section>
""",
        unsafe_allow_html=True,
    )
