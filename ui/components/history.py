from __future__ import annotations

import pandas as pd
import streamlit as st

from services.history_service import HISTORY_SPECS
from ui.components.tables import render_dataframe, _selected_row_positions

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

    selectable = bool((contact_id or "").strip())
    tbl_key = f"hist_table_select_{suffix}"

    try:
        if selectable:
            event = st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                height=300,
                key=tbl_key,
                on_select="rerun",
                selection_mode="single-row",
            )
            return _event_first_row_index(event, len(df))
        render_dataframe(df, height=300)
    except Exception:
        # Streamlit sin API de selección o fallo puntual → tabla estática.
        render_dataframe(df, height=300)

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
