"""Tarjetas paginadas para históricos operativos (sensores, campañas, suscripciones, incidencias)."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from services.history_service import HISTORY_SPECS, HistoryKind, summarize_historial_umbrales
from ui import modal_state
from ui.components.cards import chip
from ui.components.tables import filter_dataframe
from ui.palette import (
    history_incident_modifier,
    history_incident_style,
    history_open_closed_modifier,
    history_open_closed_style,
    history_subscription_modifier,
    history_subscription_style,
    priority_style,
)

HISTORY_PAGE_SIZE = 4

OPERATIVE_KINDS = ("sensores", "campanas", "suscripciones", "incidencias")

_SEARCH_LABELS: dict[str, str] = {
    "sensores": "Buscar en sensores",
    "campanas": "Buscar en campañas",
    "suscripciones": "Buscar en suscripciones",
    "incidencias": "Buscar en incidencias",
}

_EMPTY_MESSAGES: dict[str, str] = {
    "sensores": "Aún no hay histórico de sensores. Usa **Nuevo histórico** para registrar el primero.",
    "campanas": "Aún no hay histórico de campañas. Usa **Nuevo histórico** para registrar el primero.",
    "suscripciones": "Aún no hay histórico de suscripciones. Usa **Nuevo histórico** para registrar el primero.",
    "incidencias": "Aún no hay histórico de incidencias. Usa **Nuevo histórico** para registrar el primero.",
}


def _esc(x: object) -> str:
    return html.escape(str(x or "").strip())


def _short(text: str, max_chars: int = 220) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _join_bits(parts: list[str], sep: str = " · ") -> str:
    cleaned = [p for p in parts if p and p != "—"]
    return sep.join(cleaned) if cleaned else "—"


def _date_range(start: str, end: str) -> str:
    s = str(start or "").strip()
    e = str(end or "").strip()
    if s and e:
        return f"{s} – {e}"
    return s or e or "—"


def _format_label(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return "—"
    return v.replace("_", " ").capitalize()


def _wrap_card(
    modifier: str,
    *,
    head: str,
    chip_html: str,
    sub: str,
    body: str = "",
    notes: str = "",
    extra: str = "",
    meta: str = "",
) -> str:
    notes_block = ""
    if notes:
        notes_block = f'<p class="sanzar-hist-card-notes">{_esc(_short(notes))}</p>'
    body_block = f'<div class="sanzar-hist-card-body">{body}</div>' if body else ""
    extra_block = extra or ""
    meta_block = f'<div class="sanzar-hist-card-meta">{meta}</div>' if meta else ""
    return f"""
<article class="sanzar-hist-card sanzar-hist-card--{modifier}">
  <div class="sanzar-hist-card-head">
    <span class="sanzar-hist-card-when">{head or "—"}</span>
    {chip_html}
  </div>
  <div class="sanzar-hist-card-sub">{sub or "—"}</div>
  {body_block}
  {notes_block}
  {extra_block}
  {meta_block}
