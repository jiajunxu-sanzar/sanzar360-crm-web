from __future__ import annotations

import pandas as pd
import streamlit as st

from app.state import select_contact
from services.map_service import build_contacts_map
from ui.components.map import render_folium_map


def render(df: pd.DataFrame) -> None:
    st.title("Mapa")
    st.caption(
        "Ubicación por prioridad: `coordenadas` (`lat, lon`), si faltan `municipio`, y si falta `provincia`."
    )
    if df.empty:
        st.info("No hay contactos para pintar.")
        return

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
            use_container_width=True,
            disabled=not bool(selected_id),
        ):
            select_contact(selected_id)
            st.rerun()

    event = render_folium_map(build_contacts_map(df))
    tooltip = str((event or {}).get("last_object_clicked_tooltip", "") or "")
    if tooltip.startswith("cid::"):
        parts = tooltip.split("::", 2)
        contact_id = parts[1].strip() if len(parts) > 1 else ""
        contact_name = parts[2].strip() if len(parts) > 2 else contact_id
        if contact_id:
            st.session_state["map_selected_contact_id"] = contact_id
            st.session_state["map_selected_contact_name"] = contact_name
            st.rerun()
