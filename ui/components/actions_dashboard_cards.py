"""Tarjetas visuales para el dashboard Acciones."""
from __future__ import annotations

import html
from datetime import date

import streamlit as st

from config.settings import CANAL_CONTACTO_OPCIONES
from services.actions_dashboard_stats import (
    CanalBreakdown,
    PersonCanalWeekStats,
    PersonPerformanceAverages,
    PersonWeekSnapshot,
)
from ui.components.cards import chip
from ui.palette import STATUS_DANGER, STATUS_INFO, STATUS_SUCCESS

CANAL_LABELS: dict[str, str] = {
    "email": "Email",
    "llamada": "Llamada",
    "en_persona": "En persona",
}

CANAL_ORDER: tuple[str, ...] = CANAL_CONTACTO_OPCIONES


def _esc(value: object) -> str:
    return html.escape(str(value or ""))


def _format_week_range(week_start: date, week_end: date) -> str:
    return f"{week_start.strftime('%d/%m/%Y')} – {week_end.strftime('%d/%m/%Y')}"


def _canal_label(canal: str) -> str:
    return CANAL_LABELS.get(canal, canal.replace("_", " ").capitalize())


def _render_canal_mini_grid(by_canal: dict[str, CanalBreakdown]) -> str:
    blocks: list[str] = []
    for canal in CANAL_ORDER:
        stats = by_canal.get(canal, CanalBreakdown())
        if stats.total == 0:
            continue
        blocks.append(
            f"""
<div class="sanzar-acciones-canal-item">
  <div class="sanzar-acciones-canal-item-label">{_esc(_canal_label(canal))}</div>
  <div class="sanzar-acciones-canal-item-stats">
    <span>{stats.total} acc.</span>
    <span class="sanzar-acciones-stat-ok">{stats.exitosos} exitosos</span>
    <span class="sanzar-acciones-stat-ko">{stats.fallidos} fallidos</span>
  </div>
</div>
"""
        )
    if not blocks:
        return '<p class="sanzar-muted">Sin acciones por canal esta semana.</p>'
    return f'<div class="sanzar-acciones-canal-grid">{"".join(blocks)}</div>'


def render_week_kpi_cards(total: int, exitosos: int, fallidos: int) -> None:
    cards = [
        ("sanzar-acciones-kpi", "Contactos esta semana", total),
        ("sanzar-acciones-kpi sanzar-acciones-kpi--success", "Exitosos", exitosos),
        ("sanzar-acciones-kpi sanzar-acciones-kpi--danger", "Fallidos", fallidos),
    ]
    cols = st.columns(3, gap="medium")
    for col, (css_class, label, value) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
<div class="{css_class}">
  <div class="sanzar-acciones-kpi-label">{_esc(label)}</div>
  <div class="sanzar-acciones-kpi-value">{value}</div>
</div>
""",
                unsafe_allow_html=True,
            )


def render_week_navigation(
    week_start: date,
    week_end: date,
    *,
    week_offset: int,
    prev_key: str,
    next_key: str,
) -> None:
    prev_col, info_col, next_col = st.columns([0.14, 0.72, 0.14], gap="small")
    with prev_col:
        if st.button("←", key=prev_key, width="stretch"):
            st.session_state["acciones_week_offset"] = week_offset - 1
            st.rerun()
    with info_col:
        st.markdown(
            f'<p class="sanzar-acciones-week-caption">Semana del <strong>{_esc(_format_week_range(week_start, week_end))}</strong></p>',
            unsafe_allow_html=True,
        )
    with next_col:
        if st.button("→", key=next_key, disabled=week_offset >= 0, width="stretch"):
            st.session_state["acciones_week_offset"] = week_offset + 1
            st.rerun()


def render_person_week_card(person: PersonCanalWeekStats, *, button_key: str) -> None:
    card_col, btn_col = st.columns([0.82, 0.18], gap="small")
    with card_col:
        st.markdown(
            f"""
<article class="sanzar-acciones-person-card">
  <div class="sanzar-acciones-person-head">
    <span class="sanzar-acciones-person-name">{_esc(person.persona_contacto)}</span>
    <span class="sanzar-acciones-person-total">{person.total} acciones</span>
  </div>
  <div class="sanzar-acciones-person-summary">
    {chip(f"{person.exitosos} exitosos", STATUS_SUCCESS)}
    {chip(f"{person.fallidos} fallidos", STATUS_DANGER)}
  </div>
  {_render_canal_mini_grid(person.by_canal)}
