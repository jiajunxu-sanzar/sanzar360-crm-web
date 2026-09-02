"""Pestaña Incidencias: tablero visual de incidencias abiertas, pendientes de aprobar y cerradas."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app.cache import history_service, load_history_rows_cached
from app.state import bump_history_cache, select_contact
from services.incidencias_board import (
    BUCKET_ABIERTAS,
    BUCKET_CERRADAS,
    BUCKET_LABELS,
    BUCKET_PENDIENTES,
    IncidenciaCardPayload,
    VER_TODOS,
    build_incidencia_payloads,
    bucket_counts,
    bucket_payloads,
    cliente_options,
    filter_payloads,
    tipo_options,
    values_for_aprobar,
    values_for_cerrar,
    values_for_marcar_pendiente,
    values_for_reabrir,
)
from ui.components.incidencia_cards import incidencia_card_html
from ui.components.page_header import render_page_header

PRIORIDAD_OPCIONES = (VER_TODOS, "alta", "media", "baja")
CARDS_PER_PAGE = 12

_FILTER_CLIENTE_KEY = "incidencias.filtro_cliente"
_FILTER_TIPO_KEY = "incidencias.filtro_tipo"
_FILTER_PRIORIDAD_KEY = "incidencias.filtro_prioridad"
_FILTER_QUERY_KEY = "incidencias.busqueda"
_CLOSE_TARGET_KEY = "incidencias.cerrar_target"


def _load_payloads(contacts_df: pd.DataFrame) -> list[IncidenciaCardPayload]:
    version = st.session_state.get("history_cache_version", 0)
    rows = load_history_rows_cached("incidencias", version)
    return build_incidencia_payloads(rows, contacts_df=contacts_df, today=date.today())


def _apply_history_update(incidencia_id: str, values: dict[str, str], success: str) -> None:
    try:
        history_service().update_row("incidencias", incidencia_id, values)
    except Exception as exc:  # noqa: BLE001 — se muestra el motivo al usuario
        st.error(f"No se pudo actualizar la incidencia: {exc}")
        return
    bump_history_cache()
    st.session_state["incidencias.toast"] = success
    st.rerun()


@st.dialog("Cerrar incidencia")
def _cerrar_incidencia_dialog(payload: IncidenciaCardPayload) -> None:
    st.markdown(f"**{payload.cliente}** · {payload.tipo}")
    if payload.detalle:
        st.caption(payload.detalle)
    resolucion = st.text_area(
        "Resolución",
        value=payload.resolucion,
        height=120,
        placeholder="Qué se hizo para resolverla",
        key=f"inc_cerrar_resolucion_{payload.incidencia_id}",
    )
    st.caption(f"Se registrará la fecha de cierre de hoy: {date.today().strftime('%d/%m/%Y')}")
    cols = st.columns(2)
    if cols[0].button("Cerrar incidencia", width="stretch", type="primary"):
        st.session_state.pop(_CLOSE_TARGET_KEY, None)
        _apply_history_update(
            payload.incidencia_id,
            values_for_cerrar(resolucion=resolucion),
            "Incidencia cerrada.",
        )
    if cols[1].button("Cancelar", width="stretch"):
        st.session_state.pop(_CLOSE_TARGET_KEY, None)
        st.rerun()


def _render_card(payload: IncidenciaCardPayload) -> None:
    with st.container(border=True):
        st.markdown(incidencia_card_html(payload), unsafe_allow_html=True)

        key_base = f"inc_{payload.bucket}_{payload.incidencia_id or payload.contact_id}"
        if payload.bucket == BUCKET_PENDIENTES:
            cols = st.columns(3, gap="small")
            if cols[0].button("Aprobar", key=f"{key_base}_aprobar", width="stretch",
                              icon=":material/check:", help="Pasa la incidencia a «abierta»"):
                _apply_history_update(
                    payload.incidencia_id, values_for_aprobar(), "Incidencia aprobada: ahora está abierta."
                )
            if cols[1].button("Cerrar", key=f"{key_base}_cerrar", width="stretch",
                              icon=":material/task_alt:"):
                st.session_state[_CLOSE_TARGET_KEY] = payload.incidencia_id
                st.rerun()
            open_ficha = cols[2].button(
                "Abrir ficha", key=f"{key_base}_ficha", width="stretch", icon=":material/open_in_new:"
            )
        elif payload.bucket == BUCKET_ABIERTAS:
            cols = st.columns(3, gap="small")
            if cols[0].button("Cerrar", key=f"{key_base}_cerrar", width="stretch",
                              icon=":material/task_alt:"):
                st.session_state[_CLOSE_TARGET_KEY] = payload.incidencia_id
                st.rerun()
            if cols[1].button("A revisión", key=f"{key_base}_pendiente", width="stretch",
                              icon=":material/pending:", help="Marca la incidencia como pendiente de aprobar"):
                _apply_history_update(
                    payload.incidencia_id,
                    values_for_marcar_pendiente(),
                    "Incidencia marcada como pendiente de aprobar.",
                )
            open_ficha = cols[2].button(
                "Abrir ficha", key=f"{key_base}_ficha", width="stretch", icon=":material/open_in_new:"
            )
        else:
            cols = st.columns(2, gap="small")
            if cols[0].button("Reabrir", key=f"{key_base}_reabrir", width="stretch",
                              icon=":material/replay:"):
                _apply_history_update(
                    payload.incidencia_id, values_for_reabrir(), "Incidencia reabierta."
                )
            open_ficha = cols[1].button(
                "Abrir ficha", key=f"{key_base}_ficha", width="stretch", icon=":material/open_in_new:"
            )

        if open_ficha:
            if not payload.contact_id:
                st.warning("Esta incidencia no tiene contacto asociado.")
            else:
                select_contact(payload.contact_id)
                st.rerun()


def _render_bucket(payloads: list[IncidenciaCardPayload], bucket: str, empty_message: str) -> None:
    rows = bucket_payloads(payloads, bucket)
    if not rows:
        st.info(empty_message)
        return

    page_key = f"incidencias.pagina_{bucket}"
    total_pages = max(1, (len(rows) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
    current = int(st.session_state.get(page_key, 1))
    current = min(max(current, 1), total_pages)
    st.session_state[page_key] = current

    head = st.columns([0.6, 0.4], vertical_alignment="center")
    head[0].caption(f"{len(rows)} incidencia{'s' if len(rows) != 1 else ''}")
    if total_pages > 1:
        with head[1]:
            nav = st.columns([0.3, 0.4, 0.3], vertical_alignment="center")
            if nav[0].button("←", key=f"{page_key}_prev", width="stretch", disabled=current <= 1):
                st.session_state[page_key] = current - 1
                st.rerun()
            nav[1].caption(f"Página {current} de {total_pages}")
            if nav[2].button("→", key=f"{page_key}_next", width="stretch", disabled=current >= total_pages):
                st.session_state[page_key] = current + 1
                st.rerun()

    start = (current - 1) * CARDS_PER_PAGE
    visible = rows[start : start + CARDS_PER_PAGE]
    cols = st.columns(2, gap="medium")
    for i, payload in enumerate(visible):
        with cols[i % 2]:
            _render_card(payload)


def _render_filters(all_payloads: list[IncidenciaCardPayload]) -> list[IncidenciaCardPayload]:
    clientes = cliente_options(all_payloads)
    tipos = tipo_options(all_payloads)

    for key, opts in ((_FILTER_CLIENTE_KEY, clientes), (_FILTER_TIPO_KEY, tipos)):
        if st.session_state.get(key) not in opts:
            st.session_state[key] = VER_TODOS
    if st.session_state.get(_FILTER_PRIORIDAD_KEY) not in PRIORIDAD_OPCIONES:
        st.session_state[_FILTER_PRIORIDAD_KEY] = VER_TODOS

    with st.container(border=True):
        cols = st.columns([0.34, 0.22, 0.22, 0.22], gap="small")
        with cols[0]:
            query = st.text_input(
                "Buscar",
                key=_FILTER_QUERY_KEY,
                placeholder="Cliente, detalle, sensor…",
                label_visibility="collapsed",
            )
        with cols[1]:
            cliente = st.selectbox("Cliente", clientes, key=_FILTER_CLIENTE_KEY)
        with cols[2]:
            tipo = st.selectbox("Tipo", tipos, key=_FILTER_TIPO_KEY)
        with cols[3]:
            prioridad = st.selectbox("Prioridad", PRIORIDAD_OPCIONES, key=_FILTER_PRIORIDAD_KEY)

    return filter_payloads(
        all_payloads, cliente=cliente, tipo=tipo, prioridad=prioridad, query=query
    )


def render(contacts_df: pd.DataFrame) -> None:
    render_page_header("Incidencias")

    if toast := st.session_state.pop("incidencias.toast", ""):
        st.toast(str(toast), icon="✅")

    try:
        all_payloads = _load_payloads(contacts_df)
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo cargar el histórico de incidencias: {exc}")
        return

    if not all_payloads:
        st.info(
            "No hay incidencias registradas. Se crean desde la ficha de un contacto, "
            "en «Histórico de incidencias»."
        )
        return

    payloads = _render_filters(all_payloads)
    counts = bucket_counts(payloads)

    target = str(st.session_state.get(_CLOSE_TARGET_KEY, "") or "")
    if target:
        match = next((p for p in all_payloads if p.incidencia_id == target), None)
        if match is not None:
            _cerrar_incidencia_dialog(match)
        else:
            st.session_state.pop(_CLOSE_TARGET_KEY, None)

    tabs = st.tabs(
        [
            f"{BUCKET_LABELS[BUCKET_ABIERTAS]} · {counts[BUCKET_ABIERTAS]}",
            f"{BUCKET_LABELS[BUCKET_PENDIENTES]} · {counts[BUCKET_PENDIENTES]}",
            f"{BUCKET_LABELS[BUCKET_CERRADAS]} · {counts[BUCKET_CERRADAS]}",
        ]
    )
    with tabs[0]:
        _render_bucket(payloads, BUCKET_ABIERTAS, "No hay incidencias abiertas con estos filtros.")
    with tabs[1]:
        _render_bucket(
            payloads, BUCKET_PENDIENTES, "No hay incidencias pendientes de aprobar con estos filtros."
        )
    with tabs[2]:
        _render_bucket(payloads, BUCKET_CERRADAS, "No hay incidencias cerradas con estos filtros.")
