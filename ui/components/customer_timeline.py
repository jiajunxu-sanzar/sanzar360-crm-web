"""Presentación compacta del timeline unificado por contacto."""

from __future__ import annotations

import html as html_std
import streamlit as st

from app.cache import history_service
from services.customer_timeline import build_customer_timeline, timeline_events_grouped_months


def _kind_class(slug: str) -> str:
    return slug.replace("_", "-")


def _render_event_article(ev: CustomerTimelineEvent, *, weekday_label: bool) -> str:
    cls = html_std.escape(_kind_class(ev.kind_slug))
    d = ev.on_date
    if weekday_label:
        wd = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"][d.weekday()]
        when = html_std.escape(f"{wd} · {d.strftime('%d/%m/%Y')}")
    else:
        when = html_std.escape(d.strftime("%d/%m/%Y"))
    head = html_std.escape(ev.headline)
    lines_ul = ""
    if ev.lines:
        lis = "".join(f"<li>{html_std.escape(line)}</li>" for line in ev.lines)
        lines_ul = f"<ul class='sanzar-timeline-ul'>{lis}</ul>"
    return (
        "<article class='sanzar-timeline-item'"
        + f" data-kind='{cls}'>"
        + f"<span class='sanzar-timeline-dot' aria-hidden='true'></span>"
        + f"<header class='sanzar-timeline-head'><time datetime='{d.isoformat()}'>{when}</time>"
        + f"<h4 class='sanzar-timeline-title'>{head}</h4></header>"
        + lines_ul
        + "</article>"
    )


def render_contact_timeline_block(contact_id: str) -> None:
    """Bloque reutilizable: carga datos, controles opcionales, HTML tema."""
    if not contact_id:
        return
    hs = history_service()
    events = build_customer_timeline(
        sensores_rows=hs.rows_for_contact("sensores", contact_id),
        campanas_rows=hs.rows_for_contact("campanas", contact_id),
        suscripciones_rows=hs.rows_for_contact("suscripciones", contact_id),
        incidencias_rows=hs.rows_for_contact("incidencias", contact_id),
    )

    st.markdown("##### Historia del cliente")
    st.caption(
        "Sensores, campañas, pagos e incidencias en una línea temporal única "
        "(mismo origen que los históricos detallados)."
    )

    if not events:
        st.info(
            "Aún no hay fechas registradas en sensores, campañas, suscripciones o incidencias. "
            "Añádelas desde la vista **Históricos**."
        )
        return

    order_mode = st.radio(
        "Orden",
        ("Lo más nuevo primero", "Lo más antiguo primero"),
        horizontal=True,
        key=f"sanzar_tl_order_{contact_id}",
    )
    weekdays = st.toggle("Mostrar día de la semana", True, key=f"sanzar_tl_weekday_{contact_id}")

    grouped = timeline_events_grouped_months(events, reverse_chrono=order_mode.startswith("Lo más nuevo"))
    blocks: list[str] = []

    # Leyenda rápida
    pills = """
<div class='sanzar-timeline-legends'>
  <span class='san-tl-chip san-tl-sensor'>Sensores</span>
  <span class='san-tl-chip san-tl-campana'>Campaña</span>
  <span class='san-tl-chip san-tl-pago'>Pago / suscripción</span>
  <span class='san-tl-chip san-tl-incidencia'>Incidencia</span>
</div>
"""
    blocks.append(pills)

    for month_heading, bucket in grouped:
        inner = "".join(_render_event_article(ev, weekday_label=weekdays) for ev in bucket)
        blocks.append(
            "<section class='sanzar-timeline-month'>"
            f"<h5 class='sanzar-timeline-month-title'>{html_std.escape(month_heading)}</h5>"
            "<div class='sanzar-timeline-list'>"
            f"{inner}</div>"
            "</section>"
        )

    st.markdown(
        f"<div class='sanzar-timeline-shell' aria-label='Línea de tiempo del cliente'>{''.join(blocks)}</div>",
        unsafe_allow_html=True,
    )
