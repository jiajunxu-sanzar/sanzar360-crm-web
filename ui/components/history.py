from __future__ import annotations

import pandas as pd
import streamlit as st

from services.history_service import HISTORY_SPECS
from ui.components.tables import filter_dataframe, render_dataframe, _selected_row_positions

PRIMARY_COLUMNS: dict[str, list[str]] = {
    "sensores": [
        "fecha_inicio",
        "fecha_fin",
        "estado_sensor",
        "sensor_serial_number",
        "cantidad_sensores",
        "tipo_operacion",
        "red",
        "aws_user_id",
    ],
    "campanas": [
        "nombre_campana",
        "fecha_campana_inicio",
        "fecha_campana_fin",
        "cultivo",
        "parcela",
        "tipo_suelo",
    ],
    "suscripciones": [
        "fecha_pago",
        "cantidad_pago",
        "moneda",
        "suscripcion_fecha_inicio",
        "suscripcion_fecha_fin",
        "estado_suscripcion",
    ],
    "incidencias": [
        "fecha_apertura",
        "fecha_cierre",
        "estado",
        "prioridad",
        "tipo_incidencia",
        "sensor_serial_number",
        "nombre_campana",
    ],
}


def history_table_state_suffix(contact_id: str, kind: str) -> str:
    return f"{contact_id}_{kind}"


def history_table_selection_key(contact_id: str, kind: str) -> str:
    suffix = history_table_state_suffix(contact_id, kind)
    version = st.session_state.get(f"hist_table_version_{suffix}", 0)
    return f"hist_table_select_{suffix}_v{version}"


def history_table_search_key(contact_id: str, kind: str) -> str:
    suffix = history_table_state_suffix(contact_id, kind)
    return f"hist_table_search_{suffix}"


def clear_history_table_selection(contact_id: str, kind: str) -> None:
    """Drop dataframe selection state and bump widget version to force deselect."""
    suffix = history_table_state_suffix(contact_id, kind)
    for key in list(st.session_state.keys()):
        if key.startswith(f"hist_table_select_{suffix}"):
            st.session_state.pop(key, None)
    version_key = f"hist_table_version_{suffix}"
    st.session_state[version_key] = int(st.session_state.get(version_key, 0) or 0) + 1


def render_history_summary(kind: str, rows: list[dict[str, str]]) -> None:
    spec = HISTORY_SPECS[kind]
    latest = rows[0] if rows else None
    st.caption(f"{spec.title}: {len(rows)} registros")
    if not latest:
        st.info("Sin histórico todavía.")
        return
    cols = st.columns(min(4, max(1, len(spec.summary_columns))))
    for idx, column in enumerate(spec.summary_columns[:4]):
        cols[idx % len(cols)].metric(column, latest.get(column, "") or "Sin dato")


def render_history_table(
    kind: str,
    rows: list[dict[str, str]],
    *,
    technical: bool = False,
    contact_id: str = "",
    selection_key_suffix: str = "",
) -> int | None:
    """Returns selected row position in ``rows`` when selectable; otherwise None."""
    df = pd.DataFrame(rows)
    _ = technical
    if df.empty:
        st.info("No hay datos para mostrar.")
        return None

    suffix = selection_key_suffix or f"{contact_id}_{kind}"
    _ = suffix
    selectable = bool((contact_id or "").strip())
    search_key = history_table_search_key(contact_id, kind) if selectable else f"hist_table_search_{kind}"
    search_query = st.text_input(
        "Buscar",
        placeholder="Filtrar registros…",
        key=search_key,
    )
    filtered = filter_dataframe(df, search_query, list(df.columns))
    if search_query.strip():
        if filtered.empty:
            st.info(f"No hay coincidencias para «{search_query.strip()}».")
            return None
        if len(filtered) < len(df):
            st.caption(f"Mostrando {len(filtered)} de {len(df)} registros")

    tbl_key = history_table_selection_key(contact_id, kind) if selectable else ""

    try:
        if selectable:
            event = st.dataframe(
                filtered,
                width="stretch",
                hide_index=True,
                height=300,
                key=tbl_key,
                on_select="rerun",
                selection_mode="single-row",
            )
            filtered_pos = _event_first_row_index(event, len(filtered))
            if filtered_pos is None:
                return None
            return int(filtered.index[filtered_pos])
        render_dataframe(filtered, height=300)
    except Exception:
        # Streamlit sin API de selección o fallo puntual → tabla estática.
        render_dataframe(filtered, height=300)

    return None


def _event_first_row_index(event: object | None, n_rows: int) -> int | None:
    positions = _selected_row_positions(event)
    if not positions:
        return None
    try:
        pos = int(positions[0])
    except (TypeError, ValueError):
        return None
    if pos < 0 or pos >= n_rows:
        return None
    return pos
