from __future__ import annotations

import html
import zlib

import pandas as pd
import streamlit as st

from ui.components.page_header import render_page_header
from app.cache import (
    clear_all_cache,
    history_service,
    load_acciones_cached,
    load_contact_sensor_overview_cached,
    load_users_cached,
    overview_pdf_bytes_cached,
    overview_xlsx_bytes_cached,
    sheets_service,
)
from app.state import (
    bump_contacts_cache,
    bump_history_cache,
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
    CONTACT_ESTADO_OPCIONES,
    FUENTE_LEAD_OPCIONES,
    NO_RECIBIR_EMAILS_NO,
    NO_RECIBIR_EMAILS_SI,
    TIPO_RELACION_OPCIONES,
    VALOR_OPCIONES,
)
from services.contact_proxima_index import enrich_contacts_with_proxima, latest_commercial_contact_row
from services.tareas_validation import next_open_tarea
from services.contact_deletion import delete_contact_and_related_data
from services.contact_ficha_export import (
    build_contact_ficha_pdf_bytes,
    build_contact_ficha_xlsx_bytes,
    collect_histories_for_contact,
)
from services.contact_sensor_overview import (
    filter_by_sensor_overview,
    semaforo_by_contact_id,
    semaforo_display_prefix,
)
from services.contact_use_cases import create_empty_contact, save_contact_by_id
from services.contact_flags import (
    TIPO_RELACION_BOARD,
    is_sheet_true,
    is_visto_hoy,
    values_for_flag,
    values_for_visto_toggle,
)
from services.proxima_accion_stats import (
    apply_dash_bucket_date_filter,
    filter_by_contact_estado,
    filter_by_persona_proxima_accion,
    filter_by_responsable_cliente,
    next_action_bucket_counts,
)
from services.users_service import person_select_options
from services.sheet_date_format import contact_soft_warnings, validate_contact_date_fields
from ui.palette import STATUS_NEUTRAL, STATUS_SUCCESS, STATUS_WARNING
from ui.components.customer_timeline import render_contact_timeline_block
from ui.components.contact_detail_header import render_contact_detail_header
from ui.components.contact_overview_table import (
    format_incidencias_cell,
    format_proxima_accion_cell,
    format_sensors_cell,
    format_ultimo_contacto_cell,
)
from ui.components.tables import filter_dataframe

from pages.contacts_common import (  # noqa: F401
    MANUAL_CRM_URL,
    DATE_COLUMNS_BY_KIND,
    SELECT_OPTIONS,
    CONTACT_LIST_PANEL_HEIGHT_BASE,
    CONTACT_LIST_PANEL_HEIGHT_WITH_DETAIL,
    NEW_CONTACT_FLOW_KEY,
    NEW_CONTACT_FLOW_IDLE,
    NEW_CONTACT_FLOW_OPEN,
    NEW_CONTACT_FLOW_SUBMITTING,
    NEW_CONTACT_SIMILAR_CANDIDATES_KEY,
    NEW_CONTACT_REQUIRE_SECOND_CONFIRM_KEY,
    NEW_CONTACT_CONFIRM_OVERRIDE_KEY,
    CONTACTS_SHOW_LOST_KEY,
    CONTACTS_ONLY_WITH_SENSORS_KEY,
    CONTACTS_VIEW_MODE_KEY,
    CONTACTS_FILTERED_IDS_KEY,
    CONTACTS_VIEW_FICHA,
    CONTACTS_VIEW_TABLA,
    CONTACTS_SAVE_SUCCESS_KEY,
    CONTACTS_DELETE_SUCCESS_KEY,
    CONTACTS_DELETE_TARGET_ID_KEY,
    CONTACTS_DELETE_TARGET_NAME_KEY,
    HISTORY_DELETE_CONFIRM_PREFIX,
    DASH_PERSONA_PROXIMA_ACCION_KEY,
    DASH_ESTADO_FILTER_KEY,
    DASH_RESPONSABLE_FILTER_KEY,
    _INCIDENCIA_ASSOC_HEADERS,
    OFICINA_CONTACT_NAME,
    pin_oficina_contact_first,
    filter_open_sensor_history,
    _contacts_block_spacer,
    _contact_display_name,
    _filtered_overview_display_df,
    _clear_modal_flags,
    _new_contact_flow_state_get,
    _new_contact_flow_set,
    _new_contact_flow_open,
    _new_contact_flow_start_submit,
    _new_contact_flow_cancel,
    _new_contact_flow_finish,
    _normalize_contact_name,
    _find_similar_contact_names,
    _clear_history_selection,
    _clear_sensor_picker_state,
    _history_delete_confirm_key,
    _sensor_close_pending_values_key,
    _on_dismiss_history_edit,
    _on_dismiss_history_add,
    _on_dismiss_sensor_close_location,
    _is_sensor_history_open,
    _clear_contact_overlay_state,
    _set_delete_target,
    _clear_delete_target,
    _actor_name,
    _history_smart_defaults,
    _apply_smart_defaults,
    autosave_contact_fields,
)
from pages.contacts_inventory_sync import (  # noqa: F401
    _parse_ddmmyyyy,
    _extract_uc501_bundle,
    _extract_ug67_bundle,
    _extract_ws6210_bundle,
    _extract_solenoide_sn,
    _extract_sim_sn,
    _extract_em500_sn,
    _extract_wh51l_sn,
    _extract_ws69_sn,
    _find_inventory_option_by_serial,
    _serial_in_labels,
    _normalized_serial_set,
    _resolve_inventory_option,
    _infer_sensor_root_type,
    _collect_all_serials_from_sensor_sn,
    _serials_from_sensor_history_strings,
    _reconcile_inventory_locations_for_sensor_serials,
    _sync_inventory_from_sensor_history,
    _sim_eid_from_inv_df,
)
from pages.contacts_history_forms import (  # noqa: F401
    _SEGUIMIENTO_CONTACTO_FIELDS,
    _SEGUIMIENTO_CANAL_FIELDS,
    _SEGUIMIENTO_PROXIMA_FIELDS,
    _maybe_render_sensor_close_location_modal,
    _maybe_render_add_history_modal,
    _maybe_render_edit_history_modal,
    _maybe_render_riego_campanas_modal,
    _incidencia_association_init_key,
    _clear_incidencia_association_state,
    _incidencia_label_maps,
    _init_incidencia_association_state,
    _sync_incidencia_sensor_pick,
    _sync_incidencia_campana_pick,
    _resolve_incidencia_assoc_field,
    _render_incidencia_association_block,
    _add_history_dialog,
    _delete_history_row_and_sync_inventory,
    _edit_history_dialog,
    _sensor_close_location_dialog,
    _render_seguimiento_comercial_section,
    _render_operative_history_cards_section,
    _render_history_kind_section,
    _render_histories,
    _render_history_create_form,
    _render_history_edit_form,
    _render_history_form,
    _render_seguimiento_canal_block,
    _seguimiento_modal_initial,
    _render_seguimiento_comercial_fields,
    _render_history_form_body,
    _render_history_form_grouped_body,
    _render_projectiotid_editor,
    _submit_history_form,
    _render_sensor_serial_field,
    _field_for_header,
    _validate_history_values,
)

