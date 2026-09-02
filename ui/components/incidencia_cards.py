"""Tarjeta visual de incidencia para la pestaña Incidencias."""
from __future__ import annotations

import html

from services.incidencias_board import (
    BUCKET_CERRADAS,
    BUCKET_PENDIENTES,
    IncidenciaCardPayload,
)
from ui.components.cards import chip
from ui.palette import history_incident_style, priority_style


def _esc(value: object) -> str:
    return html.escape(str(value or "").strip())


def _short(text: str, max_chars: int = 320) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _bucket_modifier(bucket: str) -> str:
    if bucket == BUCKET_CERRADAS:
        return "cerrada"
    if bucket == BUCKET_PENDIENTES:
        return "pendiente"
    return "abierta"


def incidencia_card_html(payload: IncidenciaCardPayload) -> str:
    """HTML de una tarjeta: cliente, chips de estado, fechas, detalle y resolución."""
    chips = [chip(payload.estado or "abierta", history_incident_style(payload.estado))]
    if payload.prioridad:
        chips.append(chip(payload.prioridad, priority_style(payload.prioridad)))
    chips_html = "".join(chips)

    meta_items: list[tuple[str, str]] = [
        ("Apertura", payload.fecha_apertura or "—"),
    ]
    if payload.bucket == BUCKET_CERRADAS:
        meta_items.append(("Cierre", payload.fecha_cierre or "—"))
    meta_items.append(("Tipo", payload.tipo or "—"))
    if payload.sensor:
        meta_items.append(("Sensor", payload.sensor))
    if payload.campana:
        meta_items.append(("Campaña", payload.campana))

    meta_html = "".join(
        f"<div><dt>{_esc(label)}</dt><dd>{_esc(value)}</dd></div>" for label, value in meta_items
    )

    detalle = _short(payload.detalle) or "Sin detalle registrado"
    resolucion = _short(payload.resolucion)
    resolucion_html = (
        f"<div class='sanzar-inc-card__block sanzar-inc-card__block--resolucion'>"
        f"<span class='sanzar-inc-card__block-label'>Resolución</span>"
        f"<p>{_esc(resolucion)}</p></div>"
        if resolucion
        else ""
    )
    antiguedad = payload.antiguedad_label
    antiguedad_html = (
        f"<span class='sanzar-inc-card__age'>{_esc(antiguedad)}</span>" if antiguedad else ""
    )
    ref = payload.incidencia_id
    ref_html = f"<span class='sanzar-inc-card__ref'>{_esc(ref)}</span>" if ref else ""

    return (
        f"<div class='sanzar-inc-card sanzar-inc-card--{_bucket_modifier(payload.bucket)}'>"
        f"  <div class='sanzar-inc-card__head'>"
        f"    <h4 class='sanzar-inc-card__client'>{_esc(payload.cliente)}</h4>"
        f"    {ref_html}"
        f"  </div>"
        f"  <div class='sanzar-inc-card__chips'>{chips_html}{antiguedad_html}</div>"
        f"  <dl class='sanzar-inc-card__meta'>{meta_html}</dl>"
        f"  <div class='sanzar-inc-card__block'>"
        f"    <span class='sanzar-inc-card__block-label'>Detalle</span>"
        f"    <p>{_esc(detalle)}</p>"
        f"  </div>"
        f"  {resolucion_html}"
        f"</div>"
    )
