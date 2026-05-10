"""Dashboard de acciones registradas (batch email y seguimiento comercial) por persona y semana."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.cache import load_activity_log_cached
from app.telemetry import timed
from services.actions_dashboard_stats import (
    COUNTED_ACTION_TYPES,
    personas_with_counted_actions,
    summarize_actions_current_week,
    weekly_breakdown_for_person,
)


@st.dialog("Detalle histórico por semana")
def _weekly_person_modal(persona: str, breakdown: pd.DataFrame) -> None:
    """Ventana modal: totales semanales (lunes–domingo) solo para esa persona."""
    st.markdown(f"**Persona:** {persona}")
    st.caption("Suma de *batch email* + *seguimiento comercial* por semana completa.")

    bd = breakdown
    if bd.empty:
        st.info("Sin acciones registradas de esos dos tipos para esta persona.")
        return

    show = bd.copy()
    show["Semana"] = show.apply(
        lambda r: f"{r['semana_desde']:%d/%m/%Y} – {r['semana_hasta']:%d/%m/%Y}",
        axis=1,
    )
    show = show.rename(
        columns={
            "batch_email": "Batch email",
            "seguimiento_comercial": "Seguimiento comercial",
            "total": "Total",
        }
    )
    cols = ["Semana", "Batch email", "Seguimiento comercial", "Total"]
    st.dataframe(show[cols], width="stretch", hide_index=True)

    long_df = bd.melt(
        id_vars=["semana_desde"],
        value_vars=["batch_email", "seguimiento_comercial"],
        var_name="tipo",
        value_name="count",
    )
    long_df["tipo"] = long_df["tipo"].map(
        {"batch_email": "Batch email", "seguimiento_comercial": "Seguimiento comercial"}
    )
    long_df["Semana desde"] = long_df["semana_desde"].apply(lambda d: d.strftime("%d/%m/%Y"))
    fig = px.bar(
        long_df.sort_values("semana_desde"),
        x="Semana desde",
        y="count",
        color="tipo",
        barmode="group",
        labels={"count": "Acciones"},
        title="Por semana",
    )
    st.plotly_chart(fig, use_container_width=True)


def render() -> None:
    st.title("Acciones")
    st.caption(
        "Acciones contabilizadas desde el log de Google Sheets: tipos "
        + ", ".join(f"**{t}**" for t in sorted(COUNTED_ACTION_TYPES))
        + ". Sólo aparecen personas con al menos una acción en la semana actual."
    )

    with timed("actions_dashboard.render"):
        df = load_activity_log_cached()
        summary = summarize_actions_current_week(df)

    ws, we = summary.week_start, summary.week_end
    st.info(
        f"**Semana actual (lunes–domingo):** del **{ws.strftime('%d/%m/%Y')}** al **{we.strftime('%d/%m/%Y')}**."
    )

    agg = summary.by_person
    if agg.empty:
        st.warning(
            "No hay registros de *batch email* ni *seguimiento comercial* en esa semana. "
            "Puedes abrir igualmente el **detalle por persona** abajo si hay histórico en otras semanas."
        )
    else:
        st.subheader("Por persona (esta semana)")
        st.dataframe(
            agg.rename(
                columns={
                    "persona": "Persona",
                    "batch_email": "Batch email",
                    "seguimiento_comercial": "Seguimiento comercial",
                    "total": "Total",
                }
            ),
            width="stretch",
            hide_index=True,
        )

        long_df = agg.melt(
            id_vars=["persona"],
            value_vars=["batch_email", "seguimiento_comercial"],
            var_name="tipo",
            value_name="count",
        )
        long_df["tipo"] = long_df["tipo"].map(
            {"batch_email": "Batch email", "seguimiento_comercial": "Seguimiento comercial"}
        )
        order = agg.sort_values("total", ascending=True)["persona"].astype(str).tolist()
        fig = px.bar(
            long_df,
            x="count",
            y="persona",
            color="tipo",
            orientation="h",
            labels={"count": "Acciones", "persona": ""},
            title="Esta semana — desglose por tipo",
        )
        fig.update_layout(
            barmode="stack",
            yaxis={"categoryorder": "array", "categoryarray": order},
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Detalle por persona (todas las semanas del log)")
    personas_opts = personas_with_counted_actions(df)
    if not personas_opts:
        st.info("No hay registros de *batch email* ni *seguimiento comercial* en el log.")
        return

    pcol1, pcol2 = st.columns([2, 1], gap="small")
    with pcol1:
        elegida = st.selectbox(
            "Persona",
            personas_opts,
            key="actions_dashboard_person_pick",
            help="Lista de todas las personas con al menos una acción *batch email* "
            "o *seguimiento comercial* registrada alguna vez.",
        )
    with pcol2:
        st.write("")
        if st.button(
            "Ver detalle…",
            width="stretch",
            type="primary",
            disabled=not bool(elegida),
            key="actions_dashboard_open_modal",
        ):
            bd = weekly_breakdown_for_person(df, persona_display=str(elegida))
            _weekly_person_modal(str(elegida), bd)
