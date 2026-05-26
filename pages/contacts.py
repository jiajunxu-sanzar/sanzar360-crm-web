from __future__ import annotations

import html
import uuid
from difflib import SequenceMatcher
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from app import auth
from app.navigation import page_menu_title
from app.cache import clear_all_cache, history_service, inventory_service, load_inventory_cached, load_users_cached, sheets_service
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
from config.settings import (
    CANONICAL_COLUMNS,
    CONTACT_ESTADO_OPCIONES,
    FUENTE_LEAD_OPCIONES,
    PERSONA_COMERCIAL_OPCIONES,
    SEGUIMIENTO_COMERCIAL_FIELDS,
    VALOR_OPCIONES,
)
from services.activity_log import append_activity
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
from services.contact_use_cases import create_empty_contact, save_contact_by_id
from services.sheet_date_format import (
    SENSOR_SERIAL_NUMBER_FORMAT_HELP,
    is_valid_dd_mm_yyyy,
    is_valid_sensor_serial_number,
    normalize_sensor_serial_number,
    validate_contact_date_fields,
    validate_dd_mm_yyyy_fields,
)
from ui.components.cards import card, chip
from ui.components.customer_timeline import render_contact_timeline_block
from ui.components.contact_detail_header import render_contact_detail_header
from ui import modal_state
from ui.components.history import (
    clear_history_table_selection,
    render_history_summary,
    render_history_table,
)
from ui.components.tables import filter_dataframe
from ui.palette import (
    STATUS_INFO,
    STATUS_DANGER,
    STATUS_NEUTRAL,
    incident_status_style,
    subscription_status_style,
)

DATE_COLUMNS_BY_KIND = {
    "sensores": [("Fecha inicio", "fecha_inicio"), ("Fecha fin", "fecha_fin"), ("Última revisión", "ultima_revision")],
    "campanas": [("Fecha inicio campaña", "fecha_campana_inicio"), ("Fecha fin campaña", "fecha_campana_fin")],
    "suscripciones": [
        ("Fecha pago", "fecha_pago"),
        ("Inicio suscripción", "suscripcion_fecha_inicio"),
        ("Fin suscripción", "suscripcion_fecha_fin"),
    ],
    "incidencias": [("Fecha apertura", "fecha_apertura"), ("Fecha cierre", "fecha_cierre")],
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
}

CONTACT_LIST_PANEL_HEIGHT_BASE = 980
CONTACT_LIST_PANEL_HEIGHT_WITH_DETAIL = 1320
NEW_CONTACT_FLOW_KEY = "new_contact_flow_state"
NEW_CONTACT_FLOW_IDLE = "idle"
NEW_CONTACT_FLOW_OPEN = "open"
NEW_CONTACT_FLOW_SUBMITTING = "submitting"
NEW_CONTACT_SIMILAR_CANDIDATES_KEY = "new_contact_similar_candidates"
NEW_CONTACT_REQUIRE_SECOND_CONFIRM_KEY = "new_contact_require_second_confirm"
NEW_CONTACT_CONFIRM_OVERRIDE_KEY = "new_contact_confirmed_override"
CONTACTS_SHOW_LOST_KEY = "contacts.show_lost"
CONTACTS_SAVE_SUCCESS_KEY = "contacts.save_success_message"
CONTACTS_DELETE_SUCCESS_KEY = "contacts.delete_success_message"
CONTACTS_DELETE_TARGET_ID_KEY = "contacts.delete_target_id"
CONTACTS_DELETE_TARGET_NAME_KEY = "contacts.delete_target_name"
HISTORY_DELETE_CONFIRM_PREFIX = "history_delete_confirm"


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


def _on_dismiss_history_edit() -> None:
    m = modal_state.get_active_modal()
    if m and m.get("type") == "edit_history":
        kind = m["kind"]
        contact_id = m["contact_id"]
        if kind == "sensores":
            row_id = str(m["row_id"])
            _clear_sensor_picker_state(f"{kind}_{row_id}")
            st.session_state.pop(_history_delete_confirm_key(kind, row_id), None)
        modal_state.close_modal()
        _clear_history_selection(contact_id, kind)


