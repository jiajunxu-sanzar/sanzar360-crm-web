"""Diálogos y formularios de históricos/seguimiento de la página Contactos."""
from __future__ import annotations

import uuid

import streamlit as st

from app.cache import cultivos_kc_service, history_service, inventory_service, load_cultivos_kc_cached, load_inventory_cached, load_users_cached
from app.state import bump_history_cache
from app import auth
from services.commercial_action_validation import validate_commercial_action_values
from services.notas_validation import validate_nota_history_values
from services.tareas_validation import filter_open_tareas, validate_tarea_history_values
from services.history_service import (
    HISTORY_SPECS,
    HistoryService,
    ProjectIotAssignment,
    count_sensor_assets,
    parse_projectiotid_assignments,
    sensor_association_tokens,
    serialize_projectiotid_assignments,
    validate_projectiotid_assignments,
)
from services.incidencia_association_options import (
    AssociationOption,
    build_campana_history_options,
    build_sensor_history_options,
    option_by_id,
)
from services.inventory_service import normalize_inventory_serial_for_match
from ui.components.cultivo_kc_form import render_new_cultivo_kc_dialog_body
from services.sheet_date_format import (
    SENSOR_SERIAL_NUMBER_FORMAT_HELP,
    is_valid_dd_mm_yyyy,
    is_valid_sensor_serial_number,
    normalize_dd_mm_yyyy,
    normalize_sensor_serial_number,
    validate_dd_mm_yyyy_fields,
)
from ui.components.history_tables import render_history_section
from ui import modal_state

from pages.contacts_common import (
    DATE_COLUMNS_BY_KIND,
    SELECT_OPTIONS,
    _INCIDENCIA_ASSOC_HEADERS,
    filter_open_sensor_history,
    filter_util_notas,
    _clear_modal_flags,
    _clear_history_selection,
    _clear_sensor_picker_state,
    _history_delete_confirm_key,
    _sensor_close_pending_values_key,
    _is_sensor_history_open,
    _apply_smart_defaults,
    _on_dismiss_history_add,
    _on_dismiss_history_edit,
    _on_dismiss_sensor_close_location,
)
from pages.contacts_inventory_sync import (
    _extract_uc501_bundle,
    _extract_ug67_bundle,
    _extract_solenoide_sn,
    _extract_sim_sn,
    _extract_em500_sn,
    _serial_in_labels,
    _normalized_serial_set,
    _resolve_inventory_option,
    _infer_sensor_root_type,
    _serials_from_sensor_history_strings,
    _reconcile_inventory_locations_for_sensor_serials,
    _sync_inventory_from_sensor_history,
    _sim_eid_from_inv_df,
)




def _campana_actor_name() -> str:
    uid = auth.get_authenticated_user_id()
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    for user in users:
        if user.employee_id == uid:
            return user.nombre
    return uid


def _cultivo_kc_nombres() -> list[str]:
    try:
        df = load_cultivos_kc_cached(st.session_state.get("cultivos_kc_cache_version", 0))
    except Exception:
        df = cultivos_kc_service().cultivos_df()
    if df.empty or "nombre" not in df.columns:
        return []
    names = sorted(
        {str(x).strip() for x in df["nombre"].fillna("").astype(str).tolist() if str(x).strip()},
        key=str.casefold,
    )
    return names


CAMPANA_CULTIVO_CREATE_KEY = "campana_cultivo_create_open"
CAMPANA_CULTIVO_TARGET_PREFIX_KEY = "campana_cultivo_create_prefix"


def _render_campana_cultivo_field(prefix: str, value: str, key: str) -> str:
    names = _cultivo_kc_nombres()
    options = [""] + names
    current = str(value or "").strip()
    if current and current not in options:
        options = options + [current]
    col_sel, col_plus = st.columns([0.85, 0.15])
    with col_sel:
        index = options.index(current) if current in options else 0
        selected = st.selectbox("Cultivo", options, index=index, key=key)
    with col_plus:
        st.write("")
        if st.button("＋", help="Crear nuevo cultivo Kc", key=f"{prefix}_cultivo_plus"):
            st.session_state[CAMPANA_CULTIVO_CREATE_KEY] = True
            st.session_state[CAMPANA_CULTIVO_TARGET_PREFIX_KEY] = prefix
            st.rerun()
    # Nota: esto se renderiza EN LÍNEA (no como @st.dialog) porque este campo
    # se usa dentro de _add_history_dialog/_edit_history_dialog, que ya son
    # diálogos abiertos. Streamlit no permite anidar un @st.dialog dentro de
    # otro ("Dialogs may not be nested"), así que el alta de cultivo se
    # muestra aquí mismo, en un contenedor, sin abrir un segundo diálogo.
    if st.session_state.get(CAMPANA_CULTIVO_CREATE_KEY) and st.session_state.get(CAMPANA_CULTIVO_TARGET_PREFIX_KEY) == prefix:
        with st.container(border=True):
            st.markdown("**Alta de cultivo**")

            def _on_saved(_cid: str, nombre: str) -> None:
                st.session_state[key] = nombre
                st.session_state.pop(CAMPANA_CULTIVO_CREATE_KEY, None)
                st.session_state.pop(CAMPANA_CULTIVO_TARGET_PREFIX_KEY, None)

            def _on_cancel() -> None:
                st.session_state.pop(CAMPANA_CULTIVO_CREATE_KEY, None)
                st.session_state.pop(CAMPANA_CULTIVO_TARGET_PREFIX_KEY, None)

            render_new_cultivo_kc_dialog_body(
                key_prefix=f"{prefix}_cultivo_inline_new",
                actor_name=_campana_actor_name(),
                on_saved=_on_saved,
                on_cancel=_on_cancel,
            )
    return selected


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

