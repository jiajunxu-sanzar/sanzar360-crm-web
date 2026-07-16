"""Dashboard de seguimiento comercial (hoja Acciones)."""

from __future__ import annotations

import streamlit as st

from app.cache import load_acciones_cached, load_users_cached
from ui.components.page_header import render_page_header
from app.telemetry import timed
from services.actions_dashboard_stats import (
    commercial_team_roster,
    merge_person_canal_week_with_roster,
    person_performance_averages,
    person_performance_last_months,
    success_rate_by_canal,
    summarize_commercial_week,
    summarize_person_canal_week,
)
from ui.components.actions_dashboard_cards import (
    render_canal_success_cards,
    render_person_averages_dashboard,
    render_person_cards_grid,
    render_person_performance_snapshots,
    render_week_kpi_cards,
    render_week_navigation,
)

ACCIONES_VIEW_KEY = "acciones_view"
ACCIONES_PERSON_KEY = "acciones_selected_person"
ACCIONES_WEEK_OFFSET_KEY = "acciones_week_offset"


def _init_acciones_session_state() -> None:
    if ACCIONES_VIEW_KEY not in st.session_state:
        st.session_state[ACCIONES_VIEW_KEY] = "team"
    if ACCIONES_WEEK_OFFSET_KEY not in st.session_state:
        st.session_state[ACCIONES_WEEK_OFFSET_KEY] = 0


def _render_team_view(df) -> None:
    week_offset = int(st.session_state.get(ACCIONES_WEEK_OFFSET_KEY, 0) or 0)
    summary = summarize_commercial_week(df, week_offset=week_offset)
    roster = commercial_team_roster(load_users_cached(st.session_state.get("users_cache_version", 0)))
    people = merge_person_canal_week_with_roster(
        summarize_person_canal_week(df, summary.week_start, summary.week_end),
        roster,
    )

    render_week_navigation(
        summary.week_start,
        summary.week_end,
        week_offset=week_offset,
        prev_key="acciones_week_prev",
        next_key="acciones_week_next",
    )
    render_week_kpi_cards(summary.total_contacts, summary.exitosos, summary.fallidos)

    st.subheader("Por persona")
    render_person_cards_grid(people, key_prefix=f"acciones_w{week_offset}")

    st.divider()
    st.subheader("Tasa de éxito por canal (histórico)")
    render_canal_success_cards(success_rate_by_canal(df))


def _render_person_view(df) -> None:
    persona = str(st.session_state.get(ACCIONES_PERSON_KEY, "") or "").strip()
    if not persona:
        st.session_state[ACCIONES_VIEW_KEY] = "team"
        st.rerun()

    if st.button("← Volver al equipo", key="acciones_back_team"):
        st.session_state[ACCIONES_VIEW_KEY] = "team"
        st.session_state.pop(ACCIONES_PERSON_KEY, None)
        st.rerun()

    st.markdown(f"### Detalle comercial · {persona}")
    st.caption("Últimos 3 meses · resumen semanal de contactos, canales y resultados.")

    snapshots = person_performance_last_months(df, persona, months=3)
    averages = person_performance_averages(snapshots)
    render_person_averages_dashboard(averages)
    st.divider()
    render_person_performance_snapshots(snapshots)


def render() -> None:
    render_page_header("Acciones")
    st.caption(
        "Seguimiento comercial por contacto (email, llamada, en persona). "
        "Una fila por touchpoint en la hoja Acciones."
    )
    _init_acciones_session_state()

    with timed("actions_dashboard.render"):
        df = load_acciones_cached(st.session_state.get("history_cache_version", 0))

    if st.session_state.get(ACCIONES_VIEW_KEY) == "person":
        _render_person_view(df)
        return

    _render_team_view(df)
