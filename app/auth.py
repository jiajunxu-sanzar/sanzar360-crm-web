"""Authentication state API.

All session-state keys related to the logged-in user are managed here.
The key ``_authenticated_user_id`` is NEVER used as a Streamlit widget key,
which ensures Streamlit's widget machinery can never overwrite it.
"""
from __future__ import annotations

import streamlit as st

_AUTH_KEY = "_authenticated_user_id"


def login(user_id: str) -> None:
    """Mark a user as authenticated. Call before st.rerun()."""
    st.session_state[_AUTH_KEY] = str(user_id)
    st.session_state["auth_ok"] = True
    st.session_state["login_error"] = ""


def logout() -> None:
    """Clear auth state. Call before st.rerun()."""
    st.session_state[_AUTH_KEY] = ""
    st.session_state["auth_ok"] = False
    st.session_state["login_error"] = ""


def get_authenticated_user_id() -> str:
    """Return the employee_id of the currently authenticated user, or ''."""
    return str(st.session_state.get(_AUTH_KEY, ""))


def is_authenticated() -> bool:
    """True only when both auth_ok flag is set AND a user_id is stored."""
    return bool(st.session_state.get("auth_ok", False)) and bool(get_authenticated_user_id())