@st.dialog("Nuevo histórico", width="large", on_dismiss=_on_dismiss_history_add)
def _add_history_dialog(kind: str, contact: dict[str, str]) -> None:
    spec = HISTORY_SPECS[kind]
    st.markdown(f"**{spec.title}** · {contact.get('nombre', '') or 'contacto'}")
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
    elif kind == "campanas":
        excluded = frozenset({"cultivo"})
        prefix = f"{kind}_new"
        st.markdown("**Cultivo**")
        _render_campana_cultivo_field(prefix, "", f"{prefix}_cultivo")

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

@st.dialog("Editar histórico", width="large", on_dismiss=_on_dismiss_history_edit)
def _edit_history_dialog(kind: str, contact: dict[str, str], row: dict[str, str]) -> None:
    spec = HISTORY_SPECS[kind]
    contact_id = contact.get("contact_id", "")
    row_id = str(row.get(spec.id_column, "") or "")
    st.markdown(f"**{spec.title}** · {contact.get('nombre', '') or 'contacto'}")
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
    elif kind == "campanas":
        excluded = frozenset({"cultivo"})
        prefix = f"{kind}_{row_id}"
        st.markdown("**Cultivo**")
        _render_campana_cultivo_field(prefix, str(row.get("cultivo", "") or ""), f"{prefix}_cultivo")

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

@st.dialog("Cierre de histórico sensor", on_dismiss=_on_dismiss_sensor_close_location)
def _sensor_close_location_dialog(kind: str, contact: dict[str, str], row: dict[str, str]) -> None:
    spec = HISTORY_SPECS[kind]
    row_id = str(row.get(spec.id_column, "") or "")
    contact_id = str(contact.get("contact_id", "") or "")
    pending_values = st.session_state.get(_sensor_close_pending_values_key(row_id), None)
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

def _render_seguimiento_comercial_section(contact: dict[str, str], rows: list[dict[str, str]]) -> None:
    contact_id = str(contact.get("contact_id", "") or "")
    render_history_section("seguimiento_comercial", rows, contact_id)

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
    elif kind == "notas":
        toggle_key = f"hist_notas_util_only_{contact_id}"
        if toggle_key not in st.session_state:
            st.session_state[toggle_key] = True
        only_util = st.toggle("Solo útiles", key=toggle_key)
        if only_util:
            display_rows = filter_util_notas(rows)
            n_util = len(display_rows)
            n_total = len(rows)
            if n_util < n_total:
                st.caption(f"{n_util} útil{'es' if n_util != 1 else ''} · {n_total} en total")
    elif kind == "tareas":
        toggle_key = f"hist_tareas_open_only_{contact_id}"
        if toggle_key not in st.session_state:
            st.session_state[toggle_key] = True
        only_open = st.toggle("Solo abiertas", key=toggle_key)
        if only_open:
            display_rows = filter_open_tareas(rows)
            n_open = len(display_rows)
            n_total = len(rows)
            if n_open < n_total:
                st.caption(f"{n_open} abierta{'s' if n_open != 1 else ''} · {n_total} en total")
    render_history_section(kind, display_rows, contact_id)

def _render_history_kind_section(
    contact: dict[str, str],
    kind: str,
    *,
    expanded: bool | None = None,
) -> None:
    contact_id = contact.get("contact_id", "")
    spec = HISTORY_SPECS[kind]
    rows = history_service().rows_for_contact(kind, contact_id)
    # Contador en el título: se ve qué secciones tienen datos sin abrirlas.
    title = f"{spec.title} ({len(rows)})"
    if expanded is None:
        expanded_default = kind == "seguimiento_comercial" and bool(rows)
    else:
        expanded_default = expanded
    with st.expander(title, expanded=expanded_default):
        if kind == "seguimiento_comercial":
            _render_seguimiento_comercial_section(contact, rows)
            return
        _render_operative_history_cards_section(contact, kind, rows)