_BUCKET_KEYS = ("past", "today", "tomorrow", "future")
_BUCKET_LABELS = {
    "past": "Atrasadas",
    "today": "Hoy",
    "tomorrow": "Mañana",
    "future": "Futuras",
}
_DETAIL_VIEW_OPTIONS = ("Datos", "Históricos", "Actividad")
_LOST_ROW_CSS = "color:#b91c1c"


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

        header_cols = st.columns([0.84, 0.16], vertical_alignment="center")
        with header_cols[0]:
            render_page_header("Contactos")
        with header_cols[1]:
            st.link_button(
                "Manual",
                MANUAL_CRM_URL,
                width="stretch",
                icon=":material/menu_book:",
                help="Abre el manual de uso del CRM en Google Docs",
            )
        # Toast en vez de banner: no desplaza el contenido de la página al
        # confirmar un guardado/borrado, así la vista no "salta".
        if st.session_state.get(CONTACTS_SAVE_SUCCESS_KEY):
            st.toast(str(st.session_state.pop(CONTACTS_SAVE_SUCCESS_KEY)), icon="✅")
        if st.session_state.get(CONTACTS_DELETE_SUCCESS_KEY):
            st.toast(str(st.session_state.pop(CONTACTS_DELETE_SUCCESS_KEY)), icon="🗑️")
        if df.empty:
            st.warning("No hay contactos cargados. Puedes crear el primero con «Nuevo contacto».")

        if current_selected:
            # Ficha a pantalla completa; «Cerrar ficha» devuelve al listado.
            with st.container(border=True):
                df = _render_contact_detail(df, current_selected)
        else:
            # Sin selección: la lista ocupa todo el ancho.
            _render_contact_list(df)
        return df

