from __future__ import annotations

from typing import Final

import streamlit as st
import pandas as pd

CONTACTS_DF_OVERRIDE_KEY = "_contacts_df_override"
CONTACTS_PENDING_CREATED_ID_KEY = "contacts.pending_created_contact_id"
CONTACTS_WRITE_STATUS_KEY = "contacts.write_status"

# ---------------------------------------------------------------------------
# Cache version keys
#
# Every data loader that depends on Google Sheets reads a counter from
# session_state (e.g. ``load_contacts_cached(version)``). Bumping the counter
# invalidates Streamlit's ``@st.cache_data`` entry for that loader on the next
# call. Keeping the list centralized lets us invalidate all data caches at
# once when the remote spreadsheet changes, without spreading the literal
# strings around the codebase.
# ---------------------------------------------------------------------------
DATA_CACHE_VERSION_KEYS: Final[tuple[str, ...]] = (
    "contacts_cache_version",
    "history_cache_version",
    "inventory_cache_version",
    "compras_cache_version",
    "users_cache_version",
    "vacations_cache_version",
)


DEFAULT_STATE = {
    "selected_contact_id": "",
    "active_page": "Contactos",
    "dirty_contact_ids": set(),
    "contacts_cache_version": 0,
    "history_cache_version": 0,
    "inventory_cache_version": 0,
    "compras_cache_version": 0,
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


def bump_inventory_cache() -> None:
    st.session_state.inventory_cache_version = int(st.session_state.get("inventory_cache_version", 0)) + 1


def bump_compras_cache() -> None:
    st.session_state.compras_cache_version = int(st.session_state.get("compras_cache_version", 0)) + 1


def bump_all_data_caches() -> None:
    """Increment every data-cache version key in :data:`DATA_CACHE_VERSION_KEYS`.

    Use this when *all* sheets-backed data should be considered stale (e.g.
    after detecting a remote change in the spreadsheet or after the user asks
    for a soft reload).
    """
    for key in DATA_CACHE_VERSION_KEYS:
        st.session_state[key] = int(st.session_state.get(key, 0)) + 1


def soft_reload_data() -> None:
    """Clear data caches without touching UI state.

    Unlike :func:`hard_refresh_preserving_auth`, this preserves filters,
    selections, active page, dialog flags and any other session keys: it only
    invalidates the cached data layer so the next read goes back to Sheets.
    """
    from app.cache import clear_all_cache

    clear_all_cache()
    bump_all_data_caches()


def set_contacts_df_override(df: object) -> None:
    """One-shot contacts dataframe override for immediate UI consistency."""
    st.session_state[CONTACTS_DF_OVERRIDE_KEY] = df


def pop_contacts_df_override() -> object | None:
    """Consume and clear one-shot contacts dataframe override."""
    return st.session_state.pop(CONTACTS_DF_OVERRIDE_KEY, None)


def set_pending_created_contact_id(contact_id: str) -> None:
    st.session_state[CONTACTS_PENDING_CREATED_ID_KEY] = str(contact_id or "")


def pop_pending_created_contact_id() -> str:
    return str(st.session_state.pop(CONTACTS_PENDING_CREATED_ID_KEY, "") or "")


def set_contacts_write_status(status: str, *, message: str = "") -> None:
    st.session_state[CONTACTS_WRITE_STATUS_KEY] = {"status": str(status or ""), "message": str(message or "")}


def get_contacts_write_status() -> dict[str, str]:
    raw = st.session_state.get(CONTACTS_WRITE_STATUS_KEY, {})
    if isinstance(raw, dict):
        return {"status": str(raw.get("status", "") or ""), "message": str(raw.get("message", "") or "")}
    return {"status": "", "message": ""}


def clear_contacts_write_status() -> None:
    st.session_state.pop(CONTACTS_WRITE_STATUS_KEY, None)


def reconcile_selected_contact_id(df: pd.DataFrame, selected_contact_id: str) -> str:
    selected = str(selected_contact_id or "").strip()
    if not selected or "contact_id" not in df.columns:
        return ""
    matches = df[df["contact_id"].astype(str).str.strip() == selected]
    return selected if not matches.empty else ""


def hard_refresh_preserving_auth(*, extra_keep: dict[str, object] | None = None) -> None:
    """Clear app state/cache but keep authenticated user context."""
    from app.cache import clear_all_cache

    keep: dict[str, object] = {
        "_authenticated_user_id": str(st.session_state.get("_authenticated_user_id", "")),
        "auth_ok": bool(st.session_state.get("auth_ok", False)),
        "login_error": "",
    }
    if extra_keep:
        keep.update(extra_keep)
    for key in list(st.session_state.keys()):
        st.session_state.pop(key, None)
    for key, value in keep.items():
        st.session_state[key] = value
    clear_all_cache()
