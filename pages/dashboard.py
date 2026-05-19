from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.navigation import page_menu_title
from app.telemetry import timed
from services.dashboard_stats import funnel_counts, kpi_summary, value_counts
from ui.components.cards import metric_card


def render(df: pd.DataFrame) -> None:
    st.title(page_menu_title("Dashboard"))
    with timed("dashboard.render"):
        metrics = kpi_summary(df)
    cols = st.columns(4)
    with cols[0]:
        metric_card("Contactos", metrics["contactos"], "Total cargado desde Google Sheets")
    with cols[1]:
        metric_card("Clientes", metrics["clientes"], "Estado = Cliente")
    with cols[2]:
        metric_card("Próximas acciones", metrics["proximas_acciones"], "Contactos con fecha prevista")
    with cols[3]:
        metric_card("Sin estado", metrics["sin_estado"], "Requieren limpieza")

    left, right = st.columns(2)
    with left:
        st.subheader("Embudo comercial")
        funnel = funnel_counts(df)
        if funnel:
            chart_df = pd.DataFrame({"estado": list(funnel.keys()), "contactos": list(funnel.values())})
            st.plotly_chart(px.bar(chart_df, x="estado", y="contactos"), use_container_width=True)
        else:
            st.info("No hay estados disponibles.")
    with right:
        st.subheader("Top provincias")
        provinces = value_counts(df, "provincia", top=8)
        if provinces:
            chart_df = pd.DataFrame({"provincia": list(provinces.keys()), "contactos": list(provinces.values())})
            st.plotly_chart(px.bar(chart_df, x="contactos", y="provincia", orientation="h"), use_container_width=True)
        else:
            st.info("No hay provincias disponibles.")

    st.subheader("Top cultivos")
    crops = value_counts(df, "cultivos", top=12)
    if crops:
        crop_df = pd.DataFrame({"cultivo": list(crops.keys()), "contactos": list(crops.values())})
        st.dataframe(crop_df, hide_index=True, width="stretch")
    else:
        st.info("No hay cultivos disponibles.")

    with st.expander("Telemetría (baseline)"):
        events = st.session_state.get("telemetry_events", [])
        if not events:
            st.caption("No hay eventos aún.")
        else:
            telemetry_df = pd.DataFrame(events).tail(100)
            st.dataframe(telemetry_df, width="stretch", hide_index=True)