@st.fragment
def _render_contact_list(df: pd.DataFrame) -> None:
    # Fragment: teclear en la búsqueda o cambiar filtros re-ejecuta solo el
    # listado; seleccionar una fila hace st.rerun() de app para abrir la ficha.
    _restore_filter_state()
    if st.session_state.get(CONTACTS_VIEW_MODE_KEY) not in (CONTACTS_VIEW_FICHA, CONTACTS_VIEW_TABLA):
        st.session_state[CONTACTS_VIEW_MODE_KEY] = CONTACTS_VIEW_FICHA
    if CONTACTS_SHOW_LOST_KEY not in st.session_state:
        # Soft migration from legacy filter key if present.
        st.session_state[CONTACTS_SHOW_LOST_KEY] = bool(st.session_state.get("contact_filter_show_lost", False))

    acciones_df = load_acciones_cached(st.session_state.get("history_cache_version", 0))
    df = enrich_contacts_with_proxima(df, acciones_df)
    overview = load_contact_sensor_overview_cached(st.session_state.get("history_cache_version", 0))
    semaforo_map = semaforo_by_contact_id(overview)

    with st.container(border=True):
        _render_next_action_strip(df)
    _contacts_block_spacer()
    with st.container(border=True):
        head_cols = st.columns([0.34, 0.38, 0.28], gap="small")
        head_cols[0].markdown("##### Contactos")
        with head_cols[1]:
            # El radio no se renderiza con la ficha abierta, así que su estado de
            # widget se pierde; persistimos el modo en una clave propia.
            if "_contacts_view_mode_widget" not in st.session_state:
                st.session_state["_contacts_view_mode_widget"] = st.session_state[CONTACTS_VIEW_MODE_KEY]
            view_mode = st.radio(
                "Vista",
                options=(CONTACTS_VIEW_FICHA, CONTACTS_VIEW_TABLA),
                format_func=lambda v: "Lista" if v == CONTACTS_VIEW_FICHA else "Seguimiento",
                horizontal=True,
                key="_contacts_view_mode_widget",
                label_visibility="collapsed",
            )
            st.session_state[CONTACTS_VIEW_MODE_KEY] = view_mode
        with head_cols[2]:
            if st.button("Nuevo contacto", key="create_contact_top", width="stretch", icon=":material/person_add:"):
                _create_contact_dialog(df)

        search_cols = st.columns([0.56, 0.22, 0.22], gap="small", vertical_alignment="center")
        with search_cols[0]:
            query = _render_search_input()
        with search_cols[1]:
            st.toggle("Mostrar perdidos", key=CONTACTS_SHOW_LOST_KEY)
        with search_cols[2]:
            if CONTACTS_ONLY_WITH_SENSORS_KEY not in st.session_state:
                st.session_state[CONTACTS_ONLY_WITH_SENSORS_KEY] = True
            st.toggle("Con sensores", key=CONTACTS_ONLY_WITH_SENSORS_KEY)
        with st.expander("Más filtros (estado, provincia, municipio, tipo, cultivo)", icon=":material/tune:"):
            advanced = _render_advanced_filters(df)

        filtered = _apply_contact_filters(df, overview, query, advanced)
        _store_filtered_ids(filtered)

        info_cols = st.columns([0.4, 0.6], gap="small")
        info_cols[0].caption(f"{len(filtered)} contactos encontrados · click en una fila para abrir la ficha")
        info_cols[1].caption(
            "<div style='text-align:right'>🟢 sensores al día · 🟡 sensores con seguimiento · 🔴 perdido</div>",
            unsafe_allow_html=True,
        )
        if view_mode == CONTACTS_VIEW_TABLA:
            _render_overview_table()
        else:
            _render_contact_table(filtered, semaforo_map)
    _persist_filter_state()

_PERSISTED_FILTER_KEYS = (
    "contact_filter_text",
    "contact_filter_status",
    "contact_filter_province",
    "contact_filter_entity",
    "contact_filter_municipio",
    "contact_filter_cultivos",
    CONTACTS_SHOW_LOST_KEY,
    CONTACTS_ONLY_WITH_SENSORS_KEY,
    DASH_PERSONA_PROXIMA_ACCION_KEY,
    DASH_ESTADO_FILTER_KEY,
    DASH_RESPONSABLE_FILTER_KEY,
    "dash_bucket",
)

def _restore_filter_state() -> None:
    """Streamlit descarta el estado de widgets no renderizados (p. ej. con la
    ficha abierta a pantalla completa); restaurar desde las claves espejo."""
    for key in _PERSISTED_FILTER_KEYS:
        mirror = f"_persist_{key}"
        if key not in st.session_state and mirror in st.session_state:
            st.session_state[key] = st.session_state[mirror]

def _persist_filter_state() -> None:
    for key in _PERSISTED_FILTER_KEYS:
        if key in st.session_state:
            st.session_state[f"_persist_{key}"] = st.session_state[key]

def _render_search_input() -> str:
    return st.text_input(
        "Buscar",
        key="contact_filter_text",
        label_visibility="collapsed",
        placeholder="Nombre, municipio, correo, teléfono, cultivo…",
        icon=":material/search:",
    )

def _render_advanced_filters(df: pd.DataFrame) -> dict[str, str]:
    def _options(column: str) -> list[str]:
        return [""] + sorted(
            [x for x in df.get(column, pd.Series(dtype=str)).fillna("").astype(str).unique() if x]
        )

    # Descartar valores restaurados que ya no estén entre las opciones.
    for key, opts in (
        ("contact_filter_status", [""] + list(CONTACT_ESTADO_OPCIONES)),
        ("contact_filter_province", _options("provincia")),
        ("contact_filter_entity", _options("tipo_entidad")),
        ("contact_filter_municipio", _options("municipio")),
    ):
        if key in st.session_state and st.session_state[key] not in opts:
            st.session_state[key] = ""

    filter_row_1 = st.columns(3, gap="small")
    status = filter_row_1[0].selectbox("Estado", [""] + list(CONTACT_ESTADO_OPCIONES), key="contact_filter_status")
    province = filter_row_1[1].selectbox("Provincia", _options("provincia"), key="contact_filter_province")
    entity_type = filter_row_1[2].selectbox("Tipo de entidad", _options("tipo_entidad"), key="contact_filter_entity")
    filter_row_2 = st.columns(2, gap="small")
    municipio = filter_row_2[0].selectbox("Municipio", _options("municipio"), key="contact_filter_municipio")
    cultivos = filter_row_2[1].text_input("Cultivos contiene", key="contact_filter_cultivos")
    return {
        "status": status,
        "province": province,
        "entity_type": entity_type,
        "municipio": municipio,
        "cultivos": cultivos,
    }

