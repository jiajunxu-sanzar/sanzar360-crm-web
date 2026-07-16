"""Estado de sesión, constantes y helpers compartidos de la página Contactos."""
from __future__ import annotations

from difflib import SequenceMatcher
from datetime import date, datetime

import pandas as pd
import streamlit as st

from app import auth
from app.cache import load_contact_sensor_overview_cached, load_users_cached
from config.settings import (
    PERSONA_COMERCIAL_OPCIONES,
    CANAL_CONTACTO_OPCIONES,
    EMAIL_CLASIFICACION_OPCIONES,
    RESULTADO_CONTACTO_OPCIONES,
)
from ui.components.contact_overview_table import filter_overview_by_contact_ids, sort_overview_by_proxima_accion
from ui import modal_state
from ui.components.history import clear_history_table_selection

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
        # Import perezoso: evita el ciclo contacts_common <-> contacts_history_forms.
        from pages.contacts_history_forms import _clear_incidencia_association_state

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
        # Import perezoso: evita el ciclo contacts_common <-> contacts_history_forms.
        from pages.contacts_history_forms import _clear_incidencia_association_state

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

def _actor_name() -> str:
    """Return the display name of the currently logged-in user."""
    uid = auth.get_authenticated_user_id()
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    for u in users:
        if u.employee_id == uid:
            return u.nombre
    return uid

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
