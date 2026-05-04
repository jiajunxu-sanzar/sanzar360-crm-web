from __future__ import annotations

import pandas as pd
import streamlit as st

from app.cache import load_history_rows_cached
from app.state import select_contact
from app.telemetry import timed
from services.history_service import parse_sensor_asset_occurrences
from ui.components.asset_search import asset_occurrences_df


def render(_: pd.DataFrame) -> None:
    with timed("asset_search.render"):
        st.title("Buscador sensores/SIM")
        query = st.text_input("Buscar por serial, SIM, cliente, AWS user ID o asociación", key="asset_query")
        asset_type = st.selectbox("Tipo de activo", ["", "uc501", "teros10", "sim", "ug67", "em500", "em300", "uc512"])

        rows = load_history_rows_cached("sensores", st.session_state.get("history_cache_version", 0))
        occurrences = parse_sensor_asset_occurrences(rows)
        if asset_type:
            occurrences = [item for item in occurrences if item.asset.asset_type.lower() == asset_type.lower()]
        if (query or "").strip():
            q = query.strip().lower()
            occurrences = [
                item
                for item in occurrences
                if q in item.asset.serial.lower()
                or q in item.asset.asset_type.lower()
                or q in item.nombre_cliente.lower()
                or q in item.contact_id.lower()
                or q in item.aws_user_id.lower()
                or q in item.associated_with.lower()
            ]
        result_df = asset_occurrences_df(occurrences)
        available = int((result_df.get("disponibilidad", pd.Series(dtype=str)) == "Disponible").sum()) if not result_df.empty else 0
        in_use = int((result_df.get("disponibilidad", pd.Series(dtype=str)) == "En uso").sum()) if not result_df.empty else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Activos encontrados", len(result_df))
        c2.metric("En uso", in_use)
        c3.metric("Disponibles", available)

        if result_df.empty:
            st.info("No se encontraron activos.")
            return

        event = st.dataframe(
            result_df,
            use_container_width=True,
            hide_index=True,
            height=420,
            key="asset_search_table",
            on_select="rerun",
            selection_mode="single-row",
        )

        selected_rows = (
            event.selection.rows
            if event and hasattr(event, "selection") and event.selection
            else []
        )
        if selected_rows:
            row_idx = selected_rows[0]
            contact_id = str(result_df.iloc[row_idx].get("contact_id", "") or "")
            nombre = str(result_df.iloc[row_idx].get("nombre_cliente", "") or "")
            label = f"{nombre} ({contact_id})" if nombre else contact_id
            st.caption(f"Fila seleccionada: **{label}**")
            if contact_id and st.button(
                f"Abrir ficha de {label}",
                key="asset_search_open_contact",
                type="primary",
                use_container_width=True,
            ):
                select_contact(contact_id)
                st.rerun()
        else:
            st.caption("Selecciona una fila de la tabla para abrir la ficha del cliente.")