def _apply_contact_filters(
    df: pd.DataFrame,
    overview: pd.DataFrame,
    query: str,
    advanced: dict[str, str],
) -> pd.DataFrame:
    filtered = filter_dataframe(
        df,
        query,
        ["nombre", "municipio", "provincia", "correo", "telefono", "cultivos", "contact_id"],
    )
    if advanced.get("province"):
        filtered = filtered[filtered["provincia"].astype(str) == advanced["province"]]
    if advanced.get("status"):
        filtered = filtered[filtered["estado"].astype(str) == advanced["status"]]
    if advanced.get("entity_type"):
        filtered = filtered[filtered["tipo_entidad"].astype(str) == advanced["entity_type"]]
    if advanced.get("municipio"):
        filtered = filtered[filtered["municipio"].astype(str) == advanced["municipio"]]
    if (advanced.get("cultivos") or "").strip():
        filtered = filtered[
            filtered["cultivos"].fillna("").astype(str).str.contains(advanced["cultivos"].strip(), case=False, na=False)
        ]
    if not bool(st.session_state.get(CONTACTS_SHOW_LOST_KEY, True)):
        filtered = filtered[~filtered["estado"].astype(str).map(is_contact_perdido)]
    persona_proxima = str(st.session_state.get(DASH_PERSONA_PROXIMA_ACCION_KEY, "") or "")
    filtered = filter_by_persona_proxima_accion(filtered, persona_proxima)
    dash_responsable = str(st.session_state.get(DASH_RESPONSABLE_FILTER_KEY, "") or "")
    filtered = filter_by_responsable_cliente(filtered, dash_responsable)
    dash_estado = str(st.session_state.get(DASH_ESTADO_FILTER_KEY, "") or "")
    filtered = filter_by_contact_estado(filtered, dash_estado)
    dash_bucket = st.session_state.get("dash_bucket") or ""
    if dash_bucket:
        filtered = apply_dash_bucket_date_filter(filtered, str(dash_bucket))
    if bool(st.session_state.get(CONTACTS_ONLY_WITH_SENSORS_KEY, True)):
        filtered = filter_by_sensor_overview(filtered, overview, only_with_sensors=True)
    filtered = pin_oficina_contact_first(filtered)
    return filtered.reset_index(drop=True)

def _store_filtered_ids(filtered: pd.DataFrame) -> None:
    st.session_state[CONTACTS_FILTERED_IDS_KEY] = (
        filtered["contact_id"].fillna("").astype(str).str.strip().tolist()
        if not filtered.empty and "contact_id" in filtered.columns
        else []
    )

def _ids_signature(ids: list[str], *, prefix: str) -> str:
    joined = "|".join(ids)
    return f"{prefix}_{zlib.crc32(joined.encode('utf-8')):08x}"

def _table_height(nrows: int, cap: int) -> int:
    # ~35px por fila + cabecera; con tope para no crear scroll de página.
    return int(min(cap, 35 * nrows + 40))

def _render_contact_table(
    filtered: pd.DataFrame,
    semaforo_map: dict[str, str] | None = None,
) -> None:
    if filtered.empty:
        st.info("No hay datos para mostrar.")
        return

    semaforo_lookup = semaforo_map or {}
    records = filtered.fillna("").astype(str).to_dict("records")
    ids: list[str] = []
    icons: list[str] = []
    lost_flags: list[bool] = []
    data: dict[str, list[str]] = {"Nombre": [], "Estado": [], "Provincia": [], "Municipio": []}
    for row in records:
        contact_id = str(row.get("contact_id", "")).strip()
        ids.append(contact_id)
        is_lost = is_contact_perdido(str(row.get("estado", "")))
        lost_flags.append(is_lost)
        sem = semaforo_lookup.get(contact_id, "sin_sensores")
        icon = "🔴" if is_lost else semaforo_display_prefix(sem, is_lost=False).strip()
        icons.append(icon)
        data["Nombre"].append(row.get("nombre", "") or "Sin nombre")
        data["Estado"].append(row.get("estado", "") or "Sin estado")
        data["Provincia"].append(row.get("provincia", "") or "—")
        data["Municipio"].append(row.get("municipio", "") or "—")

    disp = pd.DataFrame({"sem": icons, **data})

    styler = disp.style.apply(
        lambda r: [_LOST_ROW_CSS if lost_flags[r.name] else ""] * len(r),
        axis=1,
    )
    column_config = {
        "sem": st.column_config.TextColumn("", width=34, help="Semáforo de sensores / perdido"),
        "Nombre": st.column_config.TextColumn("Nombre", width="large"),
        "Estado": st.column_config.TextColumn("Estado", width="medium"),
        "Provincia": st.column_config.TextColumn("Provincia", width="medium"),
        "Municipio": st.column_config.TextColumn("Municipio", width="medium"),
    }
    event = st.dataframe(
        styler,
        hide_index=True,
        width="stretch",
        height=_table_height(len(records), 600),
        on_select="rerun",
        selection_mode="single-row",
        key=_ids_signature(ids, prefix="contacts_df_f"),
        column_config=column_config,
    )
    rows = list(getattr(event.selection, "rows", []) or [])
    if rows:
        picked = ids[rows[0]]
        if picked and picked != str(st.session_state.get("selected_contact_id", "") or ""):
            _clear_modal_flags()
            st.session_state["selected_contact_id"] = picked
            st.rerun()

def _overview_row_css(semaforo: str) -> str:
    sem = (semaforo or "").strip().lower()
    style = STATUS_SUCCESS if sem == "verde" else STATUS_WARNING if sem == "amarillo" else STATUS_NEUTRAL
    return f"background-color:{style.bg};color:{style.fg}"

