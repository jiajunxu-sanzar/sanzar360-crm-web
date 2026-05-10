from __future__ import annotations

import pandas as pd
import streamlit as st


def render_dataframe(df: pd.DataFrame, *, columns: list[str] | None = None, height: int = 360) -> None:
    if df.empty:
        st.info("No hay datos para mostrar.")
        return
    shown = df.copy()
    if columns:
        existing = [column for column in columns if column in shown.columns]
        shown = shown[existing]
    st.dataframe(shown, width="stretch", hide_index=True, height=height)


def render_selectable_dataframe(
    df: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    key: str,
    height: int = 360,
) -> int | None:
    """Renderiza una tabla Streamlit y devuelve la posición seleccionada en ``df``."""
    if df.empty:
        st.info("No hay datos para mostrar.")
        return None

    shown = df.copy()
    if columns:
        existing = [column for column in columns if column in shown.columns]
        shown = shown[existing]

    try:
        event = st.dataframe(
            shown,
            width="stretch",
            hide_index=True,
            height=height,
            key=key,
            on_select="rerun",
            selection_mode="single-row",
        )
    except TypeError:
        st.dataframe(shown, width="stretch", hide_index=True, height=height, key=key)
        st.caption("Actualiza Streamlit si quieres selección directa de filas en la tabla.")
        return None

    selected_rows = _selected_row_positions(event)
    if not selected_rows:
        return None
    row_position = selected_rows[0]
    if row_position < 0 or row_position >= len(df):
        return None
    return int(row_position)


def _selected_row_positions(event: object) -> list[int]:
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if selection is None:
        return []
    rows = getattr(selection, "rows", None)
    if rows is None and isinstance(selection, dict):
        rows = selection.get("rows")
    return list(rows or [])


def filter_dataframe(df: pd.DataFrame, query: str, columns: list[str]) -> pd.DataFrame:
    if df.empty or not (query or "").strip():
        return df
    query = query.strip().lower()
    mask = pd.Series(False, index=df.index)
    for column in columns:
        if column in df.columns:
            mask = mask | df[column].fillna("").astype(str).str.lower().str.contains(query, na=False)
    return df[mask]
