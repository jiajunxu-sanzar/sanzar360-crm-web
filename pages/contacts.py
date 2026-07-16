from __future__ import annotations

import html
import uuid
from difflib import SequenceMatcher
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from app import auth
from ui.components.page_header import render_page_header
from app.cache import (
    clear_all_cache,
    history_service,
    inventory_service,
    load_acciones_cached,
    load_contact_sensor_overview_cached,
    load_inventory_cached,
    load_users_cached,
    sheets_service,
)
from app.state import (
    bump_contacts_cache,
    bump_history_cache,
    bump_inventory_cache,
    clear_contacts_write_status,
    get_contacts_write_status,
    pop_pending_created_contact_id,
    reconcile_selected_contact_id,
    select_contact,
    set_contacts_df_override,
    set_contacts_write_status,
    set_pending_created_contact_id,
)
from app.telemetry import timed, track_event
from config.contact_estado import is_contact_perdido
from config.settings import (
    CANONICAL_COLUMNS,
    CONTACT_ESTADO_OPCIONES,
    FUENTE_LEAD_OPCIONES,
    PERSONA_COMERCIAL_OPCIONES,
    LEAD_FIELDS,
    CANAL_CONTACTO_OPCIONES,
    EMAIL_CLASIFICACION_OPCIONES,
    RESULTADO_CONTACTO_OPCIONES,
    TIPO_RELACION_OPCIONES,
    VALOR_OPCIONES,
)
from services.commercial_action_validation import validate_commercial_action_values
from services.contact_proxima_index import enrich_contacts_with_proxima, latest_commercial_contact_row
from services.history_service import (
    HISTORY_SPECS,
    HistoryService,
    ProjectIotAssignment,
    count_sensor_assets,
    parse_projectiotid_assignments,
    sensor_association_tokens,
    sensor_serials_from_sensor_serial_number,
    serialize_projectiotid_assignments,
    validate_projectiotid_assignments,
)
from services.contact_deletion import delete_contact_and_related_data
from services.incidencia_association_options import (
    AssociationOption,
    build_campana_history_options,
    build_sensor_history_options,
    option_by_id,
)
from services.contact_sensor_overview import (
    filter_by_sensor_overview,
    semaforo_by_contact_id,
    semaforo_display_prefix,
)
from services.contact_use_cases import create_empty_contact, save_contact_by_id
from services.proxima_accion_stats import (
    apply_dash_bucket_date_filter,
    filter_by_contact_estado,
    filter_by_persona_proxima_accion,
    filter_by_responsable_cliente,
    next_action_bucket_counts,
)
from services.users_service import crm_user_names
from services.inventory_service import InventoryAssetOption, normalize_inventory_serial_for_match
from services.sheet_date_format import (
    SENSOR_SERIAL_NUMBER_FORMAT_HELP,
    is_valid_dd_mm_yyyy,
    is_valid_sensor_serial_number,
    normalize_dd_mm_yyyy,
    normalize_sensor_serial_number,
    validate_contact_date_fields,
    validate_dd_mm_yyyy_fields,
)
from ui.components.cards import card, chip
from ui.palette import contact_status_style
from ui.components.customer_timeline import render_contact_timeline_block
from ui.components.commercial_followup import render_commercial_followup_list
from ui.components.contact_detail_header import render_contact_detail_header
from ui.components.contact_overview_table import (
    filter_overview_by_contact_ids,
    render_contact_overview_dialog_content,
    sort_overview_by_proxima_accion,
)
from ui.components.history_cards import render_paginated_history_cards
from ui import modal_state
from ui.components.history import clear_history_table_selection
from ui.components.tables import filter_dataframe

DATE_COLUMNS_BY_KIND = {
    "sensores": [("Fecha inicio", "fecha_inicio"), ("Fecha fin", "fecha_fin"), ("Última revisión", "ultima_revision")],
    "campanas": [("Fecha inicio campaña", "fecha_campana_inicio"), ("Fecha fin campaña", "fecha_campana_fin")],
    "suscripciones": [
        ("Fecha pago", "fecha_pago"),
        ("Inicio suscripción", "suscripcion_fecha_inicio"),
        ("Fin suscripción", "suscripcion_fecha_fin"),
    ],
    "incidencias": [("Fecha apertura", "fecha_apertura"), ("Fecha cierre", "fecha_cierre")],
    "seguimiento_comercial": [
        ("Fecha contacto", "fecha_contacto"),
        ("Próxima acción (fecha)", "proxima_accion_fecha"),
    ],
}

SELECT_OPTIONS = {
    "red": ["auto", "movistar", "vodafone", "orange", "yoigo", "otro"],
    "tipo_operacion": ["prestamo", "venta", "demo", "mantenimiento", "otro"],
    "estado_sensor": ["activo", "en revisión", "devuelto", "mantenimiento", "baja"],
    "estado_cierre_sensor": ["abierto", "cerrado"],
    "moneda": ["EUR", "Dólar"],
    "metodo_pago": ["transferencia", "tarjeta", "recibo", "efectivo", "otro"],
    "estado_suscripcion": ["activa", "caduca pronto", "inactiva"],
    "tipo_incidencia": ["sensor", "conectividad", "riego", "facturación", "campaña", "otro"],
    "estado": ["abierta", "en curso", "bloqueada", "cerrada"],
    "estado_cierre_campana": ["abierto", "cerrado"],
    "prioridad": ["alta", "media", "baja"],
    "resultado_contacto": list(RESULTADO_CONTACTO_OPCIONES),
    "canal_contacto": list(CANAL_CONTACTO_OPCIONES),
    "email_clasificacion": list(EMAIL_CLASIFICACION_OPCIONES),
    "proxima_accion_canal": list(CANAL_CONTACTO_OPCIONES),
    "persona_contacto": list(PERSONA_COMERCIAL_OPCIONES),
    "proxima_accion_persona": list(PERSONA_COMERCIAL_OPCIONES),
}

CONTACT_LIST_PANEL_HEIGHT_BASE = 920
CONTACT_LIST_PANEL_HEIGHT_WITH_DETAIL = 1240
NEW_CONTACT_FLOW_KEY = "new_contact_flow_state"
NEW_CONTACT_FLOW_IDLE = "idle"
NEW_CONTACT_FLOW_OPEN = "open"
NEW_CONTACT_FLOW_SUBMITTING = "submitting"
NEW_CONTACT_SIMILAR_CANDIDATES_KEY = "new_contact_similar_candidates"
NEW_CONTACT_REQUIRE_SECOND_CONFIRM_KEY = "new_contact_require_second_confirm"
NEW_CONTACT_CONFIRM_OVERRIDE_KEY = "new_contact_confirmed_override"
CONTACTS_SHOW_LOST_KEY = "contacts.show_lost"
CONTACTS_ONLY_WITH_SENSORS_KEY = "contacts.only_with_sensors"
CONTACTS_VIEW_MODE_KEY = "contacts.view_mode"
CONTACTS_FILTERED_IDS_KEY = "contacts.filtered_contact_ids"
CONTACTS_VIEW_FICHA = "ficha"
CONTACTS_VIEW_TABLA = "tabla"
CONTACTS_SAVE_SUCCESS_KEY = "contacts.save_success_message"
CONTACTS_DELETE_SUCCESS_KEY = "contacts.delete_success_message"
CONTACTS_DELETE_TARGET_ID_KEY = "contacts.delete_target_id"
CONTACTS_DELETE_TARGET_NAME_KEY = "contacts.delete_target_name"
HISTORY_DELETE_CONFIRM_PREFIX = "history_delete_confirm"
DASH_PERSONA_PROXIMA_ACCION_KEY = "dash_persona_proxima_accion"
DASH_ESTADO_FILTER_KEY = "dash_estado_filter"
DASH_RESPONSABLE_FILTER_KEY = "dash_responsable_cliente"
_INCIDENCIA_ASSOC_HEADERS = frozenset(
    {
        "historial_sensor_id",
        "sensor_serial_number",
        "historial_campana_id",
        "nombre_campana",
    }
)
OFICINA_CONTACT_NAME = "oficina"


def pin_oficina_contact_first(df: pd.DataFrame) -> pd.DataFrame:
    """Put contact(s) named Oficina at the top; preserve relative order otherwise."""
    if df is None or df.empty or "nombre" not in df.columns:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    names = df["nombre"].fillna("").astype(str).str.strip().str.lower()
    is_oficina = names == OFICINA_CONTACT_NAME
    if not bool(is_oficina.any()):
        return df.reset_index(drop=True)
    return pd.concat([df.loc[is_oficina], df.loc[~is_oficina]], ignore_index=True)