def _render_overview_table() -> None:
    overview_df = _filtered_overview_display_df()
    if overview_df.empty:
        st.info("No hay contactos en el resumen.")
        return

    records = [
        row
        for row in overview_df.fillna("").to_dict("records")
        if str(row.get("contact_id", "") or "").strip()
    ]
    if not records:
        st.info("No hay contactos en el resumen.")
        return

    xlsx_bytes, xlsx_name = overview_xlsx_bytes_cached(overview_df)
    pdf_bytes: bytes | None = None
    pdf_name = "contactos_sensores.pdf"
    pdf_error: str | None = None
    try:
        pdf_bytes, pdf_name = overview_pdf_bytes_cached(overview_df)
    except Exception as exc:
        # LayoutError u otros fallos de ReportLab no deben tumbar Contactos.
        pdf_error = str(exc) or exc.__class__.__name__

    export_cols = st.columns([0.2, 0.2, 0.6], gap="small")
    export_cols[0].download_button(
        "Exportar Excel",
        data=xlsx_bytes,
        file_name=xlsx_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="contacts_export_overview_xlsx",
        width="stretch",
    )
    if pdf_bytes is not None:
        export_cols[1].download_button(
            "Exportar PDF",
            data=pdf_bytes,
            file_name=pdf_name,
            mime="application/pdf",
            key="contacts_export_overview_pdf",
            width="stretch",
        )
    else:
        export_cols[1].caption("PDF no disponible")
        if pdf_error:
            export_cols[1].caption(f"Error al generar PDF: {pdf_error[:120]}")
    export_cols[2].caption("<div style='text-align:right'>Ordenados por próxima acción</div>", unsafe_allow_html=True)

    ids = [str(row.get("contact_id", "")).strip() for row in records]
    disp = pd.DataFrame(
        {
            "Contacto": [str(r.get("nombre", "") or "Sin nombre") for r in records],
            "Sensores": [format_sensors_cell(r.get("num_sensores"), r.get("sensor_sns")) for r in records],
            "Último contacto": [
                format_ultimo_contacto_cell(
                    r.get("ultimo_contacto"), r.get("ultimo_contacto_canal"), r.get("ultimo_contacto_detalle")
                )
                for r in records
            ],
            "Próxima acción": [
                format_proxima_accion_cell(r.get("proxima_accion_fecha"), r.get("proxima_accion_detalle"))
                for r in records
            ],
            "Incidencias": [
                format_incidencias_cell(r.get("incidencias_abiertas"), r.get("incidencias_detalle"))
                for r in records
            ],
        }
    )
    row_css = [_overview_row_css(str(r.get("semaforo", "") or "")) for r in records]
    styler = disp.style.apply(lambda r: [row_css[r.name]] * len(r), axis=1)
    event = st.dataframe(
        styler,
        hide_index=True,
        width="stretch",
        height=_table_height(len(records), 600),
        on_select="rerun",
        selection_mode="single-row",
        key=_ids_signature(ids, prefix="contacts_df_ov"),
        column_config={
            "Contacto": st.column_config.TextColumn("Contacto", width="medium"),
            "Sensores": st.column_config.TextColumn("Sensores", width="medium"),
            "Último contacto": st.column_config.TextColumn("Último contacto", width="large"),
            "Próxima acción": st.column_config.TextColumn("Próxima acción", width="large"),
            "Incidencias": st.column_config.TextColumn("Incidencias", width="small"),
        },
    )
    rows = list(getattr(event.selection, "rows", []) or [])
    if rows:
        picked = ids[rows[0]]
        if picked and picked != str(st.session_state.get("selected_contact_id", "") or ""):
            _clear_modal_flags()
            st.session_state["selected_contact_id"] = picked
            st.rerun()

