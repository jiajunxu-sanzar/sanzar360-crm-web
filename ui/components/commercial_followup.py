"""Tarjetas de seguimiento comercial (histórico Acciones) en la ficha de contacto."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from services.contact_proxima_index import sort_commercial_rows_by_contact_date
from services.history_service import HISTORY_SPECS
from ui import modal_state
from ui.components.cards import chip
from ui.components.tables import filter_dataframe
from ui.palette import commercial_result_style, commercial_seg_card_modifier

PAGE_SIZE = 4


def _esc(x: object) -> str:
    return html.escape(str(x or "").strip())


def _short(text: str, max_chars: int = 220) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _format_canal(canal: str) -> str:
    c = (canal or "").strip().lower()
    labels = {"email": "Email", "llamada": "Llamada", "en_persona": "En persona"}
    return labels.get(c, c or "—")


def _format_resultado(resultado: str) -> str:
    r = (resultado or "").strip().lower()
    if r == "exitoso":
        return "Exitoso"
    if r == "fallido":
        return "Fallido"
    return resultado.strip() or "—"


def _build_card_html(row: dict[str, str]) -> str:
    resultado = str(row.get("resultado_contacto", "") or "")
    modifier = commercial_seg_card_modifier(resultado)
    fecha = _esc(row.get("fecha_contacto", ""))
    hora = _esc(row.get("hora_contacto", ""))
    when = f"{fecha}" + (f" · {hora}" if hora else "")
    persona = _esc(row.get("persona_contacto", "")) or "—"
    canal = _esc(_format_canal(str(row.get("canal_contacto", ""))))
    result_chip = chip(_format_resultado(resultado), commercial_result_style(resultado))
    notas_raw = _short(str(row.get("notas_contacto", "")))
    if notas_raw:
        notas_block = f'<p class="sanzar-seg-card-notes">{_esc(notas_raw)}</p>'
    else:
        notas_block = '<p class="sanzar-seg-card-notes sanzar-muted">Sin notas</p>'

    prox_parts: list[str] = []
    prox_f = str(row.get("proxima_accion_fecha", "") or "").strip()
    if prox_f:
        prox_parts.append(f"<strong>{_esc(prox_f)}</strong>")
        prox_p = _esc(row.get("proxima_accion_persona", ""))
        prox_c = _esc(_format_canal(str(row.get("proxima_accion_canal", ""))))
        if prox_p:
            prox_parts.append(prox_p)
        if prox_c and prox_c != "—":
            prox_parts.append(prox_c)
        prox_d = _esc(_short(str(row.get("proxima_accion_detalle", "")), 120))
        prox_line = " · ".join(prox_parts)
        prox_block = f'<div class="sanzar-seg-card-proxima"><span class="sanzar-seg-card-meta-label">Próxima</span> {prox_line}'
        if prox_d:
            prox_block += f'<p class="sanzar-seg-card-proxima-detail">{prox_d}</p>'
        prox_block += "</div>"
    else:
        prox_block = ""

    meta_bits: list[str] = []
    origen = str(row.get("origen_registro", "") or "").strip()
    if origen:
        meta_bits.append(f"Origen: {_esc(origen)}")
    email_clas = str(row.get("email_clasificacion", "") or "").strip()
    if email_clas:
        meta_bits.append(f"Email: {_esc(email_clas.replace('_', ' '))}")
    meta_line = " · ".join(meta_bits)

    return f"""
<article class="sanzar-seg-card sanzar-seg-card--{modifier}">
  <div class="sanzar-seg-card-head">
    <span class="sanzar-seg-card-when">{when or "—"}</span>
    {result_chip}
  </div>
  <div class="sanzar-seg-card-sub">{persona} · {canal}</div>
  {notas_block}
  {prox_block}
  {f'<div class="sanzar-seg-card-meta">{meta_line}</div>' if meta_line else ''}
</article>
"""


def _page_state_keys(contact_id: str) -> tuple[str, str]:
    return (
        f"seg_followup_page_{contact_id}",
        f"seg_followup_search_fp_{contact_id}",
    )


def render_commercial_followup_list(
    rows: list[dict[str, str]],
    contact_id: str,
) -> None:
    """Render full-width cards; newest contact first; 4 per page."""
    cid = str(contact_id or "").strip()
    spec = HISTORY_SPECS["seguimiento_comercial"]
    sorted_rows = sort_commercial_rows_by_contact_date(rows)

    if not sorted_rows:
        st.info("Aún no hay seguimiento comercial. Usa **Nuevo seguimiento** para registrar el primer contacto.")
        return

    search_key = f"seg_followup_search_{cid}"
    page_key, fp_key = _page_state_keys(cid)
    query = st.text_input(
        "Buscar en seguimiento",
        placeholder="Filtrar por persona, canal, notas…",
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
    max_page = max(0, (total - 1) // PAGE_SIZE) if total else 0
    page = int(st.session_state.get(page_key, 0) or 0)
    page = max(0, min(page, max_page))
    st.session_state[page_key] = page

    if total > PAGE_SIZE:
        nav_prev, nav_info, nav_next = st.columns([0.12, 0.76, 0.12], gap="small")
        with nav_prev:
            if st.button("←", key=f"seg_page_prev_{cid}", disabled=page <= 0, width="stretch"):
                st.session_state[page_key] = page - 1
                st.rerun()
        with nav_info:
            start = page * PAGE_SIZE + 1
            end = min((page + 1) * PAGE_SIZE, total)
            st.caption(f"Mostrando {start}–{end} de {total}")
        with nav_next:
            if st.button("→", key=f"seg_page_next_{cid}", disabled=page >= max_page, width="stretch"):
                st.session_state[page_key] = page + 1
                st.rerun()
    elif total:
        st.caption(f"{total} registro{'s' if total != 1 else ''}")

    offset = page * PAGE_SIZE
    page_rows = display_rows[offset : offset + PAGE_SIZE]
    for row in page_rows:
        row_id = str(row.get(spec.id_column, "") or "").strip()
        card_col, btn_col = st.columns([0.88, 0.12], gap="small")
        with card_col:
            st.markdown(_build_card_html(row), unsafe_allow_html=True)
        with btn_col:
            st.markdown('<div class="sanzar-seg-card-edit-spacer"></div>', unsafe_allow_html=True)
            if st.button(
                "Editar",
                key=f"seg_card_edit_{cid}_{row_id}",
                width="stretch",
            ):
                if row_id:
                    modal_state.open_edit_history_modal("seguimiento_comercial", cid, row_id)
                    st.rerun()
