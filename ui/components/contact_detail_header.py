"""Operational header for the contact detail (ficha) — single entry-point layout.

Keeps markup and structure in one place so pages/contacts stays thin."""
from __future__ import annotations

import html

import streamlit as st

from ui.components.cards import chip
from ui.palette import (
    commercial_result_style,
    contact_status_style,
    incident_status_style,
    next_action_style,
    subscription_status_style,
    tarea_chip_style,
    tarea_limite_style,
    valor_oportunidad_style,
)


def _esc(x: object) -> str:
    return html.escape(str(x or "").strip())


def _short_detail(text: str, max_chars: int = 140) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _format_canal_label(canal: str) -> str:
    c = (canal or "").strip().lower()
    return {"email": "Email", "llamada": "Llamada", "en_persona": "En persona"}.get(c, c or "—")


def _format_resultado_label(resultado: str) -> str:
    r = (resultado or "").strip().lower()
    if r == "exitoso":
        return "Exitoso"
    if r == "fallido":
        return "Fallido"
    return (resultado or "").strip() or "—"


def _render_last_contact_block(last_contact: dict[str, str] | None) -> str:
    if not last_contact:
        return """
  <div class="sanzar-detail-last-contact">
    <div class="sanzar-detail-last-contact-label">Último contacto</div>
    <p class="sanzar-detail-last-contact-line sanzar-muted">Sin contactos registrados en Acciones</p>
  </div>
"""
    fecha = _esc(last_contact.get("fecha_contacto", ""))
    hora = _esc(last_contact.get("hora_contacto", ""))
    when = fecha + (f" · {hora}" if hora else "") or "—"
    persona = _esc(last_contact.get("persona_contacto", "")) or "—"
    canal = _esc(_format_canal_label(str(last_contact.get("canal_contacto", ""))))
    resultado = str(last_contact.get("resultado_contacto", "") or "")
    result_chip = chip(_format_resultado_label(resultado), commercial_result_style(resultado))
    return f"""
  <div class="sanzar-detail-last-contact">
    <div class="sanzar-detail-last-contact-label">Último contacto</div>
    <div class="sanzar-detail-last-contact-row">
      <span class="sanzar-detail-last-contact-when">{when}</span>
      {result_chip}
    </div>
    <p class="sanzar-detail-last-contact-sub">{persona} · {canal}</p>
  </div>
"""


def _render_next_task_block(
    *,
    open_tasks_count: int,
    next_task: dict[str, str] | None,
) -> str:
    if open_tasks_count <= 0 or not next_task:
        return ""
    titulo = _esc(_short_detail(str(next_task.get("titulo", "") or ""), 80)) or "Sin título"
    limite = str(next_task.get("fecha_limite", "") or "").strip()
    fecha_label = limite or "Sin fecha"
    limite_chip = chip(fecha_label, tarea_limite_style(limite))
    gestiona = _esc(next_task.get("persona_gestiona", "")) or "—"
    more = ""
    if open_tasks_count > 1:
        extra = open_tasks_count - 1
        more = (
            f'<p class="sanzar-detail-task-more sanzar-muted">'
            f"+{extra} más en Históricos</p>"
        )
    return f"""
  <div class="sanzar-detail-next sanzar-detail-task">
    <div class="sanzar-detail-next-label">Próxima tarea</div>
    <div class="sanzar-detail-next-row">
      {limite_chip}
      <span class="sanzar-detail-persona">{gestiona}</span>
    </div>
    <p class="sanzar-detail-next-detail">{titulo}</p>
    {more}
  </div>
"""


def render_contact_detail_header(
    *,
    contact: dict[str, str],
    contact_id: str,
    subscription_status: str,
    open_incidents: bool,
    last_contact: dict[str, str] | None = None,
    open_tasks_count: int = 0,
    next_task: dict[str, str] | None = None,
) -> None:
    """Render the sticky-ish operational header card (nombre, estado, próxima acción, alertas, contacto)."""
    cid_full = _esc(contact_id)
    nombre = contact.get("nombre", "") or "Sin nombre"
    estado = contact.get("estado", "") or "Sin estado"
    prox_f = contact.get("proxima_accion_fecha", "")
    prox_p = contact.get("persona_proxima_accion", "")
    prox_d = contact.get("proxima_accion_detalle", "")
    prox_c = contact.get("proxima_accion_canal", "")
    mun = contact.get("municipio", "")
    prov = contact.get("provincia", "")
    tel = contact.get("telefono", "")
    mail = contact.get("correo", "")
    valor = contact.get("valor", "")
    responsable = (contact.get("responsable_cliente", "") or "").strip()

    ubic = ", ".join(p for p in (mun.strip(), prov.strip()) if p)
    if not ubic:
        ubic = "Sin ubicación"
    if responsable:
        ubic = f"{ubic} · Responsable: {_esc(responsable)}"

    estado_chip = chip(estado, contact_status_style(estado))
    fecha_label = prox_f.strip() or "Sin fecha"
    next_chip = chip(f"{fecha_label}", next_action_style(prox_f))
    subs_chip = chip(f"Suscripción · {subscription_status}", subscription_status_style(subscription_status))
    inc_chip = chip(
        "Incidencias abiertas" if open_incidents else "Sin incidencias abiertas",
        incident_status_style("abierta" if open_incidents else "cerrada"),
    )
    next_limite = str((next_task or {}).get("fecha_limite", "") or "")
    if open_tasks_count > 0:
        tareas_label = f"Tareas abiertas · {open_tasks_count}"
    else:
        tareas_label = "Sin tareas abiertas"
    tareas_chip = chip(
        tareas_label,
        tarea_chip_style(open_count=open_tasks_count, next_limite=next_limite),
    )
    valor_row = ""
    if (valor or "").strip():
        valor_row = (
            '<span class="sanzar-detail-valor-chip">'
            + chip(f"Oportunidad · {_esc(valor)}", valor_oportunidad_style(valor))
            + "</span>"
        )

    persona_line = _esc(prox_p) if prox_p.strip() else "—"
    canal_prox = _esc(_format_canal_label(str(prox_c))) if (prox_c or "").strip() else ""
    canal_suffix = f" · {canal_prox}" if canal_prox and canal_prox != "—" else ""
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

    last_contact_html = _render_last_contact_block(last_contact)
    next_task_html = _render_next_task_block(
        open_tasks_count=open_tasks_count,
        next_task=next_task,
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
  {last_contact_html}
  <div class="sanzar-detail-next">
    <div class="sanzar-detail-next-label">Próxima acción</div>
    <div class="sanzar-detail-next-row">
      {next_chip}
      <span class="sanzar-detail-persona">{persona_line}{canal_suffix}</span>
    </div>
    <p class="sanzar-detail-next-detail">{detalle_vis}</p>
  </div>
  {next_task_html}
  <div class="sanzar-detail-footer-row">
    <div class="sanzar-detail-chips-secondary">{subs_chip}{inc_chip}{tareas_chip}</div>
    {contact_block}
  </div>
</section>
""",
        unsafe_allow_html=True,
    )