def _render_histories(contact: dict[str, str]) -> None:
    for kind in (
        "seguimiento_comercial",
        "tareas",
        "notas",
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
    elif kind == "campanas":
        excluded = frozenset({"cultivo"})
        initial_cultivo = (existing or {}).get("cultivo", "")
        st.markdown("**Cultivo**")
        _render_campana_cultivo_field(prefix, str(initial_cultivo or ""), f"{prefix}_cultivo")

    with st.form(f"history_form_{kind}_{suffix}_{base.get('contact_id', '')}"):
        _render_history_form_body(kind, base, existing, excluded_headers=excluded)
        submitted = st.form_submit_button("Guardar histórico")
    if submitted and _submit_history_form(kind, base, existing):
        st.rerun()

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
    _always_skip = {
        spec.id_column,
        "contact_id",
        "nombre_cliente",
        "created_at",
        "updated_at",
        "coordenadas_parcela",  # legacy; UI usa latitud/longitud
    }
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
    if kind == "notas":
        for date_col in ("fecha_creacion", "fecha_update"):
            raw = (values.get(date_col, "") or "").strip()
            if raw:
                values[date_col] = normalize_dd_mm_yyyy(raw) or raw
    if kind == "tareas":
        for date_col in ("fecha_creacion", "fecha_update", "fecha_limite"):
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
    if kind == "notas" and header == "estado_nota":
        bool_key = f"{key}__util"
        if bool_key not in st.session_state:
            st.session_state[bool_key] = str(value or "Útil").strip() != "Obsoleta"
        is_util = st.toggle("Nota útil", key=bool_key)
        result = "Útil" if is_util else "Obsoleta"
        st.session_state[key] = result
        return result
    if kind == "notas" and header == "persona_nota":
        from app.cache import load_users_cached
        from services.users_service import person_select_options

        options = person_select_options(
            load_users_cached(st.session_state.get("users_cache_version", 0)),
            current=value,
        )
        index = options.index(value) if value in options else 0
        return st.selectbox("Autor", options, index=index, key=key)
    if kind == "notas" and header == "titulo":
        return st.text_input("Título", value=value, key=key)
    if kind == "notas" and header == "notas":
        return st.text_area("Notas", value=value, key=key, height=120)
    if kind == "tareas" and header in {"persona_creacion", "persona_gestiona"}:
        from app.cache import load_users_cached
        from services.users_service import person_select_options

        options = person_select_options(
            load_users_cached(st.session_state.get("users_cache_version", 0)),
            current=value,
        )
        index = options.index(value) if value in options else 0
        label_ui = "Creado por" if header == "persona_creacion" else "Gestiona"
        return st.selectbox(label_ui, options, index=index, key=key)
    if kind == "seguimiento_comercial" and header in {"persona_contacto", "proxima_accion_persona"}:
        from app.cache import load_users_cached
        from services.users_service import person_select_options

        options = person_select_options(
            load_users_cached(st.session_state.get("users_cache_version", 0)),
            current=value,
        )
        index = options.index(value) if value in options else 0
        return st.selectbox(label, options, index=index, key=key)
    if kind == "tareas" and header == "titulo":
        return st.text_input("Título", value=value, key=key)
    if kind == "tareas" and header == "notas":
        return st.text_area("Notas", value=value, key=key, height=120)
    if kind == "tareas" and header == "estado_tarea":
        options = list(SELECT_OPTIONS.get("estado_tarea", []))
        selected = value if value in options else ("Sin iniciar" if not (value or "").strip() else value)
        if selected not in options:
            options = [selected] + options
        index = options.index(selected) if selected in options else 0
        return st.selectbox("Estado", options, index=index, key=key)
    if kind == "sensores" and header == "projectiotid":
        sensor_serial = str(st.session_state.get(f"{prefix}_sensor_serial_number", ""))
        return _render_projectiotid_editor(prefix, value, sensor_serial)
    if kind == "campanas" and header == "historial_sensor_id":
        contact_id = str(st.session_state.get(f"{prefix}_id_contact", "") or "")
        sensor_rows = history_service().rows_for_contact("sensores", contact_id) if contact_id else []
        sensor_options = build_sensor_history_options(sensor_rows)
        label_by_id = {opt.id: opt.label for opt in sensor_options}
        id_by_label = {opt.label: opt.id for opt in sensor_options}
        labels = [""] + [opt.label for opt in sensor_options]
        current_label = label_by_id.get(str(value or "").strip(), "")
        if str(value or "").strip() and not current_label:
            # Legacy / cerrado: mostrar id pero permitir conservar
            labels = labels + [f"(id) {value}"]
            id_by_label[f"(id) {value}"] = str(value).strip()
            current_label = f"(id) {value}"
        index = labels.index(current_label) if current_label in labels else 0
        picked = st.selectbox("Sensor (histórico)", labels, index=index, key=key)
        return id_by_label.get(picked, "") if picked else ""
    if kind == "campanas" and header == "cultivo":
        return _render_campana_cultivo_field(prefix, value, key)
    if kind == "campanas" and header in {"latitud", "longitud"}:
        return st.text_input(label, value=value, key=key, placeholder="ej. 40.4168")
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
    if header == "sensor_serial_number":
        return _render_sensor_serial_field(value, prefix, key)
    if header == "cantidad_sensores":
        return st.text_input(label, value=str(count_sensor_assets(st.session_state.get(f"{prefix}_sensor_serial_number", value))), key=key, disabled=True)
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
    if kind == "notas":
        return validate_nota_history_values(values)
    if kind == "tareas":
        return validate_tarea_history_values(values)
    return None