def filter_open_sensor_history(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep sensor history rows that are not explicitly cerrado."""
    return [row for row in rows if _is_sensor_history_open(row)]


def _contacts_block_spacer() -> None:
    st.markdown('<div class="sanzar-contacts-block-spacer"></div>', unsafe_allow_html=True)


def _contact_display_name(df: pd.DataFrame, contact_id: str) -> str:
    if not (contact_id or "").strip() or df.empty or "contact_id" not in df.columns:
        return "Sin nombre"
    matches = df[df["contact_id"].astype(str).str.strip() == str(contact_id).strip()]
    if matches.empty:
        return "Sin nombre"
    return str(matches.iloc[0].get("nombre", "") or "").strip() or "Sin nombre"


def _filtered_overview_display_df() -> pd.DataFrame:
    overview = load_contact_sensor_overview_cached(st.session_state.get("history_cache_version", 0))
    ids = st.session_state.get(CONTACTS_FILTERED_IDS_KEY, [])
    return sort_overview_by_proxima_accion(filter_overview_by_contact_ids(overview, ids))


def _clear_modal_flags() -> None:
    _new_contact_flow_finish(clear_inputs=True)
    modal_state.close_modal()


def _new_contact_flow_state_get() -> str:
    state = str(st.session_state.get(NEW_CONTACT_FLOW_KEY, "") or "").strip().lower()
    if state in {NEW_CONTACT_FLOW_IDLE, NEW_CONTACT_FLOW_OPEN, NEW_CONTACT_FLOW_SUBMITTING}:
        return state
    # Legacy compatibility for previous boolean flags.
    if st.session_state.get("contact_creating_in_progress", False):
        return NEW_CONTACT_FLOW_SUBMITTING
    if st.session_state.get("contact_create_confirm_open", False):
        return NEW_CONTACT_FLOW_OPEN
    return NEW_CONTACT_FLOW_IDLE


def _new_contact_flow_set(state: str) -> None:
    normalized = state if state in {NEW_CONTACT_FLOW_IDLE, NEW_CONTACT_FLOW_OPEN, NEW_CONTACT_FLOW_SUBMITTING} else NEW_CONTACT_FLOW_IDLE
    st.session_state[NEW_CONTACT_FLOW_KEY] = normalized
    # Keep old keys synchronized for backward compatibility during transition.
    st.session_state["contact_create_confirm_open"] = normalized in {NEW_CONTACT_FLOW_OPEN, NEW_CONTACT_FLOW_SUBMITTING}
    st.session_state["contact_creating_in_progress"] = normalized == NEW_CONTACT_FLOW_SUBMITTING


def _new_contact_flow_open() -> None:
    _new_contact_flow_set(NEW_CONTACT_FLOW_OPEN)


def _new_contact_flow_start_submit(nombre: str) -> None:
    st.session_state["_create_contact_nombre"] = nombre
    _new_contact_flow_set(NEW_CONTACT_FLOW_SUBMITTING)


def _new_contact_flow_cancel() -> None:
    st.session_state.pop("dialog_new_contact_nombre", None)
    st.session_state.pop("_create_contact_nombre", None)
    st.session_state.pop(NEW_CONTACT_SIMILAR_CANDIDATES_KEY, None)
    st.session_state.pop(NEW_CONTACT_REQUIRE_SECOND_CONFIRM_KEY, None)
    st.session_state.pop(NEW_CONTACT_CONFIRM_OVERRIDE_KEY, None)
    _new_contact_flow_set(NEW_CONTACT_FLOW_IDLE)


def _new_contact_flow_finish(*, clear_inputs: bool = False) -> None:
    if clear_inputs:
        st.session_state.pop("dialog_new_contact_nombre", None)
    st.session_state.pop("_create_contact_nombre", None)
    st.session_state.pop(NEW_CONTACT_SIMILAR_CANDIDATES_KEY, None)
    st.session_state.pop(NEW_CONTACT_REQUIRE_SECOND_CONFIRM_KEY, None)
    st.session_state.pop(NEW_CONTACT_CONFIRM_OVERRIDE_KEY, None)
    _new_contact_flow_set(NEW_CONTACT_FLOW_IDLE)


def _normalize_contact_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _find_similar_contact_names(df: pd.DataFrame, new_name: str) -> tuple[bool, list[tuple[str, str]]]:
    target = _normalize_contact_name(new_name)
    if not target:
        return False, []
    exact = False
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in df.fillna("").astype(str).to_dict("records"):
        existing_name = str(row.get("nombre", "") or "").strip()
        existing_id = str(row.get("contact_id", "") or "").strip()
        existing_norm = _normalize_contact_name(existing_name)
        if not existing_norm:
            continue
        if existing_norm == target:
            exact = True
            item = (existing_name, existing_id)
            if item not in seen:
                seen.add(item)
                candidates.append(item)
            continue
        similar = (
            target in existing_norm
            or existing_norm in target
            or SequenceMatcher(None, target, existing_norm).ratio() >= 0.82
        )
        if similar:
            item = (existing_name, existing_id)
            if item not in seen:
                seen.add(item)
                candidates.append(item)
    return exact, candidates


def _clear_history_selection(contact_id: str, kind: str) -> None:
    clear_history_table_selection(contact_id, kind)


def _clear_sensor_picker_state(prefix: str) -> None:
    for suffix in (
        "_is_uc501",
        "_non_uc501_type",
        "_sensor_uc501_sn",
        "_sensor_ug67_sn",
        "_sensor_em500_sn",
        "_sensor_solenoide_sn",
        "_sensor_sim_sn",
        "_sensor_serial_number",
        "_id_historial",
    ):
        st.session_state.pop(f"{prefix}{suffix}", None)


def _history_delete_confirm_key(kind: str, row_id: str) -> str:
    safe_kind = "".join(c if c.isalnum() else "_" for c in kind)
    safe_row_id = "".join(c if c.isalnum() else "_" for c in row_id)
    return f"{HISTORY_DELETE_CONFIRM_PREFIX}_{safe_kind}_{safe_row_id}"


def _sensor_close_pending_values_key(row_id: str) -> str:
    safe_row_id = "".join(c if c.isalnum() else "_" for c in row_id)
    return f"sensor_close_pending_values_{safe_row_id}"


def _on_dismiss_history_edit() -> None:
    m = modal_state.get_active_modal()
    if m and m.get("type") == "edit_history":
        kind = m["kind"]
        contact_id = m["contact_id"]
        if kind == "sensores":
            row_id = str(m["row_id"])
            _clear_sensor_picker_state(f"{kind}_{row_id}")
            st.session_state.pop(_history_delete_confirm_key(kind, row_id), None)
        if kind == "incidencias":
            _clear_incidencia_association_state(f"{kind}_{m['row_id']}")
        modal_state.close_modal()
        _clear_history_selection(contact_id, kind)


def _on_dismiss_history_add() -> None:
    m = modal_state.get_active_modal()
    if m and m.get("type") == "add_history":
        if m.get("kind") == "sensores":
            _clear_sensor_picker_state("sensores_new")
        if m.get("kind") == "incidencias":
            _clear_incidencia_association_state("incidencias_new")
        modal_state.close_modal()


def _on_dismiss_sensor_close_location() -> None:
    m = modal_state.get_active_modal()
    if not m or m.get("type") != "sensor_close_location":
        return
    kind = str(m.get("kind", ""))
    contact_id = str(m.get("contact_id", ""))
    row_id = str(m.get("row_id", ""))
    if kind == "sensores" and row_id:
        _clear_sensor_picker_state(f"{kind}_{row_id}")
        st.session_state.pop(_sensor_close_pending_values_key(row_id), None)
    modal_state.close_modal()
    if contact_id and kind:
        _clear_history_selection(contact_id, kind)


def _is_sensor_history_open(row: dict[str, str]) -> bool:
    """Match HistoryService: open when estado is not explicitly cerrado."""
    return str(row.get("estado_cierre_sensor", "")).strip().lower() != "cerrado"


def _clear_contact_overlay_state(*, keep_contact_id: str = "") -> None:
    """Clear transient contact UI overlays/toggles that should not persist."""
    _clear_modal_flags()
    for key in list(st.session_state.keys()):
        if key.startswith("show_history_"):
            # Keep current contact section toggles only if requested.
            if keep_contact_id and key.endswith(f"_{keep_contact_id}"):
                continue
            st.session_state.pop(key, None)
        if key.startswith("hist_table_select_") or key.startswith("hist_table_version_"):
            st.session_state.pop(key, None)
    target_id = str(st.session_state.get(CONTACTS_DELETE_TARGET_ID_KEY, "") or "")
    if target_id and target_id != str(keep_contact_id or ""):
        st.session_state.pop(CONTACTS_DELETE_TARGET_ID_KEY, None)
        st.session_state.pop(CONTACTS_DELETE_TARGET_NAME_KEY, None)


def _set_delete_target(contact_id: str, nombre: str) -> None:
    st.session_state[CONTACTS_DELETE_TARGET_ID_KEY] = str(contact_id or "")
    st.session_state[CONTACTS_DELETE_TARGET_NAME_KEY] = str(nombre or "")


def _clear_delete_target() -> None:
    st.session_state.pop(CONTACTS_DELETE_TARGET_ID_KEY, None)
    st.session_state.pop(CONTACTS_DELETE_TARGET_NAME_KEY, None)


def render(df: pd.DataFrame) -> pd.DataFrame:
    with timed("contacts.render"):
        write_status = get_contacts_write_status()
        if write_status.get("status") == "ambiguous":
            st.warning(write_status.get("message") or "Guardado en verificación. Pulsa Recargar datos si no ves cambios.")
        elif write_status.get("status") == "failed":
            st.error(write_status.get("message") or "No se pudo confirmar el guardado.")
        if write_status.get("status"):
            clear_contacts_write_status()
        pending_id = pop_pending_created_contact_id()
        if pending_id and "contact_id" in df.columns:
            exists_pending = not df[df["contact_id"].astype(str).str.strip() == pending_id].empty
            if exists_pending:
                st.session_state["selected_contact_id"] = pending_id
        # If selected contact changed, purge per-contact transient overlays.
        current_selected = reconcile_selected_contact_id(df, str(st.session_state.get("selected_contact_id", "") or ""))
        st.session_state["selected_contact_id"] = current_selected
        last_selected = str(st.session_state.get("_contacts_last_selected_id", "") or "")
        if current_selected != last_selected:
            _clear_contact_overlay_state(keep_contact_id=current_selected)
            st.session_state["_contacts_last_selected_id"] = current_selected

        render_page_header("Contactos")
        # Toast en vez de banner: no desplaza el contenido de la página al
        # confirmar un guardado/borrado, así la vista no "salta".
        if st.session_state.get(CONTACTS_SAVE_SUCCESS_KEY):
            st.toast(str(st.session_state.pop(CONTACTS_SAVE_SUCCESS_KEY)), icon="✅")
        if st.session_state.get(CONTACTS_DELETE_SUCCESS_KEY):
            st.toast(str(st.session_state.pop(CONTACTS_DELETE_SUCCESS_KEY)), icon="🗑️")
        if df.empty:
            st.warning("No hay contactos cargados. Puedes crear el primero desde el formulario inferior.")

        left, right = st.columns([0.38, 0.62], gap="large")
        with left:
            selected_id = _render_contact_list(df)
        with right:
            with st.container(border=True):
                if selected_id:
                    st.markdown(f"##### {_contact_display_name(df, selected_id)}")
                    df = _render_contact_detail(df, selected_id)
                else:
                    st.markdown("##### Ficha del contacto")
                    st.info("Selecciona un contacto para abrir la ficha.")
        return df


def _render_contact_list(df: pd.DataFrame) -> str:
    if CONTACTS_VIEW_MODE_KEY not in st.session_state:
        st.session_state[CONTACTS_VIEW_MODE_KEY] = CONTACTS_VIEW_FICHA
    acciones_df = load_acciones_cached(st.session_state.get("history_cache_version", 0))
    df = enrich_contacts_with_proxima(df, acciones_df)
    with st.container(border=True):
        _render_next_action_strip(df)
    _contacts_block_spacer()
    if "contact_filters_open" not in st.session_state:
        st.session_state.contact_filters_open = False
    if CONTACTS_SHOW_LOST_KEY not in st.session_state:
        # Soft migration from legacy filter key if present.
        st.session_state[CONTACTS_SHOW_LOST_KEY] = bool(st.session_state.get("contact_filter_show_lost", False))

    with st.container(border=True):
        st.markdown("##### Buscar")
        overview = load_contact_sensor_overview_cached(st.session_state.get("history_cache_version", 0))
        # Búsqueda SIEMPRE visible: escribir y listo, sin abrirla antes.
        search_row = st.columns([0.84, 0.16], gap="small")
        query = search_row[0].text_input(
            "Buscar",
            key="contact_filter_text",
            label_visibility="collapsed",
            placeholder="Nombre, municipio, correo, teléfono, cultivo…",
            icon=":material/search:",
        )
        if search_row[1].button(
            "Filtros",
            key="contact_toggle_filters",
            icon=":material/tune:",
            width="stretch",
            help="Filtros por estado, provincia, municipio, tipo o cultivo",
            type="primary" if st.session_state.contact_filters_open else "secondary",
        ):
            st.session_state.contact_filters_open = not st.session_state.contact_filters_open
            st.rerun()
        toggles_row = st.columns(2, gap="small")
        toggles_row[0].toggle("Mostrar perdidos", key=CONTACTS_SHOW_LOST_KEY)
        toggles_row[1].toggle("Con sensores", key=CONTACTS_ONLY_WITH_SENSORS_KEY)

        province = ""
        status = ""
        entity_type = ""
        municipio = ""
        cultivos_filter = ""
        if st.session_state.contact_filters_open:
            filter_row_1 = st.columns([1.2, 1.2, 1.2], gap="small")
            status = filter_row_1[0].selectbox("Estado", [""] + list(CONTACT_ESTADO_OPCIONES), key="contact_filter_status")
            province = filter_row_1[1].selectbox(
                "Provincia",
                [""] + sorted([x for x in df.get("provincia", pd.Series(dtype=str)).fillna("").astype(str).unique() if x]),
                key="contact_filter_province",
            )
            entity_type = filter_row_1[2].selectbox(
                "Tipo de entidad",
                [""] + sorted([x for x in df.get("tipo_entidad", pd.Series(dtype=str)).fillna("").astype(str).unique() if x]),
                key="contact_filter_entity",
            )
            filter_row_2 = st.columns([1.2, 1.2], gap="small")
            municipio = filter_row_2[0].selectbox(
                "Municipio",
                [""] + sorted([x for x in df.get("municipio", pd.Series(dtype=str)).fillna("").astype(str).unique() if x]),
                key="contact_filter_municipio",
            )
            cultivos_filter = filter_row_2[1].text_input("Cultivos contiene", key="contact_filter_cultivos")
    _contacts_block_spacer()
    filtered = filter_dataframe(
        df,
        query,
        ["nombre", "municipio", "provincia", "correo", "telefono", "cultivos", "contact_id"],
    )
    if province:
        filtered = filtered[filtered["provincia"].astype(str) == province]
    if status:
        filtered = filtered[filtered["estado"].astype(str) == status]
    if entity_type:
        filtered = filtered[filtered["tipo_entidad"].astype(str) == entity_type]
    if municipio:
        filtered = filtered[filtered["municipio"].astype(str) == municipio]
    if (cultivos_filter or "").strip():
        filtered = filtered[
            filtered["cultivos"].fillna("").astype(str).str.contains(cultivos_filter.strip(), case=False, na=False)
        ]
    if not bool(st.session_state.get(CONTACTS_SHOW_LOST_KEY, True)):
        filtered = filtered[~filtered["estado"].astype(str).map(is_contact_perdido)]
    persona_proxima = str(st.session_state.get(DASH_PERSONA_PROXIMA_ACCION_KEY, "") or "")
    filtered = filter_by_persona_proxima_accion(filtered, persona_proxima)
    dash_responsable = str(st.session_state.get(DASH_RESPONSABLE_FILTER_KEY, "") or "")
    filtered = filter_by_responsable_cliente(filtered, dash_responsable)
    dash_estado = str(st.session_state.get(DASH_ESTADO_FILTER_KEY, "") or "")
    filtered = filter_by_contact_estado(filtered, dash_estado)
    dash_bucket = st.session_state.get("dash_bucket", "")
    if dash_bucket:
        filtered = apply_dash_bucket_date_filter(filtered, str(dash_bucket))
    if bool(st.session_state.get(CONTACTS_ONLY_WITH_SENSORS_KEY, False)):
        filtered = filter_by_sensor_overview(filtered, overview, only_with_sensors=True)
    filtered = pin_oficina_contact_first(filtered)
    filtered = filtered.reset_index(drop=True)

    st.session_state[CONTACTS_FILTERED_IDS_KEY] = (
        filtered["contact_id"].fillna("").astype(str).str.strip().tolist()
        if not filtered.empty and "contact_id" in filtered.columns
        else []
    )

    view_mode = st.session_state.get(CONTACTS_VIEW_MODE_KEY, CONTACTS_VIEW_FICHA)
    with st.container(border=True):
        st.markdown("##### Contactos")
        if st.button("Nuevo contacto", key="create_contact_top", width="stretch"):
            _new_contact_flow_open()
            st.rerun()
        view_col1, view_col2 = st.columns(2, gap="small")
        if view_col1.button(
            "Ver lista",
            key="contacts_view_tabla",
            width="stretch",
            type="secondary",
        ):
            _contact_overview_list_dialog()
        if view_col2.button(
            "Ver ficha",
            key="contacts_view_ficha",
            width="stretch",
            type="primary" if view_mode == CONTACTS_VIEW_FICHA else "secondary",
        ):
            st.session_state[CONTACTS_VIEW_MODE_KEY] = CONTACTS_VIEW_FICHA
            st.rerun()
        if _new_contact_flow_state_get() in {NEW_CONTACT_FLOW_OPEN, NEW_CONTACT_FLOW_SUBMITTING}:
            _render_create_contact_confirmation(df)

        st.caption(f"{len(filtered)} contactos encontrados")
        st.caption("Haz click en una fila para abrir la ficha automáticamente.")
        current = st.session_state.get("selected_contact_id", "")
        semaforo_map = semaforo_by_contact_id(overview)
        selected_from_table = _render_contact_table(filtered, current, semaforo_map)
        if selected_from_table:
            current = selected_from_table
        selected_id = selected_from_table or current
        if selected_id:
            st.session_state.selected_contact_id = selected_id
        elif st.session_state.get("selected_contact_id") and "contact_id" in filtered.columns:
            selected_raw = str(st.session_state.get("selected_contact_id") or "")
            exists = not filtered[filtered["contact_id"].astype(str).str.strip() == selected_raw].empty
            if not exists:
                st.session_state.selected_contact_id = ""
        return selected_id


def _render_contact_table(
    filtered: pd.DataFrame,
    selected_contact_id: str,
    semaforo_map: dict[str, str] | None = None,
) -> str:
    if filtered.empty:
        st.info("No hay datos para mostrar.")
        return ""

    semaforo_lookup = semaforo_map or {}
    panel_height = (
        CONTACT_LIST_PANEL_HEIGHT_WITH_DETAIL
        if (selected_contact_id or "").strip()
        else CONTACT_LIST_PANEL_HEIGHT_BASE
    )
    with st.container(height=panel_height):
        st.markdown(
            "<div class='sanzar-contact-table'>"
            "<div class='sanzar-contact-row sanzar-contact-header'>"
            "<span>Nombre</span><span>Estado</span><span>Provincia</span><span>Municipio</span>"
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        for row in filtered.fillna("").astype(str).to_dict("records"):
            contact_id = row.get("contact_id", "")
            is_lost = is_contact_perdido(str(row.get("estado", "")))
            sem = semaforo_lookup.get(str(contact_id).strip(), "sin_sensores")
            prefix = "🔴 " if is_lost else semaforo_display_prefix(sem, is_lost=False)
            nombre_raw = row.get("nombre", "") or "Sin nombre"
            row_label = " | ".join(
                [
                    nombre_raw,
                    row.get("estado", "") or "Sin estado",
                    row.get("provincia", "") or "Sin provincia",
                    row.get("municipio", "") or "Sin municipio",
                ]
            )
            if prefix:
                row_label = f"{prefix}{row_label}"
            if contact_id == selected_contact_id:
                row_class = "sanzar-contact-row selected sanzar-contact-row-lost" if is_lost else "sanzar-contact-row selected"
                nombre_display = f"{prefix}{nombre_raw}"
                estado_html = (
                    chip(row.get("estado", "") or "Sin estado", contact_status_style(row.get("estado", "")))
                    if row.get("estado", "")
                    else html.escape(row.get("estado", ""))
                )
                st.markdown(
                    f"<div class='{row_class}'>"
                    f"<span class='sanzar-contact-cell'>{html.escape(nombre_display)}</span>"
                    f"<span class='sanzar-contact-cell'>{estado_html}</span>"
                    f"<span class='sanzar-contact-cell'>{html.escape(row.get('provincia', ''))}</span>"
                    f"<span class='sanzar-contact-cell'>{html.escape(row.get('municipio', ''))}</span>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                continue
            if st.button(row_label, key=f"contact_row_{contact_id}", width="stretch"):
                _clear_modal_flags()
                st.session_state.selected_contact_id = contact_id
                st.rerun()
    return ""


@st.dialog("Vista resumen — contactos", width="large")
def _contact_overview_list_dialog() -> None:
    render_contact_overview_dialog_content(_filtered_overview_display_df())


@st.dialog("Nuevo contacto")
def _create_contact_dialog(df: pd.DataFrame) -> None:
    flow_state = _new_contact_flow_state_get()
    if flow_state == NEW_CONTACT_FLOW_IDLE:
        return
    if flow_state == NEW_CONTACT_FLOW_SUBMITTING:
        try:
            with st.spinner("Creando nuevo contacto..."):
                nombre_crear = st.session_state.pop("_create_contact_nombre", "").strip()
                new_df, new_contact_id, verify = create_empty_contact(
                    df,
                    sheets_service(),
                    nombre=nombre_crear,
                )
                set_pending_created_contact_id(new_contact_id)
                bump_contacts_cache()
                set_contacts_df_override(new_df)
                if verify.status != "confirmed":
                    set_contacts_write_status(
                        verify.status,
                        message=verify.message or "Contacto creado pero pendiente de verificación remota.",
                    )
                select_contact(new_contact_id)
                _new_contact_flow_finish(clear_inputs=True)
            st.rerun()
        except Exception as exc:
            st.session_state.pop("_create_contact_nombre", None)
            _new_contact_flow_set(NEW_CONTACT_FLOW_OPEN)
            st.error(
                "No se pudo crear el contacto de forma consistente. "
                "Comprueba conexión/cuota y vuelve a confirmar. "
                f"Detalle: {exc}"
            )

    st.markdown("Introduce el **nombre** del nuevo contacto y confirma para crear la ficha.")
    similar_candidates = st.session_state.get(NEW_CONTACT_SIMILAR_CANDIDATES_KEY, [])
    if similar_candidates:
        lines = "\n".join([f"- {name} ({cid})" if cid else f"- {name}" for name, cid in similar_candidates])
        st.warning(
            "Existen contactos con nombres similares:\n\n"
            f"{lines}\n\n"
            "¿Estás seguro de crear este contacto? Pulsa confirmar de nuevo para continuar."
        )
    st.text_input(
        "Nombre del contacto",
        key="dialog_new_contact_nombre",
        placeholder="Ej. Cooperativa San José",
    )
    col_confirm, col_cancel = st.columns(2)
    with col_confirm:
        if st.button("Confirmar", width="stretch", key="btn_save_create_contact"):
            nombre_val = str(st.session_state.get("dialog_new_contact_nombre", "")).strip()
            if not nombre_val:
                st.error("Introduce un nombre para el contacto.")
                return
            exact_match, similars = _find_similar_contact_names(df, nombre_val)
            if exact_match:
                st.error("Ya existe este contacto.")
                return
            require_second = bool(st.session_state.get(NEW_CONTACT_REQUIRE_SECOND_CONFIRM_KEY, False))
            override_ok = bool(st.session_state.get(NEW_CONTACT_CONFIRM_OVERRIDE_KEY, False))
            if similars and not (require_second and override_ok):
                st.session_state[NEW_CONTACT_SIMILAR_CANDIDATES_KEY] = similars
                st.session_state[NEW_CONTACT_REQUIRE_SECOND_CONFIRM_KEY] = True
                st.session_state[NEW_CONTACT_CONFIRM_OVERRIDE_KEY] = True
                st.rerun()
            st.session_state.pop(NEW_CONTACT_SIMILAR_CANDIDATES_KEY, None)
            st.session_state.pop(NEW_CONTACT_REQUIRE_SECOND_CONFIRM_KEY, None)
            st.session_state.pop(NEW_CONTACT_CONFIRM_OVERRIDE_KEY, None)
            _new_contact_flow_start_submit(nombre_val)
            st.rerun()
    with col_cancel:
        if st.button("Cancelar", width="stretch", key="cancel_create_contact_dialog"):
            _new_contact_flow_cancel()
            st.rerun()


def _render_create_contact_confirmation(df: pd.DataFrame) -> None:
    _create_contact_dialog(df)


def _actor_name() -> str:
    """Return the display name of the currently logged-in user."""
    uid = auth.get_authenticated_user_id()
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    for u in users:
        if u.employee_id == uid:
            return u.nombre
    return uid


def _log_contact_save_actions(
    original: dict[str, str],
    values: dict[str, str],
    actor: str,
) -> None:
    """Reserved for future audit; seguimiento comercial ya no se registra desde la ficha Contactos."""
    _ = (original, values, actor)


def _render_delete_contact_confirmation(*, contact_id: str, nombre: str) -> None:
    """Panel de confirmación tras pulsar «Eliminar contacto» en el formulario."""
    target_id = str(st.session_state.get(CONTACTS_DELETE_TARGET_ID_KEY, "") or "")
    target_name = str(st.session_state.get(CONTACTS_DELETE_TARGET_NAME_KEY, "") or "").strip() or nombre
    if target_id and target_id == str(contact_id):
        st.warning(
            f"**Vas a eliminar permanentemente** a «**{html.escape(target_name)}**» (`{html.escape(target_id)}`). "
            "Se borrarán la fila en **Contactos**, todas las filas de histórico ligadas a este id y las entradas en "
            "**Acciones**. **No se puede deshacer.**"
        )
        c_yes, c_no = st.columns(2)
        if c_yes.button("Confirmar eliminación", type="primary", key=f"btn_destruct_contact_del_{target_id}"):
            try:
                with st.spinner("Eliminando en Google Sheets…"):
                    delete_contact_and_related_data(sheets_service(), target_id)
                clear_all_cache()
                bump_contacts_cache()
                bump_history_cache()
                _clear_delete_target()
                select_contact("")
                st.session_state[CONTACTS_DELETE_SUCCESS_KEY] = "Contacto y datos relacionados eliminados."
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo eliminar el contacto: {exc}")
        if c_no.button("Cancelar", key=f"btn_delete_no_{target_id}"):
            _clear_delete_target()
            st.rerun()


def _render_contact_detail(df: pd.DataFrame, contact_id: str) -> pd.DataFrame:
    matches = df[df["contact_id"].astype(str) == str(contact_id)]
    if matches.empty:
        st.error("El contacto seleccionado no existe en la tabla actual.")
        return df
    row_idx = matches.index[0]
    contact = matches.iloc[0].fillna("").astype(str).to_dict()

    hs = history_service()
    subscription_status = hs.subscription_status_for_contact(contact_id)
    open_incidents = hs.has_open_incidents(contact_id)
    acciones_df = load_acciones_cached(st.session_state.get("history_cache_version", 0))
    enriched = enrich_contacts_with_proxima(
        pd.DataFrame([contact]),
        acciones_df,
    )
    header_contact = enriched.iloc[0].fillna("").astype(str).to_dict() if not enriched.empty else contact
    last_contact = latest_commercial_contact_row(acciones_df, contact_id)

    render_contact_detail_header(
        contact=header_contact,
        contact_id=contact_id,
        subscription_status=subscription_status,
        open_incidents=open_incidents,
        last_contact=last_contact,
    )
    if st.toggle(
        "Mostrar línea de tiempo (sensores, campañas, pagos e incidencias)",
        value=False,
        key=f"contact_timeline_visible_{contact_id}",
    ):
        render_contact_timeline_block(contact_id)
    st.divider()
    view_mode = st.radio(
        "Vista de ficha",
        ("Datos", "Históricos"),
        horizontal=True,
        key=f"contact_detail_view_mode_{contact_id}",
    )
    if view_mode == "Datos":
        updated = _render_contact_form(df, row_idx, contact)
    else:
        updated = None
        _render_history_kind_section(contact, "seguimiento_comercial")
        for kind in ("sensores", "campanas", "suscripciones", "incidencias"):
            _render_history_kind_section(contact, kind)
        _maybe_render_sensor_close_location_modal(contact)
    _maybe_render_add_history_modal(contact)
    _maybe_render_edit_history_modal(contact)
    return updated if updated is not None else df


def _render_contact_form(df: pd.DataFrame, row_idx: int, contact: dict[str, str]) -> pd.DataFrame | None:
    st.subheader("Ficha del cliente")
    sections_left: list[tuple[str, list[str]]] = [
        ("Identificación", ["nombre", "tipo_entidad", "detalle"]),
        ("Localización", ["país", "provincia", "municipio", "coordenadas", "direccion"]),
        ("Contacto", ["telefono", "correo", "otros_contactos"]),
        ("Perfil agrícola", ["cultivos", "superficie_ha", "tipo_riego"]),
        (
            "Lead",
            [
                "fuente_lead",
                "lead_detalle",
                "fecha_primer_contacto",
                "persona_primer_contacto",
            ],
        ),
    ]
    sections_right: list[tuple[str, list[str]]] = [
        (
            "Estado y oportunidad",
            ["estado", "fecha_estado", "razon_perdida", "valor", "responsable_cliente", "tipo_relacion"],
        ),
        ("Operativa y suscripción", ["cuenta_usuario", "digital_maps", "iot_module", "sowing_module"]),
    ]

    with st.form(f"contact_form_{contact['contact_id']}"):
        values: dict[str, str] = {}
        values["contact_id"] = st.text_input(
            "Contact id",
            value=contact.get("contact_id", ""),
            disabled=True,
            key=f"{contact.get('contact_id', 'new')}_contact_id",
        )
        col_left, col_right = st.columns(2, gap="large")
        with col_left:
            _render_form_sections(values, contact, sections_left, section_key="left")
        with col_right:
            _render_form_sections(values, contact, sections_right, section_key="right")
        st.caption("Los cambios no se aplican hasta pulsar **Guardar ficha**.")
        col_save, col_del = st.columns(2, gap="small")
        submitted_save = col_save.form_submit_button(
            "Guardar ficha",
            type="primary",
            width="stretch",
            key="btn_save_contact_ficha",
        )
        submitted_delete = col_del.form_submit_button(
            "Eliminar contacto…",
            type="secondary",
            width="stretch",
            key="btn_destruct_contact_ficha",
            help="Borra la ficha, históricos (seguimiento comercial en Acciones, sensores, campañas, suscripciones, incidencias).",
        )

    cid = str(contact.get("contact_id", "") or "")
    nombre_ficha = str(contact.get("nombre", "") or "").strip() or "(sin nombre)"

    if submitted_delete:
        _set_delete_target(cid, nombre_ficha)
        st.rerun()

    if submitted_save:
        error = validate_contact_date_fields(values)
        if error:
            st.error(error)
            return None
        with st.spinner("Guardando ficha…"):
            cache_before = int(st.session_state.get("contacts_cache_version", 0))
            selected_before = str(st.session_state.get("selected_contact_id", "") or "")
            new_df, verify = save_contact_by_id(
                df,
                row_idx=row_idx,
                contact_id=contact["contact_id"],
                values=values,
                sheets=sheets_service(),
            )
            bump_contacts_cache()
            _log_contact_save_actions(contact, values, _actor_name())
            track_event(
                "contacts.save.consistency",
                0,
                verify.status == "confirmed",
                operation="update",
                contact_id=str(contact.get("contact_id", "") or ""),
                status=verify.status,
                attempt=verify.attempts,
                cache_version_before=cache_before,
                cache_version_after=int(st.session_state.get("contacts_cache_version", 0)),
                selected_contact_id_before=selected_before,
                selected_contact_id_after=str(contact.get("contact_id", "") or ""),
                override_used=True,
            )
        set_contacts_df_override(new_df)
        if verify.status == "confirmed":
            st.session_state[CONTACTS_SAVE_SUCCESS_KEY] = "Ficha guardada correctamente."
        elif verify.status == "ambiguous":
            set_contacts_write_status("ambiguous", message="Guardado enviado, pendiente de confirmación en Google Sheets.")
        else:
            set_contacts_write_status("failed", message=verify.message or "No se pudo confirmar el guardado.")
        st.session_state["selected_contact_id"] = str(contact.get("contact_id", "") or "")
        st.session_state["active_page"] = "Contactos"
        st.session_state["pending_nav_page"] = "Contactos"
        st.rerun()
        return new_df

    _render_delete_contact_confirmation(contact_id=cid, nombre=nombre_ficha)
    return None


def _render_form_sections(
    values: dict[str, str],
    contact: dict[str, str],
    sections: list[tuple[str, list[str]]],
    section_key: str,
) -> None:
    for title, columns in sections:
        st.markdown(
            f"<div class='sanzar-form-section-title'>{html.escape(title)}</div>",
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            col_count = 1 if title == "Operativa y suscripción" else 2
            cols = st.columns(col_count)
            for idx, column in enumerate(columns):
                with cols[idx % col_count]:
                    values[column] = _render_contact_field_input(
                        column,
                        contact.get(column, ""),
                        key=f"contact_{contact.get('contact_id', 'new')}_{section_key}_{column}",
                    )


def _maybe_render_sensor_close_location_modal(contact: dict[str, str]) -> None:
    m = modal_state.get_active_modal()
    if not m or m.get("type") != "sensor_close_location":
        return
    contact_id = contact.get("contact_id", "")
    if m.get("contact_id") != contact_id:
        return
    kind = m["kind"]
    row_id = m["row_id"]
    spec = HISTORY_SPECS.get(kind)
    if spec is None:
        return
    rows = history_service().rows_for_contact(kind, contact_id)
    row = next((item for item in rows if str(item.get(spec.id_column, "")) == row_id), None)
    if row is None:
        return
    _sensor_close_location_dialog(kind, contact, row)


def _maybe_render_add_history_modal(contact: dict[str, str]) -> None:
    m = modal_state.get_active_modal()
    if not m or m.get("type") != "add_history":
        return
    if m.get("contact_id") != contact.get("contact_id", ""):
        return
    _add_history_dialog(m["kind"], contact)


def _maybe_render_edit_history_modal(contact: dict[str, str]) -> None:
    m = modal_state.get_active_modal()
    if not m or m.get("type") != "edit_history":
        return
    # sensor_close_location replaces edit_history until save/cancel
    contact_id = contact.get("contact_id", "")
    if m.get("contact_id") != contact_id:
        return
    kind = m["kind"]
    row_id = m["row_id"]
    spec = HISTORY_SPECS.get(kind)
    if spec is None:
        return
    rows = history_service().rows_for_contact(kind, contact_id)
    row = next((item for item in rows if str(item.get(spec.id_column, "")) == row_id), None)
    if row is None:
        return
    _edit_history_dialog(kind, contact, row)


def _incidencia_association_init_key(prefix: str) -> str:
    return f"{prefix}_incidencia_assoc_initialized"


def _clear_incidencia_association_state(prefix: str) -> None:
    for suffix in (
        "_incidencia_assoc_initialized",
        "_incidencia_sensor_pick",
        "_incidencia_campana_pick",
        "_incidencia_sensor_label_map",
        "_incidencia_campana_label_map",
        "_historial_sensor_id",
        "_sensor_serial_number",
        "_historial_campana_id",
        "_nombre_campana",
        "_incidencia_sensor_closed_legacy",
        "_incidencia_campana_closed_legacy",
        "_incidencia_sensor_touched",
        "_incidencia_campana_touched",
    ):
        st.session_state.pop(f"{prefix}{suffix}", None)


def _incidencia_label_maps(
    sensor_options: list[AssociationOption],
    campana_options: list[AssociationOption],
) -> tuple[dict[str, AssociationOption], dict[str, AssociationOption]]:
    return (
        {opt.label: opt for opt in sensor_options},
        {opt.label: opt for opt in campana_options},
    )


def _init_incidencia_association_state(prefix: str, contact_id: str, initial: dict[str, str]) -> None:
    init_key = _incidencia_association_init_key(prefix)
    if st.session_state.get(init_key):
        return
    st.session_state[init_key] = True

    sensor_rows = history_service().rows_for_contact("sensores", contact_id) if contact_id else []
    campana_rows = history_service().rows_for_contact("campanas", contact_id) if contact_id else []
    sensor_options = build_sensor_history_options(sensor_rows)
    campana_options = build_campana_history_options(campana_rows)
    sensor_label_map, campana_label_map = _incidencia_label_maps(sensor_options, campana_options)
    st.session_state[f"{prefix}_incidencia_sensor_label_map"] = sensor_label_map
    st.session_state[f"{prefix}_incidencia_campana_label_map"] = campana_label_map

    initial_sensor_id = str(initial.get("historial_sensor_id", "") or "").strip()
    initial_sensor_sn = str(initial.get("sensor_serial_number", "") or "").strip()
    initial_campana_id = str(initial.get("historial_campana_id", "") or "").strip()
    initial_campana_name = str(initial.get("nombre_campana", "") or "").strip()

    sensor_opt = option_by_id(sensor_options, initial_sensor_id)
    if sensor_opt:
        st.session_state[f"{prefix}_incidencia_sensor_pick"] = sensor_opt.label
        st.session_state[f"{prefix}_historial_sensor_id"] = sensor_opt.id
        st.session_state[f"{prefix}_sensor_serial_number"] = sensor_opt.sensor_serial_number
        st.session_state[f"{prefix}_incidencia_sensor_closed_legacy"] = False
    else:
        st.session_state[f"{prefix}_incidencia_sensor_pick"] = ""
        st.session_state[f"{prefix}_historial_sensor_id"] = initial_sensor_id
        st.session_state[f"{prefix}_sensor_serial_number"] = initial_sensor_sn
        st.session_state[f"{prefix}_incidencia_sensor_closed_legacy"] = bool(initial_sensor_id)

    campana_opt = option_by_id(campana_options, initial_campana_id)
    if campana_opt:
        st.session_state[f"{prefix}_incidencia_campana_pick"] = campana_opt.label
        st.session_state[f"{prefix}_historial_campana_id"] = campana_opt.id
        st.session_state[f"{prefix}_nombre_campana"] = campana_opt.nombre_campana
        st.session_state[f"{prefix}_incidencia_campana_closed_legacy"] = False
    else:
        st.session_state[f"{prefix}_incidencia_campana_pick"] = ""
        st.session_state[f"{prefix}_historial_campana_id"] = initial_campana_id
        st.session_state[f"{prefix}_nombre_campana"] = initial_campana_name
        st.session_state[f"{prefix}_incidencia_campana_closed_legacy"] = bool(initial_campana_id)

    st.session_state[f"{prefix}_incidencia_sensor_touched"] = False
    st.session_state[f"{prefix}_incidencia_campana_touched"] = False


def _sync_incidencia_sensor_pick(prefix: str) -> None:
    pick = str(st.session_state.get(f"{prefix}_incidencia_sensor_pick", "") or "")
    label_map: dict[str, AssociationOption] = st.session_state.get(f"{prefix}_incidencia_sensor_label_map", {})
    st.session_state[f"{prefix}_incidencia_sensor_touched"] = True
    if pick and pick in label_map:
        opt = label_map[pick]
        st.session_state[f"{prefix}_historial_sensor_id"] = opt.id
        st.session_state[f"{prefix}_sensor_serial_number"] = opt.sensor_serial_number
        st.session_state[f"{prefix}_incidencia_sensor_closed_legacy"] = False
    else:
        st.session_state[f"{prefix}_historial_sensor_id"] = ""
        st.session_state[f"{prefix}_sensor_serial_number"] = ""
        st.session_state[f"{prefix}_incidencia_sensor_closed_legacy"] = False


def _sync_incidencia_campana_pick(prefix: str) -> None:
    pick = str(st.session_state.get(f"{prefix}_incidencia_campana_pick", "") or "")
    label_map: dict[str, AssociationOption] = st.session_state.get(f"{prefix}_incidencia_campana_label_map", {})
    st.session_state[f"{prefix}_incidencia_campana_touched"] = True
    if pick and pick in label_map:
        opt = label_map[pick]
        st.session_state[f"{prefix}_historial_campana_id"] = opt.id
        st.session_state[f"{prefix}_nombre_campana"] = opt.nombre_campana
        st.session_state[f"{prefix}_incidencia_campana_closed_legacy"] = False
    else:
        st.session_state[f"{prefix}_historial_campana_id"] = ""
        st.session_state[f"{prefix}_nombre_campana"] = ""
        st.session_state[f"{prefix}_incidencia_campana_closed_legacy"] = False


def _resolve_incidencia_assoc_field(
    prefix: str,
    existing: dict[str, str] | None,
    header: str,
) -> str:
    if header in {"historial_sensor_id", "sensor_serial_number"}:
        touched = bool(st.session_state.get(f"{prefix}_incidencia_sensor_touched"))
        legacy = bool(st.session_state.get(f"{prefix}_incidencia_sensor_closed_legacy"))
    else:
        touched = bool(st.session_state.get(f"{prefix}_incidencia_campana_touched"))
        legacy = bool(st.session_state.get(f"{prefix}_incidencia_campana_closed_legacy"))
    if not touched and legacy and existing:
        return str(existing.get(header, "") or "")
    return str(st.session_state.get(f"{prefix}_{header}", "") or "")


def _render_incidencia_association_block(prefix: str, contact_id: str, initial: dict[str, str]) -> None:
    _init_incidencia_association_state(prefix, contact_id, initial)
    sensor_label_map: dict[str, AssociationOption] = st.session_state.get(
        f"{prefix}_incidencia_sensor_label_map", {}
    )
    campana_label_map: dict[str, AssociationOption] = st.session_state.get(
        f"{prefix}_incidencia_campana_label_map", {}
    )
    sensor_options = [""] + list(sensor_label_map.keys())
    campana_options = [""] + list(campana_label_map.keys())

    st.markdown("**Asociaciones**")
    with st.container(border=True):
        st.selectbox(
            "Histórico sensor",
            sensor_options,
            key=f"{prefix}_incidencia_sensor_pick",
            on_change=_sync_incidencia_sensor_pick,
            args=(prefix,),
        )
        display_sn = str(st.session_state.get(f"{prefix}_sensor_serial_number", "") or "")
        st.text_input("Sensor serial number", value=display_sn or "—", disabled=True)
        if (
            st.session_state.get(f"{prefix}_incidencia_sensor_closed_legacy")
            and not st.session_state.get(f"{prefix}_incidencia_sensor_touched")
            and display_sn
        ):
            st.caption(
                "El sensor vinculado está cerrado. Elige uno abierto para reasociar "
                "o deja vacío para quitar la vinculación al guardar."
            )

        st.selectbox(
            "Histórico campaña",
            campana_options,
            key=f"{prefix}_incidencia_campana_pick",
            on_change=_sync_incidencia_campana_pick,
            args=(prefix,),
        )
        display_camp = str(st.session_state.get(f"{prefix}_nombre_campana", "") or "")
        st.text_input("Nombre campaña", value=display_camp or "—", disabled=True)
        if (
            st.session_state.get(f"{prefix}_incidencia_campana_closed_legacy")
            and not st.session_state.get(f"{prefix}_incidencia_campana_touched")
            and display_camp
        ):
            st.caption(
                "La campaña vinculada está cerrada. Elige una abierta para reasociar "
                "o deja vacío para quitar la vinculación al guardar."
            )


@st.dialog("Nuevo histórico", on_dismiss=_on_dismiss_history_add)
def _add_history_dialog(kind: str, contact: dict[str, str]) -> None:
    spec = HISTORY_SPECS[kind]
    st.markdown(f"### {spec.title}")
    st.caption("Completa los campos y confirma para crear el nuevo registro.")

    # For sensores, render the sensor picker OUTSIDE the form — the dialog
    # supports reruns from non-form widgets, so the association panel updates
    # immediately when the user selects an asset.
    excluded: frozenset[str] = frozenset()
    incidencia_prefix = ""
    if kind == "sensores":
        excluded = frozenset({"sensor_serial_number"})
        prefix = f"{kind}_new"
        st.markdown("**Sensor**")
        _render_sensor_serial_field("", prefix, f"{prefix}_sensor_serial_number", exclude_hist_id="")
    elif kind == "incidencias":
        excluded = _INCIDENCIA_ASSOC_HEADERS
        incidencia_prefix = f"{kind}_new"
        initial = {header: "" for header in spec.headers}
        initial["contact_id"] = str(contact.get("contact_id", "") or "")
        _render_incidencia_association_block(incidencia_prefix, initial["contact_id"], initial)
    elif kind == "seguimiento_comercial":
        excluded = _SEGUIMIENTO_CANAL_FIELDS
        prefix, initial = _seguimiento_modal_initial(kind, contact, None)
        _render_seguimiento_canal_block(prefix, initial)

    with st.form(f"history_add_modal_{kind}_{contact.get('contact_id', '')}"):
        if kind == "incidencias":
            _render_history_form_grouped_body(kind, contact, None, excluded_headers=excluded)
        else:
            _render_history_form_body(kind, contact, None, excluded_headers=excluded)
        action_cols = st.columns(2)
        confirm = action_cols[0].form_submit_button("Confirmar", width="stretch")
        cancel = action_cols[1].form_submit_button("Cancelar", width="stretch")

    if cancel:
        _clear_modal_flags()
        if kind == "sensores":
            _clear_sensor_picker_state("sensores_new")
        if kind == "incidencias":
            _clear_incidencia_association_state(incidencia_prefix)
        st.rerun()

    if confirm:
        if _submit_history_form(kind, contact, None):
            _clear_modal_flags()
            if kind == "incidencias":
                _clear_incidencia_association_state(incidencia_prefix)
            st.rerun()


def _delete_history_row_and_sync_inventory(kind: str, row: dict[str, str]) -> None:
    spec = HISTORY_SPECS[kind]
    affected_serials: list[str] = []
    if kind == "sensores":
        affected_serials = _serials_from_sensor_history_strings([str(row.get("sensor_serial_number", "") or "")])
    history_service().delete_row(kind, str(row.get(spec.id_column, "")))
    if kind == "sensores":
        _reconcile_inventory_locations_for_sensor_serials(affected_serials, default_location_type="por_definir")


@st.dialog("Editar histórico", on_dismiss=_on_dismiss_history_edit)
def _edit_history_dialog(kind: str, contact: dict[str, str], row: dict[str, str]) -> None:
    spec = HISTORY_SPECS[kind]
    contact_id = contact.get("contact_id", "")
    row_id = str(row.get(spec.id_column, "") or "")
    st.markdown(f"### {spec.title}")
    st.caption("Edita la fila seleccionada. Puedes guardar, cancelar o borrar.")

    delete_confirm_key = _history_delete_confirm_key(kind, row_id)
    if kind == "sensores" and bool(st.session_state.get(delete_confirm_key, False)):
        st.warning(
            "¿Seguro que quieres borrar este histórico sensor? Se eliminará la fila del histórico "
            "y se recalculará la ubicación en Inventario para los seriales afectados."
        )
        c_confirm, c_cancel = st.columns(2)
        if c_confirm.button("Confirmar borrado", type="primary", width="stretch", key=f"{delete_confirm_key}_yes"):
            try:
                _delete_history_row_and_sync_inventory(kind, row)
                bump_history_cache()
                st.success("Histórico eliminado correctamente.")
                st.session_state.pop(delete_confirm_key, None)
                _clear_modal_flags()
                _clear_history_selection(contact_id, kind)
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo eliminar el histórico: {exc}")
        if c_cancel.button("Cancelar", width="stretch", key=f"{delete_confirm_key}_no"):
            st.session_state.pop(delete_confirm_key, None)
            st.rerun()
        return

    # For sensores, render the sensor picker OUTSIDE the form — reruns work
    # inside @st.dialog for non-form widgets.
    excluded: frozenset[str] = frozenset()
    incidencia_prefix = ""
    if kind == "sensores":
        excluded = frozenset({"sensor_serial_number"})
        hist_id = row_id
        prefix = f"{kind}_{hist_id}"
        st.markdown("**Sensor**")
        _render_sensor_serial_field(
            row.get("sensor_serial_number", ""),
            prefix,
            f"{prefix}_sensor_serial_number",
            exclude_hist_id=hist_id,
        )
    elif kind == "incidencias":
        excluded = _INCIDENCIA_ASSOC_HEADERS
        incidencia_prefix = f"{kind}_{row_id}"
        initial = {header: str(row.get(header, "") or "") for header in spec.headers}
        _render_incidencia_association_block(incidencia_prefix, contact_id, initial)
    elif kind == "seguimiento_comercial":
        excluded = _SEGUIMIENTO_CANAL_FIELDS
        prefix, initial = _seguimiento_modal_initial(kind, contact, row)
        _render_seguimiento_canal_block(prefix, initial)

    with st.form(f"history_edit_modal_{kind}_{row.get(spec.id_column, '')}"):
        _render_history_form_grouped_body(kind, contact, row, excluded_headers=excluded)
        action_cols = st.columns(3)
        confirm = action_cols[0].form_submit_button("Guardar", width="stretch")
        cancel = action_cols[1].form_submit_button("Cancelar", width="stretch")
        delete = action_cols[2].form_submit_button("Borrar", width="stretch")

    if cancel:
        if kind == "sensores":
            _clear_sensor_picker_state(f"{kind}_{row_id}")
            st.session_state.pop(delete_confirm_key, None)
            st.session_state.pop(_sensor_close_pending_values_key(row_id), None)
        if kind == "incidencias":
            _clear_incidencia_association_state(incidencia_prefix)
        _clear_modal_flags()
        _clear_history_selection(contact_id, kind)
        st.rerun()

    if delete:
        if kind == "sensores":
            st.session_state[delete_confirm_key] = True
            st.rerun()
            return
        try:
            _delete_history_row_and_sync_inventory(kind, row)
            bump_history_cache()
            st.success("Histórico eliminado correctamente.")
            _clear_modal_flags()
            _clear_history_selection(contact_id, kind)
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo eliminar el histórico: {exc}")

    if confirm:
        was_open = _is_sensor_history_open(row)
        now_closed = str(st.session_state.get(f"{kind}_{row.get(spec.id_column, '')}_estado_cierre_sensor", "")).strip().lower() == "cerrado"
        if kind == "sensores" and was_open and now_closed:
            prefix = f"{kind}_{row_id}"
            pending_values: dict[str, str] = {}
            for header in spec.headers:
                if header in {spec.id_column, "contact_id", "nombre_cliente", "created_at", "updated_at"}:
                    continue
                pending_values[header] = str(st.session_state.get(f"{prefix}_{header}", ""))
            st.session_state[_sensor_close_pending_values_key(row_id)] = pending_values
            modal_state.open_sensor_close_location_modal(kind, contact_id, row_id)
            st.rerun()
            return
        if _submit_history_form(kind, contact, row):
            _clear_modal_flags()
            if kind == "incidencias":
                _clear_incidencia_association_state(incidencia_prefix)
            _clear_history_selection(contact_id, kind)
            st.rerun()


@st.dialog("Ubicación al cerrar histórico sensor", on_dismiss=_on_dismiss_sensor_close_location)
def _sensor_close_location_dialog(kind: str, contact: dict[str, str], row: dict[str, str]) -> None:
    spec = HISTORY_SPECS[kind]
    row_id = str(row.get(spec.id_column, "") or "")
    contact_id = str(contact.get("contact_id", "") or "")
    pending_values = st.session_state.get(_sensor_close_pending_values_key(row_id), None)
    st.markdown("**Cierre de histórico sensor**")
    st.caption(
        "En inventario, los activos pasarán a **por definir** (no están asignados al cliente "
        "de este histórico). Si el equipo vuelve a almacén u oficina, regístralo con el "
        "**contacto Oficina** como cualquier otro cliente — aquí no se usa la ubicación «oficina» del inventario."
    )
    c1, c2 = st.columns(2)
    if c1.button("Guardar cierre", type="primary", width="stretch"):
        if _submit_history_form(
            kind,
            contact,
            row,
            close_target_location="por_definir",
            prefilled_values=pending_values,
        ):
            if kind == "sensores":
                _clear_sensor_picker_state(f"{kind}_{row_id}")
                st.session_state.pop(_sensor_close_pending_values_key(row_id), None)
            _clear_modal_flags()
            _clear_history_selection(contact_id, kind)
            st.rerun()
    if c2.button("Volver a editar", width="stretch"):
        st.session_state.pop(_sensor_close_pending_values_key(row_id), None)
        modal_state.open_edit_history_modal(kind, contact_id, row_id)
        st.rerun()


def _parse_ddmmyyyy(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None


def _extract_uc501_bundle(serial_value: str) -> tuple[str, str, str]:
    raw = (serial_value or "").strip()
    if not raw:
        return "", "", ""
    first = raw.split(",")[0].strip()
    if not first.lower().startswith("uc501-"):
        return "", "", ""
    first = normalize_sensor_serial_number(first)
    parts = first.split("-")
    if len(parts) == 4:
        return parts[1].strip(), parts[3].strip(), parts[2].strip()  # uc501_sn, sim_sn, probe_sn
    if len(parts) == 2:
        return parts[1].strip(), "", ""
    return "", "", ""


def _extract_ug67_bundle(serial_value: str) -> tuple[str, str]:
    """Return (ug67_sn, sim_sn) from a ug67-* serial string. Children come from inventory.

    Supports both 3-segment (ug67-{sn}-{sim}) and 2-segment (ug67-{sn}) formats.
    Returns ("", "") for sim_sn when no SIM is present.
    """
    raw = (serial_value or "").strip()
    if not raw:
        return "", ""
    first = raw.split(",")[0].strip()
    if not first.lower().startswith("ug67-"):
        return "", ""
    first = normalize_sensor_serial_number(first)
    parts = first.split("-")
    if len(parts) == 3:
        return parts[1].strip(), parts[2].strip()
    if len(parts) == 2:
        return parts[1].strip(), ""
    return "", ""


def _extract_solenoide_sn(serial_value: str) -> str:
    raw = (serial_value or "").strip()
    if not raw.lower().startswith("solenoide-"):
        return ""
    parts = raw.split("-", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def _extract_sim_sn(serial_value: str) -> str:
    raw = (serial_value or "").strip()
    if not raw.lower().startswith("sim-"):
        return ""
    parts = raw.split("-", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def _extract_em500_sn(serial_value: str) -> str:
    raw = (serial_value or "").strip()
    if not raw.lower().startswith("em500-"):
        return ""
    parts = raw.split("-", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def _find_inventory_option_by_serial(
    options: list[InventoryAssetOption],
    serial: str,
) -> InventoryAssetOption | None:
    """Match inventory rows by serial, ignoring wrapping quotes and case."""
    target = normalize_inventory_serial_for_match(serial)
    if not target:
        return None
    for opt in options:
        if normalize_inventory_serial_for_match(opt.serial_number) == target:
            return opt
    return None


def _serial_in_labels(serial: str, labels: list[str]) -> bool:
    target = normalize_inventory_serial_for_match(serial)
    if not target:
        return serial in labels
    return any(
        normalize_inventory_serial_for_match(label) == target
        for label in labels
        if label
    )


def _normalized_serial_set(options: list[InventoryAssetOption]) -> set[str]:
    return {
        normalize_inventory_serial_for_match(o.serial_number)
        for o in options
        if normalize_inventory_serial_for_match(o.serial_number)
    }


def _resolve_inventory_option(
    inv_svc,
    models: tuple[str, ...],
    serial: str,
    available_options: list[InventoryAssetOption],
    inv_df: pd.DataFrame,
) -> InventoryAssetOption | None:
    opt = _find_inventory_option_by_serial(available_options, serial)
    if opt is not None:
        return opt
    all_opts = inv_svc.asset_options_by_models(models, inv_df=inv_df)
    return _find_inventory_option_by_serial(all_opts, serial)


def _infer_sensor_root_type(serial_value: str) -> str:
    """Infer root asset type from existing sensor_serial_number."""
    first = (serial_value or "").strip().split(",")[0].strip().lower()
    if first.startswith("ug67-"):
        return "ug67"
    if first.startswith("em500-"):
        return "em500"
    if first.startswith("solenoide-"):
        return "solenoide"
    if first.startswith("sim-"):
        return "sim"
    return "uc501"


def _collect_all_serials_from_sensor_sn(sensor_serial_number: str) -> list[str]:
    """Extract every individual serial number from a canonical sensor_serial_number string."""
    serials: list[str] = []
    for item in [p.strip() for p in normalize_sensor_serial_number(sensor_serial_number).split(",") if p.strip()]:
        lower = item.lower()
        if lower.startswith("uc501-"):
            parts = item.split("-")
            if len(parts) == 4:
                serials.extend([parts[1], parts[2], parts[3]])
            elif len(parts) == 2:
                serials.append(parts[1])
        elif lower.startswith("ug67-"):
            parts = item.split("-")
            if len(parts) == 3:
                serials.extend([parts[1], parts[2]])
            elif len(parts) == 2:
                serials.append(parts[1])
        elif lower.startswith("solenoide-"):
            parts = item.split("-", 1)
            if len(parts) == 2:
                serials.append(parts[1])
        elif lower.startswith("sim-"):
            parts = item.split("-", 1)
            if len(parts) == 2:
                serials.append(parts[1])
        elif "-" in item:
            serials.append(item.split("-", 1)[1])
    return [s.strip() for s in serials if s.strip()]


def _serials_from_sensor_history_strings(sensor_serial_numbers: list[str]) -> list[str]:
    seen: set[str] = set()
    serials: list[str] = []
    for sensor_serial_number in sensor_serial_numbers:
        for serial in sensor_serials_from_sensor_serial_number(sensor_serial_number):
            key = serial.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            serials.append(serial)
    return serials


def _reconcile_inventory_locations_for_sensor_serials(
    serials: list[str],
    *,
    default_location_type: str = "por_definir",
) -> None:
    if not serials:
        return
    assignments = history_service().open_sensor_assignment_rows_for_serials(serials)
    inventory_service().reconcile_locations_for_serials(
        serials,
        assignments,
        default_location_type=default_location_type,
    )
    bump_inventory_cache()


def _sync_inventory_from_sensor_history(
    values: dict[str, str],
    *,
    close_target_location: str = "",
    previous_sensor_serial_number: str = "",
) -> None:
    serials = _serials_from_sensor_history_strings(
        [
            str(values.get("sensor_serial_number", "") or ""),
            previous_sensor_serial_number,
        ]
    )
    if not serials:
        return
    estado_cierre = str(values.get("estado_cierre_sensor", "")).strip().lower()
    if estado_cierre == "cerrado":
        target = (close_target_location or "por_definir").strip().lower()
        default_location_type = "oficina" if target == "oficina" else "por_definir"
    else:
        default_location_type = "por_definir"
    _reconcile_inventory_locations_for_sensor_serials(serials, default_location_type=default_location_type)


def _persona_proxima_accion_filter_options(df: pd.DataFrame) -> list[str]:
    opts = list(PERSONA_COMERCIAL_OPCIONES)
    if not df.empty and "persona_proxima_accion" in df.columns:
        known = set(opts)
        extra = sorted(
            {
                x
                for x in df["persona_proxima_accion"].fillna("").astype(str).str.strip().unique()
                if x and x not in known
            }
        )
        opts = opts + extra
    return [""] + opts


def _render_next_action_strip(df: pd.DataFrame) -> None:
    if "dash_bucket" not in st.session_state:
        st.session_state.dash_bucket = ""
    st.markdown("##### Próximas acciones")
    persona_opts = _persona_proxima_accion_filter_options(df)
    current_persona = str(st.session_state.get(DASH_PERSONA_PROXIMA_ACCION_KEY, "") or "")
    persona_index = persona_opts.index(current_persona) if current_persona in persona_opts else 0
    st.selectbox(
        "Persona próxima acción",
        options=persona_opts,
        index=persona_index,
        format_func=lambda v: "Todas" if not v else v,
        key=DASH_PERSONA_PROXIMA_ACCION_KEY,
    )
    persona_proxima = str(st.session_state.get(DASH_PERSONA_PROXIMA_ACCION_KEY, "") or "")
    scoped = filter_by_persona_proxima_accion(df, persona_proxima)
    dash_responsable = str(st.session_state.get(DASH_RESPONSABLE_FILTER_KEY, "") or "")
    scoped = filter_by_responsable_cliente(scoped, dash_responsable)
    dash_estado = str(st.session_state.get(DASH_ESTADO_FILTER_KEY, "") or "")
    scoped = filter_by_contact_estado(scoped, dash_estado)
    counts = next_action_bucket_counts(scoped)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    for col, key, label in (
        (c1, "past", "Fecha anterior"),
        (c2, "today", "Hoy"),
        (c3, "tomorrow", "Mañana"),
        (c4, "future", "Fecha futura"),
    ):
        active = st.session_state.dash_bucket == key
        if col.button(
            f"{label}\n{counts[key]}",
            key=f"dash_bucket_{key}",
            width="stretch",
            type="primary" if active else "secondary",
        ):
            _clear_modal_flags()
            st.session_state.dash_bucket = "" if active else key
            st.rerun()
    estado_opts = [""] + list(CONTACT_ESTADO_OPCIONES)
    current_estado = str(st.session_state.get(DASH_ESTADO_FILTER_KEY, "") or "")
    estado_index = estado_opts.index(current_estado) if current_estado in estado_opts else 0
    st.selectbox(
        "Estado",
        options=estado_opts,
        index=estado_index,
        format_func=lambda v: "Todos" if not v else v,
        key=DASH_ESTADO_FILTER_KEY,
    )
    responsable_opts = [""] + crm_user_names(load_users_cached(st.session_state.get("users_cache_version", 0)))
    current_responsable = str(st.session_state.get(DASH_RESPONSABLE_FILTER_KEY, "") or "")
    responsable_index = responsable_opts.index(current_responsable) if current_responsable in responsable_opts else 0
    st.selectbox(
        "Responsable del cliente",
        options=responsable_opts,
        index=responsable_index,
        format_func=lambda v: "Todos" if not v else v,
        key=DASH_RESPONSABLE_FILTER_KEY,
    )


def _render_contact_field_input(column: str, value: str, *, key: str) -> str:
    label = column.replace("_", " ").capitalize()
    if column in {"digital_maps", "iot_module", "sowing_module"}:
        normalized = (value or "").strip().lower()
        checked = normalized in {"true", "1", "yes", "si", "sí"}
        return "True" if st.checkbox(label, value=checked, key=key) else "False"
    if column == "estado":
        opts = [""] + list(CONTACT_ESTADO_OPCIONES)
        return st.selectbox(label, opts, index=opts.index(value) if value in opts else 0, key=key)
    if column == "fuente_lead":
        opts = [""] + list(FUENTE_LEAD_OPCIONES)
        return st.selectbox(label, opts, index=opts.index(value) if value in opts else 0, key=key)
    if column in {"persona_primer_contacto"}:
        opts = [""] + list(PERSONA_COMERCIAL_OPCIONES)
        return st.selectbox(label, opts, index=opts.index(value) if value in opts else 0, key=key)
    if column == "valor":
        opts = [""] + list(VALOR_OPCIONES)
        return st.selectbox(label, opts, index=opts.index(value) if value in opts else 0, key=key)
    if column == "tipo_relacion":
        opts = [""] + list(TIPO_RELACION_OPCIONES)
        return st.selectbox(
            "Tipo de relación",
            opts,
            index=opts.index(value) if value in opts else 0,
            key=key,
        )
    if column == "responsable_cliente":
        opts = [""] + crm_user_names(load_users_cached(st.session_state.get("users_cache_version", 0)))
        return st.selectbox(
            "Responsable del cliente",
            opts,
            index=opts.index(value) if value in opts else 0,
            key=key,
        )
    if column in {"detalle", "otros_contactos", "razon_perdida"}:
        return st.text_area(label, value=value, height=80, key=key)
    return st.text_input(label, value=value, key=key)


def _render_seguimiento_comercial_section(contact: dict[str, str], rows: list[dict[str, str]]) -> None:
    contact_id = str(contact.get("contact_id", "") or "")
    st.caption(f"{len(rows)} registro{'s' if len(rows) != 1 else ''} de seguimiento comercial")
    if st.button(
        "Nuevo seguimiento",
        type="primary",
        key=f"seg_new_followup_{contact_id}",
        width="stretch",
    ):
        modal_state.open_add_history_modal("seguimiento_comercial", contact_id)
        st.rerun()
    render_commercial_followup_list(rows, contact_id)


def _render_operative_history_cards_section(
    contact: dict[str, str],
    kind: str,
    rows: list[dict[str, str]],
) -> None:
    contact_id = str(contact.get("contact_id", "") or "")
    display_rows = rows
    if kind == "sensores":
        toggle_key = f"hist_sensors_open_only_{contact_id}"
        if toggle_key not in st.session_state:
            st.session_state[toggle_key] = True
        only_open = st.toggle("Solo abiertos", key=toggle_key)
        if only_open:
            display_rows = filter_open_sensor_history(rows)
            n_open = len(display_rows)
            n_total = len(rows)
            if n_open < n_total:
                st.caption(f"{n_open} abierto{'s' if n_open != 1 else ''} · {n_total} en total")
            else:
                st.caption(f"{n_open} abierto{'s' if n_open != 1 else ''}")
        else:
            st.caption(f"{len(rows)} registro{'s' if len(rows) != 1 else ''}")
    else:
        st.caption(f"{len(rows)} registro{'s' if len(rows) != 1 else ''}")
    if st.button(
        "Nuevo histórico",
        type="primary",
        key=f"hist_new_{kind}_{contact_id}",
        width="stretch",
    ):
        modal_state.open_add_history_modal(kind, contact_id)
        st.rerun()
    render_paginated_history_cards(kind, display_rows, contact_id)


def _render_history_kind_section(
    contact: dict[str, str],
    kind: str,
    *,
    expanded: bool | None = None,
) -> None:
    contact_id = contact.get("contact_id", "")
    spec = HISTORY_SPECS[kind]
    rows = history_service().rows_for_contact(kind, contact_id)
    expanded_default = False if expanded is None else expanded
    with st.expander(spec.title, expanded=expanded_default):
        if kind == "seguimiento_comercial":
            _render_seguimiento_comercial_section(contact, rows)
            return
        _render_operative_history_cards_section(contact, kind, rows)


def _render_histories(contact: dict[str, str]) -> None:
    for kind in (
        "seguimiento_comercial",
        "sensores",
        "campanas",
        "suscripciones",
        "incidencias",
    ):
        _render_history_kind_section(contact, kind)


def _render_history_create_form(kind: str, contact: dict[str, str]) -> None:
    spec = HISTORY_SPECS[kind]
    with st.expander(f"Añadir {spec.title.lower()}"):
        _render_history_form(kind, contact, None)


def _render_history_edit_form(kind: str, rows: list[dict[str, str]]) -> None:
    spec = HISTORY_SPECS[kind]
    ids = [row.get(spec.id_column, "") for row in rows if row.get(spec.id_column)]
    selected = st.selectbox(f"Editar registro de {spec.title.lower()}", [""] + ids, key=f"edit_{kind}_selector")
    if not selected:
        return
    row = next((item for item in rows if item.get(spec.id_column) == selected), None)
    if row:
        _render_history_form(kind, row, row)


def _render_history_form(kind: str, base: dict[str, str], existing: dict[str, str] | None) -> None:
    spec = HISTORY_SPECS[kind]
    suffix = existing.get(spec.id_column, "new") if existing else "new"
    prefix = f"{kind}_{suffix}"

    # For sensores, render the sensor picker OUTSIDE the form so that widget
    # interactions (root-type radio, asset selectbox) trigger reruns and the
    # association panel updates immediately.
    excluded: frozenset[str] = frozenset()
    if kind == "sensores":
        excluded = frozenset({"sensor_serial_number"})
        initial_ssn = (existing or {}).get("sensor_serial_number", "")
        hist_id = (existing or {}).get(spec.id_column, "")
        st.markdown("**Sensor**")
        _render_sensor_serial_field(initial_ssn, prefix, f"{prefix}_sensor_serial_number", exclude_hist_id=hist_id)

    with st.form(f"history_form_{kind}_{suffix}_{base.get('contact_id', '')}"):
        _render_history_form_body(kind, base, existing, excluded_headers=excluded)
        submitted = st.form_submit_button("Guardar histórico")
    if submitted and _submit_history_form(kind, base, existing):
        st.rerun()


_SEGUIMIENTO_CONTACTO_FIELDS = (
    "resultado_contacto",
    "fecha_contacto",
    "hora_contacto",
    "persona_contacto",
    "canal_contacto",
    "email_url",
    "email_clasificacion",
    "notas_contacto",
)
_SEGUIMIENTO_CANAL_FIELDS = frozenset({"canal_contacto", "email_url", "email_clasificacion"})
_SEGUIMIENTO_PROXIMA_FIELDS = (
    "proxima_accion_canal",
    "proxima_accion_persona",
    "proxima_accion_fecha",
    "proxima_accion_detalle",
)


def _render_seguimiento_canal_block(prefix: str, initial: dict[str, str]) -> None:
    """Canal + campos email fuera del form para que el rerun habilite email_url."""
    kind = "seguimiento_comercial"
    st.markdown("**Canal de contacto**")
    _field_for_header(kind, "canal_contacto", initial.get("canal_contacto", ""), prefix)
    canal = str(st.session_state.get(f"{prefix}_canal_contacto", "") or "").strip().lower()
    if canal == "email":
        _field_for_header(kind, "email_url", initial.get("email_url", ""), prefix)
        _field_for_header(kind, "email_clasificacion", initial.get("email_clasificacion", ""), prefix)
    elif canal:
        st.caption("URL y clasificación de email solo aplican cuando el canal es email.")
    else:
        st.caption("Selecciona un canal de contacto.")


def _seguimiento_modal_initial(kind: str, contact: dict[str, str], row: dict[str, str] | None) -> tuple[str, dict[str, str]]:
    spec = HISTORY_SPECS[kind]
    if row is None:
        prefix = f"{kind}_new"
        initial = {header: "" for header in spec.headers}
    else:
        row_id = str(row.get(spec.id_column, "") or "")
        prefix = f"{kind}_{row_id}"
        initial = {header: str(row.get(header, "") or "") for header in spec.headers}
    initial["contact_id"] = str(contact.get("contact_id", "") or "")
    initial["nombre_cliente"] = str(contact.get("nombre", contact.get("nombre_cliente", "")) or "")
    initial = _apply_smart_defaults(kind, initial, is_new=row is None)
    return prefix, initial


def _history_smart_defaults(kind: str) -> dict[str, str]:
    """Valores por defecto para un histórico NUEVO (menos clics por registro).

    Fecha del día, hora actual y persona = usuario logado (si figura entre las
    opciones comerciales). Solo se aplican sobre campos vacíos de registros
    nuevos; nunca sobre filas existentes.
    """
    today = date.today().strftime("%d/%m/%Y")
    if kind == "seguimiento_comercial":
        actor = _actor_name().strip()
        persona = actor if actor in PERSONA_COMERCIAL_OPCIONES else ""
        return {
            "fecha_contacto": today,
            "hora_contacto": datetime.now().strftime("%H:%M"),
            "persona_contacto": persona,
            "proxima_accion_persona": persona,
        }
    if kind == "sensores":
        return {"fecha_inicio": today}
    if kind == "campanas":
        return {"fecha_campana_inicio": today}
    if kind == "suscripciones":
        return {"fecha_pago": today}
    if kind == "incidencias":
        return {"fecha_apertura": today}
    return {}


def _apply_smart_defaults(kind: str, initial: dict[str, str], *, is_new: bool) -> dict[str, str]:
    if not is_new:
        return initial
    for header, default in _history_smart_defaults(kind).items():
        if not str(initial.get(header, "") or "").strip():
            initial[header] = default
    return initial


def _render_seguimiento_comercial_fields(
    kind: str,
    prefix: str,
    initial: dict[str, str],
    excluded_headers: frozenset[str],
) -> None:
    st.markdown("**Contacto realizado**")
    for header in _SEGUIMIENTO_CONTACTO_FIELDS:
        if header in excluded_headers:
            continue
        _field_for_header(kind, header, initial.get(header, ""), prefix)
    st.markdown("**Próxima acción pendiente**")
    for header in _SEGUIMIENTO_PROXIMA_FIELDS:
        if header in excluded_headers:
            continue
        _field_for_header(kind, header, initial.get(header, ""), prefix)
    if "origen_registro" not in excluded_headers:
        _field_for_header(
            kind,
            "origen_registro",
            initial.get("origen_registro", "") or "manual",
            prefix,
        )


def _render_history_form_body(
    kind: str,
    base: dict[str, str],
    existing: dict[str, str] | None,
    *,
    excluded_headers: frozenset[str] = frozenset(),
) -> None:
    spec = HISTORY_SPECS[kind]
    prefix = f"{kind}_{existing.get(spec.id_column) if existing else 'new'}"
    initial = {header: (existing or {}).get(header, "") for header in spec.headers}
    initial["contact_id"] = initial.get("contact_id") or base.get("contact_id", "")
    initial["nombre_cliente"] = initial.get("nombre_cliente") or base.get("nombre", base.get("nombre_cliente", ""))
    initial = _apply_smart_defaults(kind, initial, is_new=existing is None)
    st.markdown("**Identificación**")
    id_cols = st.columns(3)
    with id_cols[0]:
        st.text_input("Contact ID", value=initial["contact_id"], disabled=True, key=f"{prefix}_id_contact")
    with id_cols[1]:
        st.text_input("Nombre cliente", value=initial["nombre_cliente"], disabled=True, key=f"{prefix}_id_nombre")
    with id_cols[2]:
        if existing:
            st.text_input(
                spec.id_column,
                value=initial.get(spec.id_column, ""),
                disabled=True,
                key=f"{prefix}_id_historial",
            )

    if kind == "seguimiento_comercial":
        _render_seguimiento_comercial_fields(kind, prefix, initial, excluded_headers)
        return

    st.markdown("**Datos principales**")
    _always_skip = {spec.id_column, "contact_id", "nombre_cliente", "created_at", "updated_at"}
    for header in spec.headers:
        if header in _always_skip or header in excluded_headers:
            continue
        _field_for_header(kind, header, initial.get(header, ""), prefix)


def _render_history_form_grouped_body(
    kind: str,
    base: dict[str, str],
    existing: dict[str, str] | None,
    *,
    excluded_headers: frozenset[str] = frozenset(),
) -> None:
    spec = HISTORY_SPECS[kind]
    prefix = f"{kind}_{existing.get(spec.id_column) if existing else 'new'}"
    initial = {header: (existing or {}).get(header, "") for header in spec.headers}
    initial["contact_id"] = initial.get("contact_id") or base.get("contact_id", "")
    initial["nombre_cliente"] = initial.get("nombre_cliente") or base.get("nombre", base.get("nombre_cliente", ""))
    initial = _apply_smart_defaults(kind, initial, is_new=existing is None)

    st.markdown("**Identificación**")
    with st.container(border=True):
        id_cols = st.columns(3)
        with id_cols[0]:
            st.text_input("Contact ID", value=initial["contact_id"], disabled=True, key=f"{prefix}_id_contact")
        with id_cols[1]:
            st.text_input("Nombre cliente", value=initial["nombre_cliente"], disabled=True, key=f"{prefix}_id_nombre")
        with id_cols[2]:
            if existing:
                st.text_input(
                    spec.id_column,
                    value=initial.get(spec.id_column, ""),
                    disabled=True,
                    key=f"{prefix}_id_historial",
                )

    if kind == "seguimiento_comercial":
        with st.container(border=True):
            _render_seguimiento_comercial_fields(kind, prefix, initial, excluded_headers)
        return

    _always_skip = {spec.id_column, "contact_id", "nombre_cliente", "created_at", "updated_at"}
    all_fields = [
        header
        for header in spec.headers
        if header not in _always_skip and header not in excluded_headers
    ]
    first_group = all_fields[: max(1, len(all_fields) // 2)]
    second_group = all_fields[max(1, len(all_fields) // 2) :]

    st.markdown("**Bloque principal**")
    with st.container(border=True):
        for header in first_group:
            _field_for_header(kind, header, initial.get(header, ""), prefix)

    if second_group:
        st.markdown("**Bloque complementario**")
        with st.container(border=True):
            for header in second_group:
                _field_for_header(kind, header, initial.get(header, ""), prefix)


def _render_projectiotid_editor(prefix: str, raw_value: str, sensor_serial_number: str) -> str:
    """Render dynamic ProjectIoTId -> sensors mapping editor and return JSON payload."""
    state_key = f"{prefix}_projectiotid_blocks"
    source_key = f"{prefix}_projectiotid_blocks_source"
    available_tokens = sensor_association_tokens(sensor_serial_number)
    source_fingerprint = f"{sensor_serial_number}||{raw_value}"
    if state_key not in st.session_state or st.session_state.get(source_key) != source_fingerprint:
        parsed = parse_projectiotid_assignments(raw_value)
        st.session_state[state_key] = [
            {
                "uid": uuid.uuid4().hex[:8],
                "projectiotid": item.projectiotid,
                "sensors": list(item.sensors),
            }
            for item in parsed
        ]
        st.session_state[source_key] = source_fingerprint

    blocks = st.session_state.get(state_key, [])
    st.markdown("**ProjectIoTId por sensor**")
    st.caption("Asocia cada ProjectIoTId a uno o varios sensores de este histórico.")

    def _sync_blocks_from_widgets() -> None:
        for block in blocks:
            uid = str(block.get("uid", "")).strip()
            if not uid:
                continue
            pid_key = f"{prefix}_projectiotid_value_{uid}"
            sns_key = f"{prefix}_projectiotid_sensors_{uid}"
            block["projectiotid"] = str(st.session_state.get(pid_key, block.get("projectiotid", "")) or "")
            current = st.session_state.get(sns_key, block.get("sensors", []))
            block["sensors"] = [str(x).strip() for x in current if str(x).strip()]

    add_clicked = st.form_submit_button("➕ Añadir ProjectIoTId", width="stretch")
    remove_clicked = st.form_submit_button("➖ Quitar último ProjectIoTId", width="stretch")
    if add_clicked:
        _sync_blocks_from_widgets()
        blocks.append({"uid": uuid.uuid4().hex[:8], "projectiotid": "", "sensors": []})
        st.session_state[state_key] = blocks
        st.rerun()
    if remove_clicked and blocks:
        _sync_blocks_from_widgets()
        removed = blocks.pop()
        uid = str(removed.get("uid", "") or "")
        if uid:
            st.session_state.pop(f"{prefix}_projectiotid_value_{uid}", None)
            st.session_state.pop(f"{prefix}_projectiotid_sensors_{uid}", None)
        st.session_state[state_key] = blocks
        st.rerun()

    collected: list[ProjectIotAssignment] = []
    used_in_previous: set[str] = set()
    for idx, block in enumerate(blocks, start=1):
        uid = str(block.get("uid", "") or uuid.uuid4().hex[:8])
        pid_key = f"{prefix}_projectiotid_value_{uid}"
        sns_key = f"{prefix}_projectiotid_sensors_{uid}"
        if pid_key not in st.session_state:
            st.session_state[pid_key] = str(block.get("projectiotid", "") or "")
        if sns_key not in st.session_state:
            defaults = [s for s in block.get("sensors", []) if s in available_tokens]
            st.session_state[sns_key] = defaults
        current_selected = [str(x).strip() for x in st.session_state.get(sns_key, []) if str(x).strip()]
        options = [t for t in available_tokens if t.lower() not in used_in_previous or t in current_selected]
        st.text_input(f"ProjectIoTId #{idx}", key=pid_key)
        st.multiselect(
            f"Sensores asociados #{idx}",
            options=options,
            key=sns_key,
            help="Puedes dejar sensores sin asociar.",
        )
        pid_val = str(st.session_state.get(pid_key, "") or "").strip()
        sensors_val = [str(x).strip() for x in st.session_state.get(sns_key, []) if str(x).strip()]
        if pid_val:
            collected.append(ProjectIotAssignment(projectiotid=pid_val, sensors=tuple(sensors_val)))
        used_in_previous.update(s.lower() for s in sensors_val)

    used = {s.lower() for item in collected for s in item.sensors}
    unassigned = [token for token in available_tokens if token.lower() not in used]
    if unassigned:
        st.caption("Sensores sin ProjectIoTId: " + ", ".join(unassigned))
    serialized = serialize_projectiotid_assignments(collected)
    st.session_state[f"{prefix}_projectiotid"] = serialized
    return serialized


def _submit_history_form(
    kind: str,
    base: dict[str, str],
    existing: dict[str, str] | None,
    *,
    close_target_location: str = "",
    prefilled_values: dict[str, str] | None = None,
) -> bool:
    spec = HISTORY_SPECS[kind]
    prefix = f"{kind}_{existing.get(spec.id_column) if existing else 'new'}"
    previous_sensor_serial_number = ""
    if kind == "sensores" and existing:
        previous_sensor_serial_number = str(existing.get("sensor_serial_number", "") or "")
    values: dict[str, str] = {}
    values["contact_id"] = str(base.get("contact_id", ""))
    values["nombre_cliente"] = str(base.get("nombre", base.get("nombre_cliente", "")))
    if existing:
        values[spec.id_column] = str(existing.get(spec.id_column, ""))
    for header in spec.headers:
        if header in {spec.id_column, "contact_id", "nombre_cliente", "created_at", "updated_at"}:
            continue
        if prefilled_values is not None:
            values[header] = str(prefilled_values.get(header, ""))
        else:
            values[header] = str(st.session_state.get(f"{prefix}_{header}", ""))

    if kind == "incidencias":
        for header in _INCIDENCIA_ASSOC_HEADERS:
            values[header] = _resolve_incidencia_assoc_field(prefix, existing, header)

    error = _validate_history_values(kind, values, prefix=prefix)
    if error:
        st.error(error)
        return False
    if kind == "seguimiento_comercial":
        for date_col in ("fecha_contacto", "proxima_accion_fecha"):
            raw = (values.get(date_col, "") or "").strip()
            if raw:
                values[date_col] = normalize_dd_mm_yyyy(raw) or raw
    try:
        with st.spinner("Guardando y comprobando que no se solapen sensores..."):
            if kind == "sensores":
                conflicts = history_service().sensor_assignment_conflicts(
                    values,
                    ignore_historial_sensor_id=values.get(spec.id_column, ""),
                )
                if conflicts:
                    lines = [
                        f"{conflict.asset.asset_type.upper()} {conflict.asset.serial} ya está en {conflict.nombre_cliente} "
                        f"({conflict.fecha_inicio or 'sin inicio'} - {conflict.fecha_fin or 'sin fin'})."
                        for conflict in conflicts
                    ]
                    st.error("No se puede guardar porque hay solape temporal:\n\n" + "\n".join(lines))
                    return False
                values["cantidad_sensores"] = str(count_sensor_assets(values.get("sensor_serial_number", "")))
            if kind == "campanas":
                values["dias_campana"] = HistoryService._campaign_days(values)
            if existing:
                history_service().update_row(kind, values[spec.id_column], values)
            else:
                history_service().add_row(kind, values)
            if kind == "sensores":
                _sync_inventory_from_sensor_history(
                    values,
                    close_target_location=close_target_location,
                    previous_sensor_serial_number=previous_sensor_serial_number,
                )
        bump_history_cache()
        # Toast: sobrevive al rerun que cierra el diálogo (st.success no se ve).
        st.toast("Histórico guardado correctamente.", icon="✅")
        return True
    except Exception as exc:
        st.error(f"No se pudo guardar el histórico: {exc}")
        return False


def _sim_eid_from_inv_df(inv_df: pd.DataFrame, inventory_id: str) -> str:
    if inv_df.empty or not (inventory_id or "").strip():
        return ""
    iid = inventory_id.strip()
    m = inv_df[inv_df["inventory_id"].astype(str).str.strip() == iid]
    if m.empty:
        return ""
    return str(m.iloc[0].get("sim_eid_number", "") or "").strip()


def _render_sensor_serial_field(value: str, prefix: str, key: str, *, exclude_hist_id: str = "") -> str:
    """Guided picker for sensor_serial_number: UC501, UG67, Solenoide or SIM individual.

    Must be rendered OUTSIDE any st.form so that widget interactions trigger
    reruns and the association panel updates immediately.

    - Shows only *available* assets (not assigned to a client and no open
      sensor history for that serial, unless we're editing that very record).
    - Reads associations (SIM, probe, child sensors) from Inventory — the
      single source of truth — and shows them read-only below the selector.
    - Composes the canonical sensor_serial_number string automatically and
      stores it in session_state[key].
    """
    inv_df = load_inventory_cached(st.session_state.get("inventory_cache_version", 0))
    inv_svc = inventory_service()

    # ID of the record being edited (to exclude it from open-serial blocking).
    # Prefer the explicitly-passed value; fall back to session state (legacy path).
    resolved_hist_id = exclude_hist_id or str(st.session_state.get(f"{prefix}_id_historial", "") or "")
    open_serials = history_service().open_asset_serials(exclude_historial_id=resolved_hist_id)

    # ── Two-step root-type selector ──────────────────────────────────────────
    # Step 1: UC501 yes/no radio
    is_uc501_key = f"{prefix}_is_uc501"
    non_uc501_key = f"{prefix}_non_uc501_type"
    inferred_type = _infer_sensor_root_type(value)
    if is_uc501_key not in st.session_state:
        st.session_state[is_uc501_key] = (inferred_type == "uc501")
    if non_uc501_key not in st.session_state:
        st.session_state[non_uc501_key] = inferred_type if inferred_type != "uc501" else "ug67"

    is_uc501 = st.radio(
        "¿Es un UC501?",
        options=[True, False],
        format_func=lambda x: "Sí" if x else "No",
        horizontal=True,
        key=is_uc501_key,
    )

    # Step 2: if not UC501, choose between UG67, EM500, solenoide or SIM individual
    if is_uc501:
        root_type = "uc501"
    else:
        root_type = st.radio(
            "Tipo de activo",
            options=["ug67", "em500", "solenoide", "sim"],
            format_func=lambda x: {
                "ug67": "UG67 (gateway)",
                "em500": "EM500 (nodo suelto)",
                "solenoide": "Electroválvula solenoide",
                "sim": "SIM individual",
            }[x],
            horizontal=True,
            key=non_uc501_key,
        )

    compound = ""

    # ── UC501 branch ─────────────────────────────────────────────────────────
    if root_type == "uc501":
        existing_uc, _, _ = _extract_uc501_bundle(value)
        uc_sn_key = f"{prefix}_sensor_uc501_sn"

        options_uc501 = inv_svc.available_root_assets_for_history(("uc501",), open_serials=open_serials, inv_df=inv_df)
        # Always include the currently-selected serial even if it's technically in open_serials
        # (happens when editing a record that has this UC501 open for another contact)
        selected_sn = str(st.session_state.get(uc_sn_key, existing_uc) or "")
        uc_labels = [""]
        uc_serials_set = _normalized_serial_set(options_uc501)
        for o in options_uc501:
            uc_labels.append(o.serial_number)
        if selected_sn and normalize_inventory_serial_for_match(selected_sn) not in uc_serials_set:
            uc_labels.append(selected_sn)  # keep editing selection visible

        if not options_uc501 and not selected_sn:
            st.info("Aún no hay ningún UC501 disponible en inventario.")
        else:
            if uc_sn_key not in st.session_state:
                st.session_state[uc_sn_key] = selected_sn if _serial_in_labels(selected_sn, uc_labels) else (uc_labels[0] if uc_labels else "")
            uc_sn = st.selectbox("UC501 disponibles (SN)", options=uc_labels, key=uc_sn_key)
            if uc_sn:
                opt = _resolve_inventory_option(
                    inv_svc, ("uc501",), uc_sn, options_uc501, inv_df
                )
                if opt:
                    assoc = inv_svc.associations_for_root_asset(opt.inventory_id, inv_df=inv_df)
                    with st.container(border=True):
                        st.caption("**Asociaciones desde Inventario (solo lectura)**")
                        if assoc.probe:
                            st.caption(f"🌱 Sonda: **{assoc.probe.serial_number}** ({assoc.probe.model})")
                        else:
                            st.warning("Sin sonda asociada en inventario. Ve a Inventario para vincularla.")
                        if assoc.sim:
                            eid = _sim_eid_from_inv_df(inv_df, assoc.sim.inventory_id)
                            if eid:
                                st.caption(f"📶 SIM: **{assoc.sim.serial_number}** · EID: **{eid}**")
                            else:
                                st.caption(f"📶 SIM: **{assoc.sim.serial_number}**")
                        else:
                            st.warning("Sin SIM asociada en inventario. Ve a Inventario para vincularla.")
                    probe_sn = assoc.probe.serial_number if assoc.probe else ""
                    sim_sn = assoc.sim.serial_number if assoc.sim else ""
                    if probe_sn and sim_sn:
                        compound = f"uc501-{uc_sn}-{probe_sn}-{sim_sn}"
                    elif not probe_sn and not sim_sn:
                        compound = f"uc501-{uc_sn}"
                        st.warning(
                            f"El UC501 **{uc_sn}** no tiene sonda (Teros 10/12) ni SIM configurada "
                            "en Inventario. Puedes guardar el histórico solo con el serial del UC501; "
                            "vincula componentes en Inventario cuando los tengas."
                        )
                    else:
                        compound = f"uc501-{uc_sn}"
                        _missing = []
                        if not probe_sn:
                            _missing.append("sonda (Teros 10/12)")
                        if not sim_sn:
                            _missing.append("SIM")
                        st.warning(
                            f"El UC501 **{uc_sn}** no tiene **{' ni '.join(_missing)}** configurada en Inventario. "
                            "Puedes guardar el histórico solo con el serial del UC501; "
                            "vincula los componentes en Inventario cuando los tengas."
                        )

    # ── UG67 branch ──────────────────────────────────────────────────────────
    elif root_type == "ug67":
        existing_ug, _ = _extract_ug67_bundle(value)
        ug_sn_key = f"{prefix}_sensor_ug67_sn"

        options_ug67 = inv_svc.available_root_assets_for_history(("ug67",), open_serials=open_serials, inv_df=inv_df)
        selected_sn = str(st.session_state.get(ug_sn_key, existing_ug) or "")
        ug_labels = [""]
        ug_serials_set = _normalized_serial_set(options_ug67)
        for o in options_ug67:
            ug_labels.append(o.serial_number)
        if selected_sn and normalize_inventory_serial_for_match(selected_sn) not in ug_serials_set:
            ug_labels.append(selected_sn)

        if not options_ug67 and not selected_sn:
            st.info("Aún no hay ningún UG67 disponible en inventario.")
        else:
            if ug_sn_key not in st.session_state:
                st.session_state[ug_sn_key] = selected_sn if _serial_in_labels(selected_sn, ug_labels) else (ug_labels[0] if ug_labels else "")
            ug_sn = st.selectbox("UG67 disponibles (SN)", options=ug_labels, key=ug_sn_key)
            if ug_sn:
                opt = _resolve_inventory_option(
                    inv_svc, ("ug67",), ug_sn, options_ug67, inv_df
                )
                if opt:
                    assoc = inv_svc.associations_for_root_asset(opt.inventory_id, inv_df=inv_df)
                    with st.container(border=True):
                        st.caption("**Asociaciones desde Inventario (solo lectura)**")
                        if assoc.sim:
                            eid = _sim_eid_from_inv_df(inv_df, assoc.sim.inventory_id)
                            if eid:
                                st.caption(f"📶 SIM: **{assoc.sim.serial_number}** · EID: **{eid}**")
                            else:
                                st.caption(f"📶 SIM: **{assoc.sim.serial_number}**")
                        else:
                            st.warning("Sin SIM asociada en inventario. Ve a Inventario para vincularla.")
                        if assoc.sensors:
                            for child in assoc.sensors:
                                st.caption(f"📊 {child.model.upper()}: **{child.serial_number}**")
                        else:
                            st.caption("Sin sensores hijos asociados.")
                    sim_sn = assoc.sim.serial_number if assoc.sim else ""
                    if sim_sn:
                        gateway_part = f"ug67-{ug_sn}-{sim_sn}"
                    else:
                        gateway_part = f"ug67-{ug_sn}"
                        st.warning(
                            f"El UG67 **{ug_sn}** no tiene SIM en Inventario — se guardará sin SIM. "
                            "Puedes vincularla más tarde editando ese activo en Inventario."
                        )
                    sensor_parts = [
                        f"{c.model.lower()}-{c.serial_number}"
                        for c in assoc.sensors
                    ]
                    compound = ",".join([gateway_part] + sensor_parts)

    # ── EM500 standalone branch ─────────────────────────────────────────────
    elif root_type == "em500":
        existing_em500 = _extract_em500_sn(value)
        em500_sn_key = f"{prefix}_sensor_em500_sn"

        options_em500 = inv_svc.available_root_assets_for_history(("em500",), open_serials=open_serials, inv_df=inv_df)
        selected_sn = str(st.session_state.get(em500_sn_key, existing_em500) or "")
        em500_labels = [""]
        em500_serials_set = _normalized_serial_set(options_em500)
        for o in options_em500:
            em500_labels.append(o.serial_number)
        if selected_sn and normalize_inventory_serial_for_match(selected_sn) not in em500_serials_set:
            em500_labels.append(selected_sn)

        if not options_em500 and not selected_sn:
            st.info("Aún no hay ningún EM500 disponible en inventario.")
        else:
            if em500_sn_key not in st.session_state:
                st.session_state[em500_sn_key] = selected_sn if _serial_in_labels(selected_sn, em500_labels) else (em500_labels[0] if em500_labels else "")
            em500_sn = st.selectbox("EM500 disponibles (SN)", options=em500_labels, key=em500_sn_key)
            if em500_sn:
                compound = f"em500-{em500_sn}"

    # ── Solenoide branch ─────────────────────────────────────────────────────
    elif root_type == "solenoide":
        existing_sol = _extract_solenoide_sn(value)
        sol_sn_key = f"{prefix}_sensor_solenoide_sn"

        options_sol = inv_svc.available_root_assets_for_history(("solenoide",), open_serials=open_serials, inv_df=inv_df)
        selected_sn = str(st.session_state.get(sol_sn_key, existing_sol) or "")
        sol_labels = [""]
        sol_serials_set = _normalized_serial_set(options_sol)
        for o in options_sol:
            sol_labels.append(o.serial_number)
        if selected_sn and normalize_inventory_serial_for_match(selected_sn) not in sol_serials_set:
            sol_labels.append(selected_sn)

        if not options_sol and not selected_sn:
            st.info("Aún no hay ninguna electroválvula solenoide disponible en inventario.")
        else:
            if sol_sn_key not in st.session_state:
                st.session_state[sol_sn_key] = selected_sn if _serial_in_labels(selected_sn, sol_labels) else (sol_labels[0] if sol_labels else "")
            sol_sn = st.selectbox("Solenoide disponibles (SN)", options=sol_labels, key=sol_sn_key)
            if sol_sn:
                compound = f"solenoide-{sol_sn}"

    # ── SIM individual branch ────────────────────────────────────────────────
    elif root_type == "sim":
        existing_sim = _extract_sim_sn(value)
        sim_sn_key = f"{prefix}_sensor_sim_sn"

        options_sim = inv_svc.available_root_assets_for_history(("sim",), open_serials=open_serials, inv_df=inv_df)
        selected_sn = str(st.session_state.get(sim_sn_key, existing_sim) or "")
        sim_labels = [""]
        sim_serials_set = _normalized_serial_set(options_sim)
        for o in options_sim:
            sim_labels.append(o.serial_number)
        if selected_sn and normalize_inventory_serial_for_match(selected_sn) not in sim_serials_set:
            sim_labels.append(selected_sn)

        if not options_sim and not selected_sn:
            st.info("Aún no hay ninguna SIM disponible en inventario.")
        else:
            if sim_sn_key not in st.session_state:
                st.session_state[sim_sn_key] = selected_sn if _serial_in_labels(selected_sn, sim_labels) else (sim_labels[0] if sim_labels else "")
            sim_sn = st.selectbox("SIM disponibles (SN)", options=sim_labels, key=sim_sn_key)
            if sim_sn:
                opt = _resolve_inventory_option(
                    inv_svc, ("sim",), sim_sn, options_sim, inv_df
                )
                with st.container(border=True):
                    st.caption("**SIM seleccionada**")
                    eid = _sim_eid_from_inv_df(inv_df, opt.inventory_id) if opt else ""
                    if eid:
                        st.caption(f"📶 SN: **{sim_sn}** · EID: **{eid}**")
                    else:
                        st.caption(f"📶 SN: **{sim_sn}**")
                compound = f"sim-{sim_sn}"

    if compound:
        compound = normalize_sensor_serial_number(compound)
    st.session_state[key] = compound
    return compound


def _field_for_header(kind: str, header: str, value: str, prefix: str) -> str:
    label = "ProjectIoTId" if header == "projectiotid" else header.replace("_", " ").capitalize()
    key = f"{prefix}_{header}"
    if kind == "sensores" and header == "projectiotid":
        sensor_serial = str(st.session_state.get(f"{prefix}_sensor_serial_number", ""))
        return _render_projectiotid_editor(prefix, value, sensor_serial)
    if kind == "campanas" and header == "historial_sensor_id":
        contact_id = str(st.session_state.get(f"{prefix}_id_contact", "") or "")
        sensor_rows = history_service().rows_for_contact("sensores", contact_id) if contact_id else []
        options = [""] + [str(row.get("historial_sensor_id", "")).strip() for row in sensor_rows if str(row.get("historial_sensor_id", "")).strip()]
        unique_options = []
        seen: set[str] = set()
        for opt in options:
            if opt in seen:
                continue
            seen.add(opt)
            unique_options.append(opt)
        index = unique_options.index(value) if value in unique_options else 0
        return st.selectbox(label, unique_options, index=index, key=key)
    if header == "sensor_serial_number":
        return _render_sensor_serial_field(value, prefix, key)
    if header == "cantidad_sensores":
        return st.text_input(label, value=str(count_sensor_assets(st.session_state.get(f"{prefix}_sensor_serial_number", value))), key=key, disabled=True)
    if kind == "campanas" and header == "dias_campana":
        computed = HistoryService._campaign_days(
            {
                "fecha_campana_inicio": str(st.session_state.get(f"{prefix}_fecha_campana_inicio", "")),
                "fecha_campana_fin": str(st.session_state.get(f"{prefix}_fecha_campana_fin", "")),
            }
        )
        display = computed if computed else value
        st.caption("Se calcula automáticamente: fecha fin campaña − fecha inicio campaña.")
        return st.text_input("Días campaña", value=display, key=key, disabled=True)
    if header in SELECT_OPTIONS:
        options = [""] + SELECT_OPTIONS[header]
        selected_value = value
        if header in {"estado_cierre_sensor", "estado_cierre_campana"} and not (value or "").strip():
            selected_value = "abierto"
        if kind == "incidencias" and header == "estado" and not (value or "").strip():
            selected_value = "abierta"
        index = options.index(selected_value) if selected_value in options else 0
        return st.selectbox(label, options, index=index, key=key)
    if header == "red_otro":
        red_value = st.session_state.get(f"{prefix}_red", "")
        return st.text_input(label, value=value, key=key, disabled=red_value != "otro")
    if header in {"detalles", "detalle", "resolucion"}:
        return st.text_area(label, value=value, key=key, height=90)
    if kind == "seguimiento_comercial":
        if header == "hora_contacto":
            return st.text_input(label, value=value, key=key, placeholder="14:30")
        if header == "email_url":
            return st.text_input(label, value=value, key=key)
        if header in {"notas_contacto", "proxima_accion_detalle"}:
            return st.text_area(label, value=value, key=key, height=120)
        if header == "origen_registro":
            return st.text_input(label, value=value or "manual", key=key, disabled=True)
    if header in {col for _, col in DATE_COLUMNS_BY_KIND.get(kind, [])}:
        return st.text_input(label, value=value, key=key, placeholder="DD/MM/AAAA")
    return st.text_input(label, value=value, key=key)


def _validate_history_values(kind: str, values: dict[str, str], prefix: str = "") -> str | None:
    dates = [(label, values.get(column, "")) for label, column in DATE_COLUMNS_BY_KIND.get(kind, [])]
    date_error = validate_dd_mm_yyyy_fields(dates)
    if date_error:
        return date_error
    if kind == "sensores":
        ssn = values.get("sensor_serial_number", "").strip()
        if not ssn:
            # Try to give a context-aware error based on what was selected
            if prefix:
                is_uc501 = st.session_state.get(f"{prefix}_is_uc501")
                uc_sn = str(st.session_state.get(f"{prefix}_sensor_uc501_sn", "") or "").strip()
                ug67_sn = str(st.session_state.get(f"{prefix}_sensor_ug67_sn", "") or "").strip()
                em500_sn = str(st.session_state.get(f"{prefix}_sensor_em500_sn", "") or "").strip()
                if is_uc501 is True and uc_sn:
                    return (
                        f"El UC501 **{uc_sn}** no tiene sonda y/o SIM configuradas en Inventario. "
                        "Ve a Inventario, edita ese UC501 y vincula los componentes antes de guardar."
                    )
                if is_uc501 is False and st.session_state.get(f"{prefix}_non_uc501_type") == "em500" and em500_sn:
                    return (
                        f"No se pudo generar el sensor_serial_number para el EM500 **{em500_sn}**. "
                        "Vuelve a seleccionarlo en el formulario antes de guardar."
                    )
                if is_uc501 is False and ug67_sn:
                    inv_df = load_inventory_cached(st.session_state.get("inventory_cache_version", 0))
                    inv_svc = inventory_service()
                    ug_opt = _resolve_inventory_option(
                        inv_svc,
                        ("ug67",),
                        ug67_sn,
                        inv_svc.available_root_assets_for_history(("ug67",), inv_df=inv_df),
                        inv_df,
                    )
                    if ug_opt is None:
                        return (
                            f"No se encontró el UG67 **{ug67_sn}** en Inventario "
                            "(revisa que el serial en la hoja coincida, con o sin comillas)."
                        )
                    assoc = inv_svc.associations_for_root_asset(ug_opt.inventory_id, inv_df=inv_df)
                    if not assoc.sim:
                        return (
                            f"El UG67 **{ug67_sn}** no tiene SIM configurada en Inventario. "
                            "Ve a Inventario, edita ese UG67 y vincula la SIM antes de guardar."
                        )
                    return (
                        f"No se pudo generar el sensor_serial_number para el UG67 **{ug67_sn}**. "
                        "Vuelve a seleccionarlo en el formulario antes de guardar."
                    )
            return "Debes seleccionar un activo (UC501, UG67, EM500, Electroválvula solenoide o SIM individual) antes de guardar."
        if not is_valid_sensor_serial_number(ssn):
            return "El sensor_serial_number no tiene un formato válido.\n\n" + SENSOR_SERIAL_NUMBER_FORMAT_HELP
        if values.get("red") == "otro" and not values.get("red_otro", "").strip():
            return "Si red = otro, debes completar el campo red_otro."
        assignments = parse_projectiotid_assignments(values.get("projectiotid", ""))
        projectiot_error = validate_projectiotid_assignments(
            assignments,
            sensor_association_tokens(values.get("sensor_serial_number", "")),
        )
        if projectiot_error:
            return projectiot_error
    if kind == "campanas":
        start = values.get("fecha_campana_inicio", "")
        end = values.get("fecha_campana_fin", "")
        if start and end and is_valid_dd_mm_yyyy(start) and is_valid_dd_mm_yyyy(end):
            pass
    if kind == "seguimiento_comercial":
        commercial_error = validate_commercial_action_values(values)
        if commercial_error:
            return commercial_error
    return None