def _on_dismiss_history_add() -> None:
    m = modal_state.get_active_modal()
    if m and m.get("type") == "add_history":
        if m.get("kind") == "sensores":
            _clear_sensor_picker_state("sensores_new")
        modal_state.close_modal()


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

        st.title(page_menu_title("Contactos"))
        if st.session_state.get(CONTACTS_SAVE_SUCCESS_KEY):
            st.success(str(st.session_state.pop(CONTACTS_SAVE_SUCCESS_KEY)))
        if st.session_state.get(CONTACTS_DELETE_SUCCESS_KEY):
            st.success(str(st.session_state.pop(CONTACTS_DELETE_SUCCESS_KEY)))
        if df.empty:
            st.warning("No hay contactos cargados. Puedes crear el primero desde el formulario inferior.")

        left, right = st.columns([0.38, 0.62], gap="large")
        with left:
            selected_id = _render_contact_list(df)
        with right:
            if selected_id:
                df = _render_contact_detail(df, selected_id)
            else:
                st.info("Selecciona un contacto para abrir la ficha.")
        return df


def _render_contact_list(df: pd.DataFrame) -> str:
    _render_next_action_strip(df)
    if "contact_search_open" not in st.session_state:
        st.session_state.contact_search_open = False
    if "contact_filters_open" not in st.session_state:
        st.session_state.contact_filters_open = False
    if CONTACTS_SHOW_LOST_KEY not in st.session_state:
        # Soft migration from legacy filter key if present.
        st.session_state[CONTACTS_SHOW_LOST_KEY] = bool(st.session_state.get("contact_filter_show_lost", False))

    st.subheader("Buscar")
    st.toggle("Mostrar perdidos", key=CONTACTS_SHOW_LOST_KEY)
    top_row = st.columns([0.16, 0.84], gap="small")
    if top_row[0].button("🔍", key="contact_toggle_search", width="stretch"):
        st.session_state.contact_search_open = not st.session_state.contact_search_open
        if not st.session_state.contact_search_open:
            st.session_state.contact_filter_text = ""
            st.session_state.contact_filters_open = False
        st.rerun()

    query = ""
    if st.session_state.contact_search_open:
        search_row = top_row[1].columns([0.86, 0.14], gap="small")
        query = search_row[0].text_input(
            "Buscar",
            key="contact_filter_text",
            label_visibility="collapsed",
            placeholder="Nombre, municipio, provincia, correo, teléfono, cultivo o contact_id",
        )
        if search_row[1].button("⏬", key="contact_toggle_filters", width="stretch", help="Filtros"):
            st.session_state.contact_filters_open = not st.session_state.contact_filters_open
            st.rerun()

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
        filtered = filtered[filtered["estado"].astype(str).str.lower() != "perdido"]
    dash_bucket = st.session_state.get("dash_bucket", "")
    if dash_bucket:
        today = pd.Timestamp(date.today())
        next_actions = pd.to_datetime(
            filtered["proxima_accion_fecha"].fillna("").astype(str),
            format="%d/%m/%Y",
            errors="coerce",
        )
        if dash_bucket == "past":
            filtered = filtered[next_actions < today]
        elif dash_bucket == "today":
            filtered = filtered[next_actions == today]
        elif dash_bucket == "tomorrow":
            filtered = filtered[next_actions == (today + pd.Timedelta(days=1))]
    filtered = filtered.reset_index(drop=True)

    if st.button("Nuevo contacto", key="create_contact_top", width="stretch"):
        _new_contact_flow_open()
        st.rerun()
    if _new_contact_flow_state_get() in {NEW_CONTACT_FLOW_OPEN, NEW_CONTACT_FLOW_SUBMITTING}:
        _render_create_contact_confirmation(df)

    st.caption(f"{len(filtered)} contactos encontrados")
    st.caption("Haz click en una fila para abrir la ficha automáticamente.")
    current = st.session_state.get("selected_contact_id", "")
    selected_from_table = _render_contact_table(filtered, current)
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


