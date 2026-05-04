from __future__ import annotations

from dataclasses import dataclass
from html import escape

import streamlit as st

from ui.palette import priority_style


@dataclass(frozen=True)
class WorkAlarmItem:
    """Single row in the alarms work inbox (source-agnostic).

    ``context_line``: optional SLA / aging (e.g. "Vence en 5 días", "15 días sin cambio").
    """

    title: str
    priority: str
    due: str
    owner: str
    suggested_action: str
    detail: str
    contact_id: str
    context_line: str = ""


def _stripe_color(item: WorkAlarmItem) -> str:
    return priority_style(item.priority).border


def render_work_inbox_row(item: WorkAlarmItem, *, row_index: int, category_label: str) -> bool:
    """Render one inbox row + primary CTA. Returns True when *Abrir ficha* was clicked."""
    stripe = escape(_stripe_color(item))
    pr = escape((item.priority or "sin dato").strip().capitalize())
    due_esc = escape(item.due or "—")
    owner_esc = escape(item.owner or "Sin responsable")
    title_esc = escape(item.title)
    detail_esc = escape(item.detail)
    action_esc = escape(item.suggested_action)
    ctx_esc = escape(item.context_line) if item.context_line.strip() else ""
    cat_esc = escape(category_label or "—")

    ctx_block = (
        f'<p class="sanzar-inbox-context">{ctx_esc}</p>'
        if ctx_esc
        else ""
    )

    left = f"""
<section class="sanzar-inbox-card" aria-label="{title_esc}" style="border-left-color:{stripe}">
  <div class="sanzar-inbox-eyebrow">
    <span class="sanzar-inbox-badge">{cat_esc}</span>
    <span class="sanzar-inbox-prio">Prioridad · <strong>{pr}</strong></span>
    <span class="sanzar-inbox-sep" aria-hidden="true"></span>
    <span class="sanzar-inbox-when-label">Referencia fecha</span>
    <span class="sanzar-inbox-when">{due_esc}</span>
  </div>
  <h3 class="sanzar-inbox-title">{title_esc}</h3>
  {ctx_block}
  <p class="sanzar-inbox-detail">{detail_esc}</p>
  <div class="sanzar-inbox-owner"><span class="sanzar-muted">Responsable</span> {owner_esc}</div>
  <div class="sanzar-inbox-next">
    <div class="sanzar-inbox-next-label">Siguiente acción</div>
    <div class="sanzar-inbox-next-text">{action_esc}</div>
  </div>
</section>
"""

    cat_slug = "_".join((category_label or "x").split())
    cid_safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in (item.contact_id or "anon"))

    col_main, col_cta = st.columns([5.8, 1.2], gap="small")
    with col_main:
        st.markdown(left, unsafe_allow_html=True)
    with col_cta:
        open_clicked = st.button(
            "Abrir ficha",
            key=f"alarm_inbox_open_{cat_slug}_{row_index}_{cid_safe}",
            use_container_width=True,
            type="primary",
        )

    st.markdown('<div class="sanzar-inbox-spacer"></div>', unsafe_allow_html=True)
    return open_clicked