@st.dialog("Nuevo contacto")
def _create_contact_dialog(df: pd.DataFrame) -> None:
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
    confirm_clicked = col_confirm.button("Confirmar", type="primary", width="stretch", key="btn_save_create_contact")
    cancel_clicked = col_cancel.button("Cancelar", width="stretch", key="cancel_create_contact_dialog")

    if cancel_clicked:
        _new_contact_flow_cancel()
        st.rerun()

    if not confirm_clicked:
        return
    nombre_val = str(st.session_state.get("dialog_new_contact_nombre", "")).strip()
    if not nombre_val:
        st.error("Introduce un nombre para el contacto.")
        return
    exact_match, similars = _find_similar_contact_names(df, nombre_val)
    if exact_match:
        st.error("Ya existe este contacto.")
        return
    require_second = bool(st.session_state.get(NEW_CONTACT_REQUIRE_SECOND_CONFIRM_KEY, False))
    if similars and not require_second:
        st.session_state[NEW_CONTACT_SIMILAR_CANDIDATES_KEY] = similars
        st.session_state[NEW_CONTACT_REQUIRE_SECOND_CONFIRM_KEY] = True
        st.rerun(scope="fragment")
    try:
        with st.spinner("Creando nuevo contacto..."):
            new_df, new_contact_id, verify = create_empty_contact(
                df,
                sheets_service(),
                nombre=nombre_val,
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
        st.error(
            "No se pudo crear el contacto de forma consistente. "
            "Comprueba conexión/cuota y vuelve a confirmar. "
            f"Detalle: {exc}"
        )

def _log_contact_save_actions(
    original: dict[str, str],
    values: dict[str, str],
    actor: str,
) -> None:
    """Reserved for future audit; seguimiento comercial ya no se registra desde la ficha Contactos."""
    _ = (original, values, actor)

@st.dialog("Eliminar contacto")
def _delete_contact_dialog(contact_id: str, nombre: str) -> None:
    st.warning(
        f"**Vas a eliminar permanentemente** a «**{html.escape(nombre)}**» (`{html.escape(contact_id)}`). "
        "Se borrarán la fila en **Contactos**, todas las filas de histórico ligadas a este id y las entradas en "
        "**Acciones**. **No se puede deshacer.**"
    )
    c_yes, c_no = st.columns(2)
    if c_yes.button("Eliminar definitivamente", type="primary", width="stretch", key="btn_confirm_delete_contact"):
        try:
            with st.spinner("Eliminando en Google Sheets…"):
                delete_contact_and_related_data(sheets_service(), contact_id)
            clear_all_cache()
            bump_contacts_cache()
            bump_history_cache()
            _clear_delete_target()
            st.session_state[CONTACTS_DELETE_SUCCESS_KEY] = "Contacto y datos relacionados eliminados."
            st.session_state["selected_contact_id"] = ""
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo eliminar el contacto: {exc}")
    if c_no.button("Cancelar", width="stretch", key="btn_cancel_delete_contact"):
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
    open_tasks_count, next_task = next_open_tarea(hs.rows_for_contact("tareas", contact_id))
    acciones_df = load_acciones_cached(st.session_state.get("history_cache_version", 0))
    enriched = enrich_contacts_with_proxima(
        pd.DataFrame([contact]),
        acciones_df,
    )
    header_contact = enriched.iloc[0].fillna("").astype(str).to_dict() if not enriched.empty else contact
    last_contact = latest_commercial_contact_row(acciones_df, contact_id)

    bar = st.columns([0.76, 0.24], gap="small")
    with bar[1]:
        if st.button("Cerrar ficha", key=f"close_ficha_{contact_id}", width="stretch", icon=":material/close:"):
            _clear_contact_overlay_state()
            st.session_state["selected_contact_id"] = ""
            st.session_state["_contacts_last_selected_id"] = ""
            st.rerun()

    show_flags = str(contact.get("tipo_relacion", "") or "").strip() in TIPO_RELACION_BOARD
    render_contact_detail_header(
        contact=header_contact,
        contact_id=contact_id,
        subscription_status=subscription_status,
        open_incidents=open_incidents,
        last_contact=last_contact,
        open_tasks_count=open_tasks_count,
        next_task=next_task,
        with_flags=show_flags,
    )

    df = _render_ficha_board_flags(df, contact)

    mode_key = f"contact_detail_view_mode_{contact_id}"
    if st.session_state.get(mode_key) not in _DETAIL_VIEW_OPTIONS:
        st.session_state[mode_key] = "Datos"
    view_mode = st.radio(
        "Vista de ficha",
        _DETAIL_VIEW_OPTIONS,
        horizontal=True,
        key=mode_key,
        label_visibility="collapsed",
    )
    st.divider()
    if view_mode == "Datos":
        updated = _render_contact_form(df, row_idx, contact)
    elif view_mode == "Históricos":
        updated = None
        _render_history_kind_section(contact, "seguimiento_comercial")
        _render_history_kind_section(contact, "tareas")
        _render_history_kind_section(contact, "notas")
        for kind in ("sensores", "campanas", "suscripciones", "incidencias"):
            _render_history_kind_section(contact, kind)
        _maybe_render_sensor_close_location_modal(contact)
    else:
        updated = None
        render_contact_timeline_block(contact_id)
    _maybe_render_add_history_modal(contact)
    _maybe_render_edit_history_modal(contact)
    _maybe_render_riego_campanas_modal(contact)
    return updated if updated is not None else df


def _render_ficha_board_flags(df: pd.DataFrame, contact: dict[str, str]) -> pd.DataFrame:
    """Visto hoy / Umbrales / Suelo seco bajo los chips del header."""
    tipo = str(contact.get("tipo_relacion", "") or "").strip()
    if tipo not in TIPO_RELACION_BOARD:
        return df

    cid = str(contact.get("contact_id", "") or "")
    cid_safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in cid)
    cache_ver = int(st.session_state.get("contacts_cache_version", 0))
    key_suffix = f"{cid_safe}_{cache_ver}"

    visto_hoy = is_visto_hoy(contact.get("visto_cliente_fecha", ""))
    umbrales_on = is_sheet_true(contact.get("umbrales_activadas", ""))
    suelo_on = is_sheet_true(contact.get("suelo_seco", ""))

    visto_key = f"ficha_visto_{key_suffix}"
    umbrales_key = f"ficha_umbrales_{key_suffix}"
    suelo_key = f"ficha_suelo_{key_suffix}"

    if visto_key not in st.session_state:
        st.session_state[visto_key] = visto_hoy
    if umbrales_key not in st.session_state:
        st.session_state[umbrales_key] = umbrales_on
    if suelo_key not in st.session_state:
        st.session_state[suelo_key] = suelo_on

    c1, c2, c3 = st.columns(3, gap="small")
    with c1:
        st.markdown('<span class="sanzar-flags-marker" hidden></span>', unsafe_allow_html=True)
        visto = st.checkbox("Visto hoy", key=visto_key)
    with c2:
        umbrales = st.toggle("Umbrales activadas", key=umbrales_key)
    with c3:
        suelo = st.toggle("Suelo seco", key=suelo_key)

    if visto != visto_hoy:
        return autosave_contact_fields(
            df,
            contact_id=cid,
            updates=values_for_visto_toggle(checked=visto),
        )
    if umbrales != umbrales_on:
        return autosave_contact_fields(
            df,
            contact_id=cid,
            updates=values_for_flag("umbrales_activadas", checked=umbrales),
        )
    if suelo != suelo_on:
        return autosave_contact_fields(
            df,
            contact_id=cid,
            updates=values_for_flag("suelo_seco", checked=suelo),
        )
    return df


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
            [
                "estado",
                "fecha_estado",
                "razon_perdida",
                "valor",
                "responsable_cliente",
                "tipo_relacion",
                "no_recibir_emails",
            ],
        ),
        ("Operativa y suscripción", ["cuenta_usuario", "digital_maps", "iot_module", "sowing_module", "link_carpeta_cliente"]),
    ]

    with st.form(f"contact_form_{contact['contact_id']}"):
        values: dict[str, str] = {}
        values["contact_id"] = contact.get("contact_id", "")
        col_left, col_right = st.columns(2, gap="large")
        with col_left:
            _render_form_sections(values, contact, sections_left, section_key="left")
        with col_right:
            _render_form_sections(values, contact, sections_right, section_key="right")
        st.caption("Los cambios no se aplican hasta pulsar **Guardar ficha**.")
        submitted_save = st.form_submit_button(
            "Guardar ficha",
            type="primary",
            width="stretch",
            key="btn_save_contact_ficha",
        )

    cid = str(contact.get("contact_id", "") or "")
    nombre_ficha = str(contact.get("nombre", "") or "").strip() or "(sin nombre)"

    if submitted_save:
        error = validate_contact_date_fields(values)
        if error:
            st.error(error)
            return None
        # Avisos no bloqueantes (correo/teléfono): se muestran como toast pero
        # NO impiden guardar; puede haber datos a medias a propósito.
        for warning in contact_soft_warnings(values):
            st.toast(warning, icon="⚠️")
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

    st.divider()
    _render_contact_ficha_export(contact)
    st.divider()
    danger_cols = st.columns([0.66, 0.34], gap="small", vertical_alignment="center")
    danger_cols[0].caption("Eliminar borra la ficha y todos sus históricos (acciones, sensores, campañas, suscripciones e incidencias).")
    if danger_cols[1].button(
        "Eliminar contacto…",
        key="btn_destruct_contact_ficha",
        width="stretch",
        icon=":material/delete:",
    ):
        _delete_contact_dialog(cid, nombre_ficha)
    return None