</article>
"""


def build_sensor_card_html(row: dict[str, str]) -> str:
    estado_cierre = str(row.get("estado_cierre_sensor", "") or "")
    modifier = history_open_closed_modifier("estado_cierre_sensor", estado_cierre)
    head = _esc(_date_range(str(row.get("fecha_inicio", "")), str(row.get("fecha_fin", ""))))
    chip_html = chip(_format_label(estado_cierre), history_open_closed_style(estado_cierre))
    sub = _esc(
        _join_bits(
            [
                str(row.get("sensor_serial_number", "") or "").strip() or "—",
                _format_label(str(row.get("tipo_operacion", ""))),
                (
                    f"{row.get('cantidad_sensores', '')} sensores".strip()
                    if str(row.get("cantidad_sensores", "") or "").strip()
                    else ""
                ),
            ]
        )
    )
    red = str(row.get("red", "") or "").strip()
    red_display = red
    if red.lower() == "otro":
        otro = str(row.get("red_otro", "") or "").strip()
        if otro:
            red_display = f"otro ({otro})"
    body = _esc(
        _join_bits(
            [
                f"Estado: {_format_label(str(row.get('estado_sensor', '')))}",
                f"Red: {red_display}" if red_display else "",
                (
                    f"Última revisión: {row.get('ultima_revision', '')}"
                    if str(row.get("ultima_revision", "") or "").strip()
                    else ""
                ),
            ],
            sep=" · ",
        )
    )
    meta_bits = []
    for label, key in (
        ("AWS", "aws_user_id"),
        ("ProjectIoT", "projectiotid"),
        ("Cuenta", "cuenta_usuario"),
    ):
        val = str(row.get(key, "") or "").strip()
        if val:
            meta_bits.append(f"{label}: {_esc(val)}")
    return _wrap_card(
        modifier,
        head=head,
        chip_html=chip_html,
        sub=sub,
        body=body,
        notes=str(row.get("detalles", "") or ""),
        meta=" · ".join(meta_bits),
    )


def build_campana_card_html(row: dict[str, str]) -> str:
    estado_cierre = str(row.get("estado_cierre_campana", "") or "")
    modifier = history_open_closed_modifier("estado_cierre_campana", estado_cierre)
    head = _esc(str(row.get("nombre_campana", "") or "").strip() or "—")
    chip_html = chip(_format_label(estado_cierre), history_open_closed_style(estado_cierre))
    period = _date_range(
        str(row.get("fecha_campana_inicio", "")),
        str(row.get("fecha_campana_fin", "")),
    )
    dias = str(row.get("dias_campana", "") or "").strip()
    sub = _esc(_join_bits([period, f"{dias} días" if dias else ""]))
    umbrales_summary = summarize_historial_umbrales(str(row.get("historial_umbrales_json", "") or ""))
    body = _esc(
        _join_bits(
            [
                f"Cultivo: {row.get('cultivo', '')}" if str(row.get("cultivo", "") or "").strip() else "",
                (
                    f"Suelo: {_format_label(str(row.get('textura_suelo', '') or row.get('tipo_suelo', '')))}"
                    if str(row.get("textura_suelo", "") or row.get("tipo_suelo", "") or "").strip()
                    else ""
                ),
                (
                    f"Razón textura: {row.get('razon_textura_suelo', '')}"
                    if str(row.get("razon_textura_suelo", "") or "").strip()
                    else ""
                ),
                f"Umbrales: {umbrales_summary}" if umbrales_summary else "",
                (
                    f"Lat/Lon: {row.get('latitud', '')}, {row.get('longitud', '')}"
                    if str(row.get("latitud", "") or "").strip() and str(row.get("longitud", "") or "").strip()
                    else (
                        f"Coords: {row.get('coordenadas_parcela', '')}"
                        if str(row.get("coordenadas_parcela", "") or "").strip()
                        else ""
                    )
                ),
            ]
        )
    )
    meta_bits: list[str] = []
    hist_sensor = str(row.get("historial_sensor_id", "") or "").strip()
    if hist_sensor:
        meta_bits.append(f"Sensor hist.: {_esc(hist_sensor)}")
    return _wrap_card(
        modifier,
        head=head,
        chip_html=chip_html,
        sub=sub,
        body=body,
        notes=str(row.get("detalles", "") or ""),
        meta=" · ".join(meta_bits),
    )


def build_suscripcion_card_html(row: dict[str, str]) -> str:
    estado = str(row.get("estado_suscripcion", "") or "")
    modifier = history_subscription_modifier(estado)
    fecha_pago = str(row.get("fecha_pago", "") or "").strip()
    cantidad = str(row.get("cantidad_pago", "") or "").strip()
    moneda = str(row.get("moneda", "") or "").strip()
    pago_parts = [p for p in (fecha_pago, cantidad, moneda) if p]
    head = _esc(" · ".join(pago_parts) if pago_parts else "—")
    chip_html = chip(_format_label(estado), history_subscription_style(estado))
    sub = _esc(
        _date_range(
            str(row.get("suscripcion_fecha_inicio", "")),
            str(row.get("suscripcion_fecha_fin", "")),
        )
    )
    metodo = str(row.get("metodo_pago", "") or "").strip()
    body = _esc(f"Método: {_format_label(metodo)}" if metodo else "")
    meta_bits: list[str] = []
    for label, key in (("Factura", "factura_url"), ("Pago", "factura_pago_url")):
        url = str(row.get(key, "") or "").strip()
        if url:
            meta_bits.append(f'{label}: <a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(url)}</a>')
    return _wrap_card(
        modifier,
        head=head,
        chip_html=chip_html,
        sub=sub,
        body=body,
        notes=str(row.get("detalles", "") or ""),
        meta=" · ".join(meta_bits),
    )


def build_incidencia_card_html(row: dict[str, str]) -> str:
    estado = str(row.get("estado", "") or "")
    modifier = history_incident_modifier(estado)
    head = _esc(
        _date_range(str(row.get("fecha_apertura", "")), str(row.get("fecha_cierre", "")))
    )
    estado_chip = chip(_format_label(estado), history_incident_style(estado))
    prioridad = str(row.get("prioridad", "") or "").strip()
    chip_html = estado_chip
    if prioridad:
        chip_html += chip(_format_label(prioridad), priority_style(prioridad))
    sub = _esc(_format_label(str(row.get("tipo_incidencia", ""))))
    body = _esc(_short(str(row.get("detalle", "") or "")))
    extra = ""
    if history_incident_modifier(estado) == "fallido":
        resolucion = str(row.get("resolucion", "") or "").strip()
        if resolucion:
            extra = (
                f'<div class="sanzar-hist-card-extra">'
                f'<span class="sanzar-hist-card-meta-label">Resolución</span> '
                f"{_esc(_short(resolucion))}</div>"
            )
    meta_bits: list[str] = []
    ssn = str(row.get("sensor_serial_number", "") or "").strip()
    if ssn:
        meta_bits.append(f"Sensor: {_esc(ssn)}")
    camp = str(row.get("nombre_campana", "") or "").strip()
    if camp:
        meta_bits.append(f"Campaña: {_esc(camp)}")
    return _wrap_card(
        modifier,
        head=head,
        chip_html=chip_html,
        sub=sub,
        body=body,
        extra=extra,
        meta=" · ".join(meta_bits),
    )


_BUILDERS = {
    "sensores": build_sensor_card_html,
    "campanas": build_campana_card_html,
    "suscripciones": build_suscripcion_card_html,
    "incidencias": build_incidencia_card_html,
}


def build_history_card_html(kind: str, row: dict[str, str]) -> str:
    builder = _BUILDERS.get(kind)
    if builder is None:
        raise ValueError(f"Unsupported history card kind: {kind}")
    return builder(row)


def _page_state_keys(kind: str, contact_id: str) -> tuple[str, str]:
    cid = str(contact_id or "").strip()
    k = str(kind or "").strip()
    return (
        f"hist_card_page_{k}_{cid}",
        f"hist_card_search_fp_{k}_{cid}",
    )


def render_paginated_history_cards(
    kind: HistoryKind,
    rows: list[dict[str, str]],
    contact_id: str,
) -> None:
    """Render operative history cards; newest first; 4 per page."""
    cid = str(contact_id or "").strip()
    spec = HISTORY_SPECS[kind]
    sorted_rows = list(rows)

    if not sorted_rows:
        st.info(_EMPTY_MESSAGES.get(kind, "Sin registros todavía."))
        return

    search_key = f"hist_card_search_{kind}_{cid}"
    page_key, fp_key = _page_state_keys(kind, cid)
    query = st.text_input(
        _SEARCH_LABELS.get(kind, "Buscar"),
        placeholder="Filtrar por cualquier campo…",
        key=search_key,
    )
    fp = query.strip()
    if st.session_state.get(fp_key) != fp:
        st.session_state[fp_key] = fp
        st.session_state[page_key] = 0

    df = pd.DataFrame(sorted_rows)
    filtered_df = filter_dataframe(df, query, list(df.columns))
    if query.strip() and filtered_df.empty:
        st.info(f"No hay coincidencias para «{query.strip()}».")
        return
    if query.strip() and len(filtered_df) < len(df):
        st.caption(f"Mostrando {len(filtered_df)} de {len(df)} registros")

    display_rows = filtered_df.to_dict("records")
    total = len(display_rows)
    max_page = max(0, (total - 1) // HISTORY_PAGE_SIZE) if total else 0
    page = int(st.session_state.get(page_key, 0) or 0)
    page = max(0, min(page, max_page))
    st.session_state[page_key] = page

    if total > HISTORY_PAGE_SIZE:
        nav_prev, nav_info, nav_next = st.columns([0.12, 0.76, 0.12], gap="small")
        with nav_prev:
            if st.button("←", key=f"hist_page_prev_{kind}_{cid}", disabled=page <= 0, width="stretch"):
                st.session_state[page_key] = page - 1
                st.rerun()
        with nav_info:
            start = page * HISTORY_PAGE_SIZE + 1
            end = min((page + 1) * HISTORY_PAGE_SIZE, total)
            st.caption(f"Mostrando {start}–{end} de {total}")
        with nav_next:
            if st.button(
                "→",
                key=f"hist_page_next_{kind}_{cid}",
                disabled=page >= max_page,
                width="stretch",
            ):
                st.session_state[page_key] = page + 1
                st.rerun()
    elif total:
        st.caption(f"{total} registro{'s' if total != 1 else ''}")

    offset = page * HISTORY_PAGE_SIZE
    page_rows = display_rows[offset : offset + HISTORY_PAGE_SIZE]
    builder = _BUILDERS[kind]
    for row in page_rows:
        row_id = str(row.get(spec.id_column, "") or "").strip()
        card_col, btn_col = st.columns([0.88, 0.12], gap="small")
        with card_col:
            st.markdown(builder(row), unsafe_allow_html=True)
        with btn_col:
            st.markdown('<div class="sanzar-hist-card-edit-spacer"></div>', unsafe_allow_html=True)
            if st.button(
                "Editar",
                key=f"hist_card_edit_{kind}_{cid}_{row_id}",
                width="stretch",
            ):
                if row_id:
                    modal_state.open_edit_history_modal(kind, cid, row_id)
                    st.rerun()
