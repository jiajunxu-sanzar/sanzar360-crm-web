from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from app.telemetry import timed
from config.settings import CONFIG
from config.settings import ACCIONES_HEADERS
from services.blogs_service import BlogsService
from services.compras_service import ComprasService
from services.contact_sensor_overview import build_contact_sensor_overview
from services.contacts_export import build_overview_pdf_bytes, build_overview_xlsx_bytes
from services.history_service import HistoryService
from services.inventory_service import InventoryService
from services.sheets_service import SheetsService
from services.users_service import load_users


@st.cache_resource
def sheets_service() -> SheetsService:
    return SheetsService()


@st.cache_resource
def blogs_service() -> BlogsService:
    return BlogsService(sheets_service())


@st.cache_resource
def compras_service() -> ComprasService:
    return ComprasService(sheets_service())


@st.cache_resource
def history_service() -> HistoryService:
    return HistoryService(sheets_service())


@st.cache_resource
def inventory_service() -> InventoryService:
    return InventoryService(sheets_service())


# NOTE: each loader takes a ``version`` argument bound to a session-state
# counter so that incrementing the counter invalidates the cache entry. The
# ``timed(...)`` blocks only run on cache *miss* (Streamlit short-circuits the
# decorated body on hit), giving us real-world latency for actual reads.


@st.cache_data(ttl=300, show_spinner=False)
def load_contacts_cached(version: int = 0):
    with timed("load_contacts_cached", version=version):
        return sheets_service().load_contacts_df()


@st.cache_data(ttl=300, show_spinner=False)
def load_history_rows_cached(kind: str, version: int = 0):
    with timed("load_history_rows_cached", kind=kind, version=version):
        return history_service().rows(kind)


@st.cache_data(ttl=300, show_spinner=False)
def load_users_cached(version: int = 0):
    with timed("load_users_cached", version=version):
        return load_users(sheets_service())


@st.cache_data(ttl=300, show_spinner=False)
def load_inventory_cached(version: int = 0):
    with timed("load_inventory_cached", version=version):
        return inventory_service().inventory_df()


@st.cache_data(ttl=300, show_spinner=False)
def load_inventory_model_fields_cached(version: int = 0):
    with timed("load_inventory_model_fields_cached", version=version):
        return inventory_service().model_fields_df()


@st.cache_data(ttl=300, show_spinner=False)
def load_blogs_cached(version: int = 0):
    with timed("load_blogs_cached", version=version):
        return blogs_service().blogs_df()


@st.cache_data(ttl=300, show_spinner=False)
def load_compras_cached(version: int = 0):
    with timed("load_compras_cached", version=version):
        return compras_service().compras_df()


@st.cache_data(ttl=300, show_spinner=False)
def load_acciones_cached(version: int = 0):
    """Filas de seguimiento comercial (hoja Acciones)."""
    with timed("load_acciones_cached", version=version):
        return sheets_service().read_worksheet_df(
            CONFIG.google_activity_log_worksheet_name, list(ACCIONES_HEADERS)
        )


def load_activity_log_cached(version: int = 0):
    """Alias de ``load_acciones_cached``."""
    return load_acciones_cached(version)


@st.cache_data(ttl=300, show_spinner=False)
def load_contact_sensor_overview_cached(version: int = 0) -> pd.DataFrame:
    with timed("load_contact_sensor_overview_cached", version=version):
        contacts = load_contacts_cached(version)
        sensor_rows = load_history_rows_cached("sensores", version)
        incidencia_rows = load_history_rows_cached("incidencias", version)
        acciones_df = load_acciones_cached(version)
        return build_contact_sensor_overview(
            contacts, sensor_rows, incidencia_rows, acciones_df
        )


def _overview_fingerprint(overview_df: pd.DataFrame) -> str:
    """Hash estable del contenido del resumen para cachear exports."""
    if overview_df is None or overview_df.empty:
        return "empty"
    return hashlib.md5(
        pd.util.hash_pandas_object(overview_df, index=True).values.tobytes()
    ).hexdigest()


@st.cache_data(ttl=300, show_spinner=False)
def _overview_xlsx_bytes_cached(fingerprint: str, _overview_df: pd.DataFrame):
    # ``exported_at`` fijado en el momento de generar; el fingerprint (no la hora)
    # decide el acierto de cache, así que el archivo no se regenera en cada rerun.
    return build_overview_xlsx_bytes(_overview_df)


@st.cache_data(ttl=300, show_spinner=False)
def _overview_pdf_bytes_cached(fingerprint: str, _overview_df: pd.DataFrame):
    return build_overview_pdf_bytes(_overview_df)


def overview_xlsx_bytes_cached(overview_df: pd.DataFrame):
    return _overview_xlsx_bytes_cached(_overview_fingerprint(overview_df), overview_df)


def overview_pdf_bytes_cached(overview_df: pd.DataFrame):
    return _overview_pdf_bytes_cached(_overview_fingerprint(overview_df), overview_df)


def clear_all_cache() -> None:
    st.cache_data.clear()
    history_service().invalidate_all()