CONTACT_FICHA_EXPORT_PREFIX = "contact_ficha_export"


def _render_contact_ficha_export(contact: dict[str, str]) -> None:
    """Caption + botón Exportar; al pulsar genera PDF/Excel y muestra downloads."""
    cid = str(contact.get("contact_id", "") or "").strip()
    if not cid:
        return
    xlsx_key = f"{CONTACT_FICHA_EXPORT_PREFIX}_xlsx_{cid}"
    pdf_key = f"{CONTACT_FICHA_EXPORT_PREFIX}_pdf_{cid}"
    xlsx_name_key = f"{CONTACT_FICHA_EXPORT_PREFIX}_xlsx_name_{cid}"
    pdf_name_key = f"{CONTACT_FICHA_EXPORT_PREFIX}_pdf_name_{cid}"

    export_cols = st.columns([0.66, 0.34], gap="small", vertical_alignment="center")
    export_cols[0].caption(
        "Exporta los detalles de la ficha en PDF y en Excel "
        "(ficha del cliente + seguimiento, tareas, notas, sensores, campañas, suscripciones e incidencias)."
    )
    if export_cols[1].button(
        "Exportar datos del contacto",
        key=f"btn_export_contact_ficha_{cid}",
        width="stretch",
        icon=":material/download:",
        type="primary",
    ):
        try:
            histories = collect_histories_for_contact(history_service(), cid)
            xlsx_bytes, xlsx_name = build_contact_ficha_xlsx_bytes(contact, histories)
            pdf_bytes, pdf_name = build_contact_ficha_pdf_bytes(contact, histories)
            st.session_state[xlsx_key] = xlsx_bytes
            st.session_state[pdf_key] = pdf_bytes
            st.session_state[xlsx_name_key] = xlsx_name
            st.session_state[pdf_name_key] = pdf_name
            st.toast("Exportación lista: descarga PDF y Excel abajo.", icon="✅")
        except Exception as exc:
            st.error(f"No se pudo generar la exportación: {exc}")

    xlsx_bytes = st.session_state.get(xlsx_key)
    pdf_bytes = st.session_state.get(pdf_key)
    if xlsx_bytes is None and pdf_bytes is None:
        return

    dl_cols = st.columns(2, gap="small")
    if xlsx_bytes is not None:
        dl_cols[0].download_button(
            "Descargar Excel",
            data=xlsx_bytes,
            file_name=str(st.session_state.get(xlsx_name_key) or "contacto.xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_contact_ficha_xlsx_{cid}",
            width="stretch",
            icon=":material/table:",
        )
    if pdf_bytes is not None:
        dl_cols[1].download_button(
            "Descargar PDF",
            data=pdf_bytes,
            file_name=str(st.session_state.get(pdf_name_key) or "contacto.pdf"),
            mime="application/pdf",
            key=f"dl_contact_ficha_pdf_{cid}",
            width="stretch",
            icon=":material/picture_as_pdf:",
        )

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
            # Un campo por fila: inputs anchos y selects legibles sin truncar.
            for column in columns:
                values[column] = _render_contact_field_input(
                    column,
                    contact.get(column, ""),
                    key=f"contact_{contact.get('contact_id', 'new')}_{section_key}_{column}",
                )

def _persona_proxima_accion_filter_options(df: pd.DataFrame) -> list[str]:
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    extras: list[str] = []
    if not df.empty and "persona_proxima_accion" in df.columns:
        extras = [
            x
            for x in df["persona_proxima_accion"].fillna("").astype(str).str.strip().unique()
            if x
        ]
    return person_select_options(users, extra=extras)


def _render_next_action_strip(df: pd.DataFrame) -> None:
    if st.session_state.get("dash_bucket") not in _BUCKET_KEYS:
        st.session_state["dash_bucket"] = None

    st.markdown("##### Filtros")

    persona_opts = _persona_proxima_accion_filter_options(df)
    estado_opts = [""] + list(CONTACT_ESTADO_OPCIONES)
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    responsable_extras: list[str] = []
    if not df.empty and "responsable_cliente" in df.columns:
        responsable_extras = [
            x
            for x in df["responsable_cliente"].fillna("").astype(str).str.strip().unique()
            if x
        ]
    responsable_opts = person_select_options(users, extra=responsable_extras)    # Si el valor restaurado ya no existe entre las opciones, descartarlo antes
    # de instanciar el widget (evita excepciones de Streamlit).
    for key, opts in (
        (DASH_PERSONA_PROXIMA_ACCION_KEY, persona_opts),
        (DASH_ESTADO_FILTER_KEY, estado_opts),
        (DASH_RESPONSABLE_FILTER_KEY, responsable_opts),
    ):
        if key in st.session_state and st.session_state[key] not in opts:
            st.session_state[key] = ""

    select_cols = st.columns(3, gap="small")
    select_cols[0].selectbox(
        "Persona próxima acción",
        options=persona_opts,
        format_func=lambda v: "Todas" if not v else v,
        key=DASH_PERSONA_PROXIMA_ACCION_KEY,
    )
    select_cols[1].selectbox(
        "Estado",
        options=estado_opts,
        format_func=lambda v: "Todos" if not v else v,
        key=DASH_ESTADO_FILTER_KEY,
    )
    select_cols[2].selectbox(
        "Responsable del cliente",
        options=responsable_opts,
        format_func=lambda v: "Todos" if not v else v,
        key=DASH_RESPONSABLE_FILTER_KEY,
    )

    persona_proxima = str(st.session_state.get(DASH_PERSONA_PROXIMA_ACCION_KEY, "") or "")
    scoped = filter_by_persona_proxima_accion(df, persona_proxima)
    dash_responsable = str(st.session_state.get(DASH_RESPONSABLE_FILTER_KEY, "") or "")
    scoped = filter_by_responsable_cliente(scoped, dash_responsable)
    dash_estado = str(st.session_state.get(DASH_ESTADO_FILTER_KEY, "") or "")
    scoped = filter_by_contact_estado(scoped, dash_estado)
    counts = next_action_bucket_counts(scoped)

    st.segmented_control(
        "Próxima acción",
        options=_BUCKET_KEYS,
        format_func=lambda k: f"{_BUCKET_LABELS[k]} · {counts[k]}",
        selection_mode="single",
        key="dash_bucket",
        on_change=_clear_modal_flags,
        help="Filtra por la fecha de la próxima acción. Vuelve a pulsar para quitar el filtro.",
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
        opts = person_select_options(
            load_users_cached(st.session_state.get("users_cache_version", 0)),
            current=value,
        )
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
    if column == "no_recibir_emails":
        opts = [NO_RECIBIR_EMAILS_NO, NO_RECIBIR_EMAILS_SI]
        normalized = (value or "").strip().lower()
        if normalized in {"si", "sí", "yes", "true", "1"}:
            current = NO_RECIBIR_EMAILS_SI
        else:
            current = NO_RECIBIR_EMAILS_NO
        return st.selectbox(
            "No recibir emails",
            opts,
            index=opts.index(current),
            key=key,
            help="Si = no enviar correo individual ni newsletter a este contacto.",
        )
    if column == "link_carpeta_cliente":
        return st.text_input(
            "Link carpeta cliente",
            value=value,
            key=key,
            placeholder="https://…",
            help="URL de la carpeta del cliente (Drive u otro).",
        )
    if column == "responsable_cliente":
        opts = person_select_options(
            load_users_cached(st.session_state.get("users_cache_version", 0)),
            current=value,
        )
        return st.selectbox(
            "Responsable del cliente",
            opts,
            index=opts.index(value) if value in opts else 0,
            key=key,
        )
    if column in {"detalle", "otros_contactos", "razon_perdida"}:
        return st.text_area(label, value=value, height=80, key=key)
    return st.text_input(label, value=value, key=key)
