from __future__ import annotations

import html

import streamlit as st

from ui.palette import VisualStatusStyle, STATUS_NEUTRAL


def chip(label: str, style: VisualStatusStyle = STATUS_NEUTRAL) -> str:
    return (
        f"<span class='sanzar-chip' style='{style.css()}'>"
        f"{html.escape(str(label or 'Sin dato'))}</span>"
    )


def card(title: str, body: str, *, style: VisualStatusStyle = STATUS_NEUTRAL) -> None:
    st.markdown(
        f"""
        <div class="sanzar-card" style="{style.css()}">
          <h3>{html.escape(title)}</h3>
          <div>{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(title: str, value: str | int, help_text: str = "") -> None:
    st.markdown(
        f"""
        <div class="sanzar-card">
          <div class="sanzar-muted">{html.escape(title)}</div>
          <div style="font-size:1.75rem;font-weight:650;letter-spacing:-0.02em;">{html.escape(str(value))}</div>
          <div class="sanzar-kv">{html.escape(help_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
