"""Tarjetas visuales para el Dashboard principal."""
from __future__ import annotations

import html

import streamlit as st

from config.contact_estado import normalize_contact_estado
from config.settings import CONTACT_ESTADO_ORDER
from ui.palette import contact_status_style


def _esc(value: object) -> str:
    return html.escape(str(value or ""))


def rank_fill_width(value: int, max_value: int) -> float:
    """Return bar width percentage in [0, 100]."""
    if max_value <= 0 or value <= 0:
        return 0.0
    return max(0.0, min(100.0, (value / max_value) * 100.0))


def _kpi_card_html(label: str, value: int | str, help_text: str, modifier: str) -> str:
    return f"""
<div class="sanzar-kpi sanzar-kpi--{modifier}">
  <div class="sanzar-kpi-label">{_esc(label)}</div>
  <div class="sanzar-kpi-value">{_esc(value)}</div>
  <div class="sanzar-kpi-help">{_esc(help_text)}</div>
</div>
"""


def render_dashboard_kpi_row(metrics: dict[str, int]) -> None:
    cards = [
        ("neutral", "Contactos", metrics.get("contactos", 0), "Total cargado desde Google Sheets"),
        ("success", "Clientes", metrics.get("clientes", 0), "Estado = Cliente"),
        ("info", "Próximas acciones", metrics.get("proximas_acciones", 0), "Contactos con fecha prevista"),
        ("warning", "Sin estado", metrics.get("sin_estado", 0), "Requieren limpieza"),
    ]
    cols = st.columns(4, gap="medium")
    for col, (modifier, label, value, help_text) in zip(cols, cards):
        with col:
            st.markdown(_kpi_card_html(label, value, help_text, modifier), unsafe_allow_html=True)


def build_funnel_card_html(estado: str, count: int, total_contactos: int) -> str:
    pct = rank_fill_width(count, total_contactos)
    style = contact_status_style(estado)
    fill_color = style.border
    return f"""
<article class="sanzar-dash-funnel-card" style="border-left:4px solid {fill_color};">
  <div class="sanzar-dash-funnel-head">
    <span class="sanzar-dash-funnel-title">{_esc(estado)}</span>
    <span class="sanzar-dash-funnel-value">{count} contactos</span>
  </div>
  <div class="sanzar-dash-funnel-track">
    <div class="sanzar-dash-funnel-fill" style="width:{pct:.1f}%;background:{fill_color};"></div>
  </div>
  <div class="sanzar-dash-funnel-meta">{pct:.1f}% del total</div>
</article>
"""


def _funnel_display_order(funnel: dict[str, int]) -> list[tuple[str, int]]:
    order_index = {estado: idx for idx, estado in enumerate(CONTACT_ESTADO_ORDER)}
    aggregated: dict[str, int] = {}
    for estado, count in funnel.items():
        label = normalize_contact_estado(estado) or estado or "Sin estado"
        aggregated[label] = aggregated.get(label, 0) + int(count)

    def sort_key(item: tuple[str, int]) -> tuple[int, int, str]:
        estado, count = item
        return (order_index.get(estado, 999), -count, estado)

    return sorted(aggregated.items(), key=sort_key)


def render_funnel_cards(funnel: dict[str, int], total_contactos: int) -> None:
    st.markdown('<div class="sanzar-dash-section">', unsafe_allow_html=True)
    if not funnel:
        st.info("No hay estados disponibles.")
        return
    ordered = _funnel_display_order(funnel)
    total = total_contactos if total_contactos > 0 else sum(funnel.values())
    for estado, count in ordered:
        st.markdown(build_funnel_card_html(estado, count, total), unsafe_allow_html=True)


def build_ranked_bar_card_html(label: str, value: int, max_value: int) -> str:
    pct = rank_fill_width(value, max_value)
    return f"""
<article class="sanzar-dash-rank-card">
  <div class="sanzar-dash-rank-head">
    <span class="sanzar-dash-rank-title">{_esc(label)}</span>
    <span class="sanzar-dash-rank-value">{value}</span>
  </div>
  <div class="sanzar-dash-rank-track">
    <div class="sanzar-dash-rank-fill" style="width:{pct:.1f}%;"></div>
  </div>
</article>
"""


def render_ranked_bar_cards(items: dict[str, int], *, empty_msg: str) -> None:
    st.markdown('<div class="sanzar-dash-section">', unsafe_allow_html=True)
    if not items:
        st.info(empty_msg)
        return
    max_value = max(items.values()) if items else 0
    for label, value in items.items():
        st.markdown(build_ranked_bar_card_html(label, value, max_value), unsafe_allow_html=True)
