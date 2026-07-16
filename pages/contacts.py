from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from ui.components.page_header import render_page_header
from app.cache import (
    clear_all_cache,
    history_service,
    load_acciones_cached,
    load_contact_sensor_overview_cached,
    load_users_cached,
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
    PERSONA_COMERCIAL_OPCIONES,
    TIPO_RELACION_OPCIONES,
    VALOR_OPCIONES,
)
from services.contact_proxima_index import enrich_contacts_with_proxima, latest_commercial_contact_row
from services.contact_deletion import delete_contact_and_related_data
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
from services.sheet_date_format import validate_contact_date_fields
from ui.components.cards import chip
from ui.palette import contact_status_style
from ui.components.customer_timeline import render_contact_timeline_block
from ui.components.contact_detail_header import render_contact_detail_header
from ui.components.contact_overview_table import render_contact_overview_dialog_content
from ui.components.tables import filter_dataframe

from pages.contacts_common import (  # noqa: F401
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
)
from pages.contacts_inventory_sync import (  # noqa: F401
    _parse_ddmmyyyy,
    _extract_uc501_bundle,
    _extract_ug67_bundle,
    _extract_solenoide_sn,
    _extract_sim_sn,
    _extract_em500_sn,
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
            "",
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

def _contact_overview_list_dialog() -> None:
    render_contact_overview_dialog_content(_filtered_overview_display_df())

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
