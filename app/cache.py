from __future__ import annotations

import streamlit as st

from config.settings import CONFIG
from services.activity_log import ACTIVITY_HEADERS
from services.history_service import HistoryService
from services.inventory_service import InventoryService
from services.sheets_service import SheetsService
from services.users_service import load_users


@st.cache_resource
def sheets_service() -> SheetsService:
    return SheetsService()


@st.cache_resource
def history_service() -> HistoryService:
    return HistoryService(sheets_service())


@st.cache_resource
def inventory_service() -> InventoryService:
    return InventoryService(sheets_service())


@st.cache_data(ttl=300, show_spinner=False)
def load_contacts_cached(version: int = 0):
    return sheets_service().load_contacts_df()


@st.cache_data(ttl=300, show_spinner=False)
def load_history_rows_cached(kind: str, version: int = 0):
    return history_service().rows(kind)


@st.cache_data(ttl=300, show_spinner=False)
def load_users_cached(version: int = 0):
    return load_users(sheets_service())


@st.cache_data(ttl=300, show_spinner=False)
def load_inventory_cached(version: int = 0):
    return inventory_service().inventory_df()


@st.cache_data(ttl=300, show_spinner=False)
def load_inventory_model_fields_cached(version: int = 0):
    return inventory_service().model_fields_df()


@st.cache_data(ttl=300, show_spinner=False)
def load_activity_log_cached():
    """Filas del log ``Acciones`` (append-only desde la app)."""
    return sheets_service().read_worksheet_df(CONFIG.google_activity_log_worksheet_name, list(ACTIVITY_HEADERS))


def clear_all_cache() -> None:
    st.cache_data.clear()
    history_service().invalidate_all()
