from __future__ import annotations

import pandas as pd
import streamlit as st

from app.cache import load_acciones_cached
from app.navigation import page_menu_title
from app.telemetry import timed
from services.contact_proxima_index import enrich_contacts_with_proxima
from services.dashboard_stats import funnel_counts, kpi_summary, value_counts
from ui.components.dashboard_cards import (
    render_dashboard_kpi_row,
    render_funnel_cards,
    render_ranked_bar_cards,
)


def render(df: pd.DataFrame) -> None:
    st.title(page_menu_title("Dashboard"))
    st.caption("Resumen del CRM: contactos, embudo comercial y distribución geográfica y agrícola.")

    acciones_df = load_acciones_cached(st.session_state.get("history_cache_version", 0))
    df = enrich_contacts_with_proxima(df, acciones_df)
    with timed("dashboard.render"):
        metrics = kpi_summary(df)

    render_dashboard_kpi_row(metrics)

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Embudo comercial")
        render_funnel_cards(funnel_counts(df), metrics["contactos"])
    with right:
        st.subheader("Top provincias")
        render_ranked_bar_cards(
            value_counts(df, "provincia", top=8),
            empty_msg="No hay provincias disponibles.",
        )

    st.subheader("Top cultivos")
    render_ranked_bar_cards(
        value_counts(df, "cultivos", top=12),
        empty_msg="No hay cultivos disponibles.",
    )

    with st.expander("Telemetría (baseline)"):
        events = st.session_state.get("telemetry_events", [])
        if not events:
            st.caption("No hay eventos aún.")
        else:
            telemetry_df = pd.DataFrame(events).tail(100)
            st.dataframe(telemetry_df, width="stretch", hide_index=True)
