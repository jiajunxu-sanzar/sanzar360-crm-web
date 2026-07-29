"""Centralised modal-state API.

All modal open/close operations go through this module so that any
navigation button can call ``close_modal()`` once and be guaranteed no
stale modal will re-appear on the next rerun.

The entire modal state lives under a **single** ``st.session_state`` key
(``_MODAL_KEY``) whose value is either ``None`` (no modal open) or a dict
describing what is open:

    {"type": "edit_history", "kind": str, "contact_id": str, "row_id": str}
    {"type": "add_history",  "kind": str, "contact_id": str}
    {"type": "sensor_close_location", "kind": str, "contact_id": str, "row_id": str}
    {"type": "riego_campanas", "contact_id": str, "historial_campana_id": str}
"""
from __future__ import annotations

import streamlit as st

_MODAL_KEY = "active_modal"


# ---------------------------------------------------------------------------
# Open helpers
# ---------------------------------------------------------------------------

def open_edit_history_modal(kind: str, contact_id: str, row_id: str) -> None:
    st.session_state[_MODAL_KEY] = {
        "type": "edit_history",
        "kind": kind,
        "contact_id": contact_id,
        "row_id": row_id,
    }


def open_add_history_modal(kind: str, contact_id: str) -> None:
    st.session_state[_MODAL_KEY] = {
        "type": "add_history",
        "kind": kind,
        "contact_id": contact_id,
    }


def open_sensor_close_location_modal(kind: str, contact_id: str, row_id: str) -> None:
    """Open location picker after closing a sensor history (replaces edit_history modal)."""
    st.session_state[_MODAL_KEY] = {
        "type": "sensor_close_location",
        "kind": kind,
        "contact_id": contact_id,
        "row_id": row_id,
    }


def open_riego_campanas_modal(contact_id: str, historial_campana_id: str) -> None:
    st.session_state[_MODAL_KEY] = {
        "type": "riego_campanas",
        "contact_id": contact_id,
        "historial_campana_id": historial_campana_id,
    }


# ---------------------------------------------------------------------------
# Close / read helpers
# ---------------------------------------------------------------------------

def close_modal() -> None:
    """Close any open modal. Safe to call even when nothing is open."""
    st.session_state[_MODAL_KEY] = None


def get_active_modal() -> dict | None:
    return st.session_state.get(_MODAL_KEY)


# ---------------------------------------------------------------------------
# Convenience checkers
# ---------------------------------------------------------------------------

def is_edit_history_open(kind: str, contact_id: str) -> tuple[bool, str]:
    """Return (True, row_id) if the edit-history modal is open for this (kind, contact)."""
    m = get_active_modal()
    if (
        m
        and m.get("type") == "edit_history"
        and m.get("contact_id") == contact_id
        and m.get("kind") == kind
    ):
        return True, str(m.get("row_id", ""))
    return False, ""


def is_add_history_open(kind: str, contact_id: str) -> bool:
    """Return True if the add-history modal is open for this (kind, contact)."""
    m = get_active_modal()
    return bool(
        m
        and m.get("type") == "add_history"
        and m.get("contact_id") == contact_id
        and m.get("kind") == kind
    )


def is_riego_campanas_open(contact_id: str) -> tuple[bool, str]:
    """Return (True, historial_campana_id) if the riego modal is open for this contact."""
    m = get_active_modal()
    if m and m.get("type") == "riego_campanas" and m.get("contact_id") == contact_id:
        return True, str(m.get("historial_campana_id", "") or "")
    return False, ""
