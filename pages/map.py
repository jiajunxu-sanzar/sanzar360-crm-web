from __future__ import annotations

import pandas as pd
import streamlit as st

from app.state import select_contact
from services.map_service import build_contacts_map, resolve_row_coordinates
from ui.components.map import render_folium_map

MAP_SHOW_LOST_KEY = "map.show_lost"


def render(df: pd.DataFrame) -> None:
    st.title("Mapa")
    st.caption(
        "Ubicación por prioridad: `coordenadas` (`lat, lon`), si faltan `municipio`, y si falta `provincia`."
    )
    if df.empty:
        st.info("No hay contactos para pintar.")
        return

    if MAP_SHOW_LOST_KEY not in st.session_state:
        st.session_state[MAP_SHOW_LOST_KEY] = True
    st.toggle("Mostrar perdidos", key=MAP_SHOW_LOST_KEY)

    records = df.fillna("").astype(str).to_dict("records")
    if not bool(st.session_state.get(MAP_SHOW_LOST_KEY, True)):
        records = [row for row in records if str(row.get("estado", "")).strip().lower() != "perdido"]

    visible_ids = {str(row.get("contact_id", "")).strip() for row in records}
    selected_id_state = str(st.session_state.get("map_selected_contact_id", "") or "")
    focus_id_state = str(st.session_state.get("map_focus_contact_id", "") or "")
    if selected_id_state and selected_id_state not in visible_ids:
        st.session_state.pop("map_selected_contact_id", None)
        st.session_state.pop("map_selected_contact_name", None)
    if focus_id_state and focus_id_state not in visible_ids:
        st.session_state.pop("map_focus_contact_id", None)

    options_by_label = {
        f"{row.get('nombre', '(sin nombre)')} ({row.get('contact_id', '')})": row
        for row in records
        if row.get("contact_id", "")
    }
    search_col, go_col = st.columns([0.8, 0.2], gap="small")
    selected_label = search_col.selectbox(
        "Buscar contacto",
        options=[""] + list(options_by_label.keys()),
        key="map_search_contact_label",
        help="Selecciona un contacto y pulsa 'Ir al mapa' para centrarlo.",
    )
    if go_col.button("Ir al mapa", width="stretch"):
        selected_row = options_by_label.get(selected_label, {})
        focus_contact_id = str(selected_row.get("contact_id", "") or "")
        focus_contact_name = str(selected_row.get("nombre", "") or focus_contact_id)
        coords = resolve_row_coordinates(selected_row) if selected_row else None
        if not focus_contact_id:
            st.warning("Selecciona un contacto para centrar el mapa.")
        elif not coords:
            st.warning("No se pudo resolver ubicación para ese contacto.")
        else:
            st.session_state["map_focus_contact_id"] = focus_contact_id
            st.session_state["map_selected_contact_id"] = focus_contact_id
            st.session_state["map_selected_contact_name"] = focus_contact_name
            st.rerun()

    selected_id = st.session_state.get("map_selected_contact_id", "")
    selected_name = st.session_state.get("map_selected_contact_name", selected_id)
    info_col, button_col = st.columns([0.72, 0.28], gap="small")
    with info_col:
        if selected_id:
            st.info(f"Usuario seleccionado: {selected_name}")
        else:
            st.caption("Selecciona un punto del mapa para habilitar Abrir ficha.")
    with button_col:
        if st.button(
            "Abrir ficha",
            key="map_open_contact_button",
            width="stretch",
            disabled=not bool(selected_id),
        ):
            select_contact(selected_id)
            st.rerun()

    focus_id = str(st.session_state.get("map_focus_contact_id", "") or "")
    focus_coords: tuple[float, float] | None = None
    if focus_id:
        focused = next((row for row in records if str(row.get("contact_id", "")) == focus_id), None)
        if focused:
            focus_coords = resolve_row_coordinates(focused)
    map_df = pd.DataFrame(records)
    event = render_folium_map(build_contacts_map(map_df, focus_coords=focus_coords))
    tooltip = str((event or {}).get("last_object_clicked_tooltip", "") or "")
    if tooltip.startswith("cid::"):
        parts = tooltip.split("::", 2)
        contact_id = parts[1].strip() if len(parts) > 1 else ""
        contact_name = parts[2].strip() if len(parts) > 2 else contact_id
        if contact_id:
            st.session_state["map_selected_contact_id"] = contact_id
            st.session_state["map_selected_contact_name"] = contact_name
            st.rerun()
