"""Dashboard de seguimiento comercial (hoja Acciones)."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from app.cache import load_acciones_cached
from app.navigation import page_menu_title
from app.telemetry import timed
from services.actions_dashboard_stats import (
    contacts_by_hour,
    success_rate_by_canal,
    summarize_commercial_week,
)


def render() -> None:
    st.title(page_menu_title("Acciones"))
    st.caption("Seguimiento comercial por contacto (email, llamada, en persona). Una fila por touchpoint en la hoja Acciones.")

    with timed("actions_dashboard.render"):
        df = load_acciones_cached(st.session_state.get("history_cache_version", 0))
        summary = summarize_commercial_week(df)

    ws, we = summary.week_start, summary.week_end
    st.info(
        f"**Semana actual (lunes–domingo):** del **{ws.strftime('%d/%m/%Y')}** al **{we.strftime('%d/%m/%Y')}**."
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Contactos esta semana", summary.total_contacts)
    m2.metric("Exitosos", summary.exitosos)
    m3.metric("Fallidos", summary.fallidos)

    if summary.by_person.empty:
        st.warning("No hay registros de seguimiento en la semana actual.")
    else:
        st.subheader("Por persona (esta semana)")
        show = summary.by_person.rename(
            columns={
                "persona_contacto": "Persona",
                "total": "Total",
                "exitosos": "Exitosos",
                "fallidos": "Fallidos",
            }
        )
        st.dataframe(show, width="stretch", hide_index=True)

    st.divider()
    st.subheader("Tasa de éxito por canal (histórico)")
    canal_df = success_rate_by_canal(df)
    if canal_df.empty:
        st.info("Sin datos de canal todavía.")
    else:
        st.dataframe(
            canal_df.rename(
                columns={
                    "canal_contacto": "Canal",
                    "total": "Total",
                    "exitosos": "Exitosos",
                    "tasa_exito": "Tasa éxito %",
                }
            ),
            width="stretch",
            hide_index=True,
        )
        fig = px.bar(canal_df, x="canal_contacto", y="tasa_exito", title="Tasa de éxito por canal (%)")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Contactos por hora del día (histórico)")
    hour_df = contacts_by_hour(df)
    if hour_df.empty:
        st.info("Sin horas registradas todavía.")
    else:
        fig2 = px.bar(hour_df, x="hora", y="total", title="Volumen por hora (HH)")
        st.plotly_chart(fig2, use_container_width=True)
