from __future__ import annotations

import streamlit as st


DEFAULT_STATE = {
    "selected_contact_id": "",
    "active_page": "Contactos",
    "dirty_contact_ids": set(),
    "contacts_cache_version": 0,
    "history_cache_version": 0,
    "alarm_category": "Embudo",
    "asset_search_query": "",
    # Auth keys — managed exclusively via app.auth, never as widget keys.
    "_authenticated_user_id": "",
    "auth_ok": False,
    "login_error": "",
}


def init_state() -> None:
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value.copy() if isinstance(value, set) else value


def select_contact(contact_id: str) -> None:
    st.session_state.selected_contact_id = str(contact_id or "")
    st.session_state.active_page = "Contactos"
    st.session_state.pending_nav_page = "Contactos"


def mark_contact_dirty(contact_id: str) -> None:
    if "dirty_contact_ids" not in st.session_state:
        st.session_state.dirty_contact_ids = set()
    st.session_state.dirty_contact_ids.add(str(contact_id))


def bump_history_cache() -> None:
    st.session_state.history_cache_version = int(st.session_state.get("history_cache_version", 0)) + 1


def bump_contacts_cache() -> None:
    st.session_state.contacts_cache_version = int(st.session_state.get("contacts_cache_version", 0)) + 1