def _render_contact_table(filtered: pd.DataFrame, selected_contact_id: str) -> str:
    if filtered.empty:
        st.info("No hay datos para mostrar.")
        return ""

    panel_height = (
        CONTACT_LIST_PANEL_HEIGHT_WITH_DETAIL
        if (selected_contact_id or "").strip()
        else CONTACT_LIST_PANEL_HEIGHT_BASE
    )
    with st.container(height=panel_height, border=True):
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
            is_lost = str(row.get("estado", "")).strip().lower() == "perdido"
            row_label = " | ".join(
                [
                    row.get("nombre", "") or "Sin nombre",
                    row.get("estado", "") or "Sin estado",
                    row.get("provincia", "") or "Sin provincia",
                    row.get("municipio", "") or "Sin municipio",
                ]
            )
            if is_lost:
                row_label = f"🔴 {row_label}"
            if contact_id == selected_contact_id:
                row_class = "sanzar-contact-row selected sanzar-contact-row-lost" if is_lost else "sanzar-contact-row selected"
                st.markdown(
                    f"<div class='{row_class}'>"
                    f"<span class='sanzar-contact-cell'>{html.escape(row.get('nombre', ''))}</span>"
                    f"<span class='sanzar-contact-cell'>{html.escape(row.get('estado', ''))}</span>"
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
                append_activity(
                    sheets_service(),
                    contact_id=new_contact_id,
                    nombre_contacto=nombre_crear,
                    tipo_accion="creacion nuevo contacto",
                    detalle="",
                    persona=_actor_name(),
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
    """Diff old vs new values and log 'seguimiento comercial' and/or
    'modificacion contacto' actions for whichever field groups changed."""
    contact_id = str(original.get("contact_id", ""))
    nombre_contacto = str(values.get("nombre") or original.get("nombre", ""))
    sheets = sheets_service()

    seg_changed: list[str] = []
    other_changed: list[str] = []
    skip = {"contact_id"}

    for key, new_val in values.items():
        if key in skip:
            continue
        old_val = str(original.get(key, "")).strip()
        if str(new_val).strip() != old_val:
            if key in SEGUIMIENTO_COMERCIAL_FIELDS:
                seg_changed.append(key)
            else:
                other_changed.append(key)

    if seg_changed:
        append_activity(
            sheets,
            contact_id=contact_id,
            nombre_contacto=nombre_contacto,
            tipo_accion="seguimiento comercial",
            detalle=", ".join(seg_changed),
            persona=actor,
        )
    if other_changed:
        append_activity(
            sheets,
            contact_id=contact_id,
            nombre_contacto=nombre_contacto,
            tipo_accion="modificacion contacto",
            detalle=", ".join(other_changed),
            persona=actor,
        )


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
    render_contact_detail_header(
        contact=contact,
        contact_id=contact_id,
        subscription_status=subscription_status,
        open_incidents=open_incidents,
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
        _render_operativa_cards(contact)
    return updated if updated is not None else df


def _render_contact_form(df: pd.DataFrame, row_idx: int, contact: dict[str, str]) -> pd.DataFrame | None:
    st.subheader("Ficha del cliente")
    sections_left: list[tuple[str, list[str]]] = [
        ("Identificación", ["nombre", "tipo_entidad", "detalle"]),
        ("Localización", ["país", "provincia", "municipio", "coordenadas", "direccion"]),
        ("Contacto", ["telefono", "correo", "otros_contactos"]),
        ("Perfil agrícola y lead", ["cultivos", "superficie_ha", "tipo_riego"]),
    ]
    sections_right: list[tuple[str, list[str]]] = [
        (
            "Seguimiento comercial",
            [
                "fuente_lead",
                "lead_detalle",
                "fecha_primer_contacto",
                "persona_primer_contacto",
                "fecha_ultimo_contacto",
                "persona_ultimo_contacto",
                "proxima_accion_fecha",
                "persona_proxima_accion",
                "proxima_accion_detalle",
                "fecha_veces_sin_respuesta",
            ],
        ),
        ("Estado y oportunidad", ["estado", "fecha_estado", "razon_perdida", "valor"]),
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
            help="Borra la ficha, históricos (sensores, campañas, suscripciones, incidencias) y Acciones.",
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


def _handle_history_table_secondary_open(
    kind: str,
    rows: list[dict[str, str]],
    contact: dict[str, str],
    selected_pos: int | None,
) -> None:
    """Segunda acción explícita: editar la fila actualmente destacada en la tabla."""
    if selected_pos is None or selected_pos < 0:
        return
    if selected_pos >= len(rows):
        return
    spec = HISTORY_SPECS[kind]
    contact_id = contact.get("contact_id", "")
    row_id = str(rows[selected_pos].get(spec.id_column, "")).strip()
    if not row_id:
        return
    suffix = f"{contact_id}_{kind}"
    if st.button(
        "Editar fila seleccionada",
        key=f"hist_edit_selected_{suffix}",
        width="stretch",
        type="primary",
    ):
        modal_state.open_edit_history_modal(kind, contact_id, row_id)
        st.rerun()


def _render_operativa_cards(contact: dict[str, str]) -> None:
    hs = history_service()
    contact_id = contact.get("contact_id", "")
    st.markdown("##### Sensores / Campañas / Suscripciones / Incidencias")
    for kind in ("sensores", "campanas", "suscripciones", "incidencias"):
        rows = hs.rows_for_contact(kind, contact_id)
        spec = HISTORY_SPECS[kind]
        latest = rows[0] if rows else {}
        summary_parts = [
            f"{column}: {latest.get(column, '—')}"
            for column in spec.summary_columns[:2]
        ]
        style = STATUS_NEUTRAL
        if kind == "suscripciones":
            style = subscription_status_style(hs.subscription_status_for_contact(contact_id))
        if kind == "incidencias":
            style = incident_status_style(hs.has_open_incidents(contact_id))
        card(
            spec.title,
            (
                chip(f"{len(rows)} registros", STATUS_INFO)
                + "<br>"
                + "<br>".join(summary_parts if summary_parts else ["Sin registros todavía."])
            ),
            style=style,
        )
        c1, c2 = st.columns([0.6, 0.4], gap="small")
        if c1.button("Historial", key=f"inline_history_{kind}_{contact_id}", width="stretch"):
            _clear_contact_overlay_state(keep_contact_id=contact_id)
            _clear_history_selection(contact_id, kind)
            st.session_state[f"show_history_{kind}_{contact_id}"] = not st.session_state.get(
                f"show_history_{kind}_{contact_id}", False
            )
            st.rerun()
        if c2.button(
            "Nuevo histórico",
            key=f"inline_add_{kind}_{contact_id}",
            width="stretch",
        ):
            _clear_contact_overlay_state(keep_contact_id=contact_id)
            modal_state.open_add_history_modal(kind, contact_id)
            st.rerun()

        if st.session_state.get(f"show_history_{kind}_{contact_id}", False):
            selected_pos = render_history_table(
                kind,
                rows,
                technical=False,
                contact_id=contact_id,
            )
            _handle_history_table_secondary_open(kind, rows, contact, selected_pos)

    _maybe_render_add_history_modal(contact)
    _maybe_render_edit_history_modal(contact)


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


@st.dialog("Nuevo histórico", on_dismiss=_on_dismiss_history_add)
def _add_history_dialog(kind: str, contact: dict[str, str]) -> None:
    spec = HISTORY_SPECS[kind]
    st.markdown(f"### {spec.title}")
    st.caption("Completa los campos y confirma para crear el nuevo registro.")

    # For sensores, render the sensor picker OUTSIDE the form — the dialog
    # supports reruns from non-form widgets, so the association panel updates
    # immediately when the user selects an asset.
    excluded: frozenset[str] = frozenset()
    if kind == "sensores":
        excluded = frozenset({"sensor_serial_number"})
        prefix = f"{kind}_new"
        st.markdown("**Sensor**")
        _render_sensor_serial_field("", prefix, f"{prefix}_sensor_serial_number", exclude_hist_id="")

    with st.form(f"history_add_modal_{kind}_{contact.get('contact_id', '')}"):
        _render_history_form_body(kind, contact, None, excluded_headers=excluded)
        action_cols = st.columns(2)
        confirm = action_cols[0].form_submit_button("Confirmar", width="stretch")
        cancel = action_cols[1].form_submit_button("Cancelar", width="stretch")

    if cancel:
        _clear_modal_flags()
        if kind == "sensores":
            _clear_sensor_picker_state("sensores_new")
        st.rerun()

    if confirm:
        if _submit_history_form(kind, contact, None):
            _clear_modal_flags()
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
        was_open = str(row.get("estado_cierre_sensor", "")).strip().lower() == "abierto"
        now_closed = str(st.session_state.get(f"{kind}_{row.get(spec.id_column, '')}_estado_cierre_sensor", "")).strip().lower() == "cerrado"
        if kind == "sensores" and was_open and now_closed:
            _sensor_close_location_dialog(kind, contact, row)
            return
        if _submit_history_form(kind, contact, row):
            _clear_modal_flags()
            _clear_history_selection(contact_id, kind)
            st.rerun()


@st.dialog("Ubicación al cerrar histórico sensor")
def _sensor_close_location_dialog(kind: str, contact: dict[str, str], row: dict[str, str]) -> None:
    st.markdown("¿Dónde quieres indicar que está este sensor?")
    choice = st.radio(
        "Destino",
        ("oficina", "por definir"),
        horizontal=True,
        key=f"sensor_close_target_{row.get('historial_sensor_id', '')}",
    )
    c1, c2 = st.columns(2)
    if c1.button("Guardar cierre", type="primary", width="stretch"):
        if _submit_history_form(kind, contact, row, close_target_location=choice):
            _clear_modal_flags()
            _clear_history_selection(str(contact.get("contact_id", "")), kind)
            st.rerun()
    if c2.button("Cancelar", width="stretch"):
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
    parts = first.split("-")
    if len(parts) != 4:
        return "", "", ""
    return parts[1].strip(), parts[3].strip(), parts[2].strip()  # uc501_sn, sim_sn, probe_sn


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


def _infer_sensor_root_type(serial_value: str) -> str:
    """Infer root asset type from existing sensor_serial_number."""
    first = (serial_value or "").strip().split(",")[0].strip().lower()
    if first.startswith("ug67-"):
        return "ug67"
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


def _render_next_action_strip(df: pd.DataFrame) -> None:
    if "dash_bucket" not in st.session_state:
        st.session_state.dash_bucket = ""
    today = date.today()
    counts = {"past": 0, "today": 0, "tomorrow": 0}
    for row in df.fillna("").astype(str).to_dict("records"):
        when = _parse_ddmmyyyy(row.get("proxima_accion_fecha", ""))
        if when is None:
            continue
        if when < today:
            counts["past"] += 1
        elif when == today:
            counts["today"] += 1
        elif when == today + timedelta(days=1):
            counts["tomorrow"] += 1
    st.markdown("##### Próximas acciones")
    c1, c2, c3 = st.columns(3, gap="small")
    for col, key, label in (
        (c1, "past", "Fecha anterior"),
        (c2, "today", "Hoy"),
        (c3, "tomorrow", "Mañana"),
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
    if column in {"persona_ultimo_contacto", "persona_proxima_accion", "persona_primer_contacto"}:
        opts = [""] + list(PERSONA_COMERCIAL_OPCIONES)
        return st.selectbox(label, opts, index=opts.index(value) if value in opts else 0, key=key)
    if column == "valor":
        opts = [""] + list(VALOR_OPCIONES)
        return st.selectbox(label, opts, index=opts.index(value) if value in opts else 0, key=key)
    if column in {"detalle", "otros_contactos", "proxima_accion_detalle", "razon_perdida"}:
        return st.text_area(label, value=value, height=80, key=key)
    return st.text_input(label, value=value, key=key)


def _render_histories(contact: dict[str, str]) -> None:
    contact_id = contact.get("contact_id", "")
    for kind in ("sensores", "campanas", "suscripciones", "incidencias"):
        spec = HISTORY_SPECS[kind]
        rows = history_service().rows_for_contact(kind, contact_id)
        with st.expander(spec.title, expanded=kind in {"sensores", "suscripciones", "incidencias"}):
            render_history_summary(kind, rows)
            col_a, col_b = st.columns([0.24, 0.76])
            with col_a:
                technical = st.checkbox("Ver columnas técnicas", key=f"{kind}_technical_{contact_id}")
            with col_b:
                selected_pos = render_history_table(
                    kind,
                    rows,
                    technical=technical,
                    contact_id=contact_id,
                )
                _handle_history_table_secondary_open(kind, rows, contact, selected_pos)
            _render_history_create_form(kind, contact)
            if rows:
                _render_history_edit_form(kind, rows)


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
        values[header] = str(st.session_state.get(f"{prefix}_{header}", ""))

    error = _validate_history_values(kind, values, prefix=prefix)
    if error:
        st.error(error)
        return False
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
        st.success("Histórico guardado correctamente.")
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

    # Step 2: if not UC501, choose between UG67, solenoide or SIM individual
    if is_uc501:
        root_type = "uc501"
    else:
        root_type = st.radio(
            "Tipo de activo",
            options=["ug67", "solenoide", "sim"],
            format_func=lambda x: {
                "ug67": "UG67 (gateway)",
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
        uc_serials_set = {o.serial_number for o in options_uc501}
        for o in options_uc501:
            uc_labels.append(o.serial_number)
        if selected_sn and selected_sn not in uc_serials_set:
            uc_labels.append(selected_sn)  # keep editing selection visible

        if not options_uc501 and not selected_sn:
            st.info("Aún no hay ningún UC501 disponible en inventario.")
        else:
            if uc_sn_key not in st.session_state:
                st.session_state[uc_sn_key] = selected_sn if selected_sn in uc_labels else (uc_labels[0] if uc_labels else "")
            uc_sn = st.selectbox("UC501 disponibles (SN)", options=uc_labels, key=uc_sn_key)
            if uc_sn:
                opt = next((o for o in options_uc501 if o.serial_number == uc_sn), None)
                if opt is None:
                    # Editing mode: find in full inventory
                    all_opts = inv_svc.asset_options_by_models(("uc501",), inv_df=inv_df)
                    opt = next((o for o in all_opts if o.serial_number == uc_sn), None)
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
                    else:
                        compound = ""
                        _missing = []
                        if not probe_sn:
                            _missing.append("sonda (Teros 10/12)")
                        if not sim_sn:
                            _missing.append("SIM")
                        st.error(
                            f"No se puede guardar: el UC501 **{uc_sn}** no tiene "
                            f"**{' ni '.join(_missing)}** configurada en Inventario. "
                            "Ve a Inventario → edita ese UC501 y vincula los componentes antes de crear el historial."
                        )

    # ── UG67 branch ──────────────────────────────────────────────────────────
    elif root_type == "ug67":
        existing_ug, _ = _extract_ug67_bundle(value)
        ug_sn_key = f"{prefix}_sensor_ug67_sn"

        options_ug67 = inv_svc.available_root_assets_for_history(("ug67",), open_serials=open_serials, inv_df=inv_df)
        selected_sn = str(st.session_state.get(ug_sn_key, existing_ug) or "")
        ug_labels = [""]
        ug_serials_set = {o.serial_number for o in options_ug67}
        for o in options_ug67:
            ug_labels.append(o.serial_number)
        if selected_sn and selected_sn not in ug_serials_set:
            ug_labels.append(selected_sn)

        if not options_ug67 and not selected_sn:
            st.info("Aún no hay ningún UG67 disponible en inventario.")
        else:
            if ug_sn_key not in st.session_state:
                st.session_state[ug_sn_key] = selected_sn if selected_sn in ug_labels else (ug_labels[0] if ug_labels else "")
            ug_sn = st.selectbox("UG67 disponibles (SN)", options=ug_labels, key=ug_sn_key)
            if ug_sn:
                opt = next((o for o in options_ug67 if o.serial_number == ug_sn), None)
                if opt is None:
                    all_opts = inv_svc.asset_options_by_models(("ug67",), inv_df=inv_df)
                    opt = next((o for o in all_opts if o.serial_number == ug_sn), None)
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

    # ── Solenoide branch ─────────────────────────────────────────────────────
    elif root_type == "solenoide":
        existing_sol = _extract_solenoide_sn(value)
        sol_sn_key = f"{prefix}_sensor_solenoide_sn"

        options_sol = inv_svc.available_root_assets_for_history(("solenoide",), open_serials=open_serials, inv_df=inv_df)
        selected_sn = str(st.session_state.get(sol_sn_key, existing_sol) or "")
        sol_labels = [""]
        sol_serials_set = {o.serial_number for o in options_sol}
        for o in options_sol:
            sol_labels.append(o.serial_number)
        if selected_sn and selected_sn not in sol_serials_set:
            sol_labels.append(selected_sn)

        if not options_sol and not selected_sn:
            st.info("Aún no hay ninguna electroválvula solenoide disponible en inventario.")
        else:
            if sol_sn_key not in st.session_state:
                st.session_state[sol_sn_key] = selected_sn if selected_sn in sol_labels else (sol_labels[0] if sol_labels else "")
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
        sim_serials_set = {o.serial_number for o in options_sim}
        for o in options_sim:
            sim_labels.append(o.serial_number)
        if selected_sn and selected_sn not in sim_serials_set:
            sim_labels.append(selected_sn)

        if not options_sim and not selected_sn:
            st.info("Aún no hay ninguna SIM disponible en inventario.")
        else:
            if sim_sn_key not in st.session_state:
                st.session_state[sim_sn_key] = selected_sn if selected_sn in sim_labels else (sim_labels[0] if sim_labels else "")
            sim_sn = st.selectbox("SIM disponibles (SN)", options=sim_labels, key=sim_sn_key)
            if sim_sn:
                opt = next((o for o in options_sim if o.serial_number == sim_sn), None)
                if opt is None:
                    all_opts = inv_svc.asset_options_by_models(("sim",), inv_df=inv_df)
                    opt = next((o for o in all_opts if o.serial_number == sim_sn), None)
                with st.container(border=True):
                    st.caption("**SIM seleccionada**")
                    eid = _sim_eid_from_inv_df(inv_df, opt.inventory_id) if opt else ""
                    if eid:
                        st.caption(f"📶 SN: **{sim_sn}** · EID: **{eid}**")
                    else:
                        st.caption(f"📶 SN: **{sim_sn}**")
                compound = f"sim-{sim_sn}"

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
        index = options.index(selected_value) if selected_value in options else 0
        return st.selectbox(label, options, index=index, key=key)
    if header == "red_otro":
        red_value = st.session_state.get(f"{prefix}_red", "")
        return st.text_input(label, value=value, key=key, disabled=red_value != "otro")
    if header in {"detalles", "detalle", "resolucion"}:
        return st.text_area(label, value=value, key=key, height=90)
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
                if is_uc501 is True and uc_sn:
                    return (
                        f"El UC501 **{uc_sn}** no tiene sonda y/o SIM configuradas en Inventario. "
                        "Ve a Inventario, edita ese UC501 y vincula los componentes antes de guardar."
                    )
                if is_uc501 is False and ug67_sn:
                    return (
                        f"El UG67 **{ug67_sn}** no tiene SIM configurada en Inventario. "
                        "Ve a Inventario, edita ese UG67 y vincula la SIM antes de guardar."
                    )
            return "Debes seleccionar un activo (UC501, UG67, Electroválvula solenoide o SIM individual) antes de guardar."
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
    return None