</article>
""",
            unsafe_allow_html=True,
        )
    with btn_col:
        st.markdown('<div class="sanzar-acciones-person-btn-spacer"></div>', unsafe_allow_html=True)
        if st.button("Ver detalle", key=button_key, width="stretch"):
            st.session_state["acciones_view"] = "person"
            st.session_state["acciones_selected_person"] = person.persona_contacto
            st.rerun()


def render_person_cards_grid(people: list[PersonCanalWeekStats], *, key_prefix: str) -> None:
    if not people:
        st.info("No hay registros de seguimiento en esta semana.")
        return
    for row_start in range(0, len(people), 2):
        row_people = people[row_start : row_start + 2]
        cols = st.columns(len(row_people), gap="medium")
        for col, person in zip(cols, row_people):
            with col:
                safe_name = person.persona_contacto.replace(" ", "_").replace("(", "").replace(")", "")
                render_person_week_card(
                    person,
                    button_key=f"{key_prefix}_person_{safe_name}_{row_start}",
                )


def _canal_rate_style(canal: str, tasa: float) -> str:
    if tasa >= 60:
        return "sanzar-acciones-canal-rate-fill sanzar-acciones-canal-rate-fill--high"
    if tasa >= 35:
        return "sanzar-acciones-canal-rate-fill sanzar-acciones-canal-rate-fill--mid"
    return "sanzar-acciones-canal-rate-fill sanzar-acciones-canal-rate-fill--low"


def render_canal_success_cards(canal_df) -> None:
    if canal_df.empty:
        st.info("Sin datos de canal todavía.")
        return
    for _, row in canal_df.iterrows():
        canal = str(row.get("canal_contacto", "") or "")
        total = int(row.get("total", 0) or 0)
        exitosos = int(row.get("exitosos", 0) or 0)
        fallidos = int(row.get("fallidos", 0) or 0)
        tasa = float(row.get("tasa_exito", 0) or 0)
        pct = max(0.0, min(100.0, tasa))
        st.markdown(
            f"""
<article class="sanzar-acciones-canal-rate-card">
  <div class="sanzar-acciones-canal-rate-head">
    <span class="sanzar-acciones-canal-rate-title">{_esc(_canal_label(canal))}</span>
    <span class="sanzar-acciones-canal-rate-pct">{pct:.1f}%</span>
  </div>
  <div class="sanzar-acciones-canal-rate-track">
    <div class="{_canal_rate_style(canal, pct)}" style="width:{pct:.1f}%;"></div>
  </div>
  <div class="sanzar-acciones-canal-rate-meta">
    {total} contactos · {exitosos} exitosos · {fallidos} fallidos
  </div>
</article>
""",
            unsafe_allow_html=True,
        )


def render_person_averages_dashboard(averages: PersonPerformanceAverages) -> None:
    cols = st.columns(4, gap="medium")
    metrics = [
        ("Semanas con actividad", averages.weeks_with_activity),
        ("Media acciones/semana", averages.avg_acciones_per_week),
        ("Media contactos/semana", averages.avg_contactos_unicos_per_week),
        ("Tasa éxito media", f"{averages.avg_success_rate_pct:.1f}%"),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            st.markdown(
                f"""
<div class="sanzar-acciones-kpi">
  <div class="sanzar-acciones-kpi-label">{_esc(label)}</div>
  <div class="sanzar-acciones-kpi-value">{_esc(value)}</div>
</div>
""",
                unsafe_allow_html=True,
            )
    st.caption(
        f"Totales en el periodo: {averages.total_acciones} acciones · "
        f"{averages.total_exitosos} exitosos · {averages.total_fallidos} fallidos"
    )


def render_person_week_snapshot_card(snapshot: PersonWeekSnapshot) -> None:
    if snapshot.total_acciones == 0:
        return
    st.markdown(
        f"""
<article class="sanzar-acciones-week-snapshot">
  <div class="sanzar-acciones-week-snapshot-head">
    <span class="sanzar-acciones-week-snapshot-when">{_esc(_format_week_range(snapshot.week_start, snapshot.week_end))}</span>
    <span class="sanzar-acciones-week-snapshot-total">{snapshot.total_acciones} acciones</span>
  </div>
  <div class="sanzar-acciones-week-snapshot-summary">
    {chip(f"{snapshot.contactos_unicos} contactos", STATUS_INFO)}
    {chip(f"{snapshot.exitosos} exitosos", STATUS_SUCCESS)}
    {chip(f"{snapshot.fallidos} fallidos", STATUS_DANGER)}
  </div>
  {_render_canal_mini_grid(snapshot.by_canal)}
</article>
""",
        unsafe_allow_html=True,
    )


def render_person_performance_snapshots(snapshots: list[PersonWeekSnapshot]) -> None:
    active = [snap for snap in snapshots if snap.total_acciones > 0]
    if not active:
        st.info("Sin actividad registrada en las últimas semanas.")
        return
    for snapshot in active:
        render_person_week_snapshot_card(snapshot)
