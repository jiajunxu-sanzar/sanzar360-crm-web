"""Backward-compatible shim; commercial data lives in Acciones (see commercial_actions_service)."""
from __future__ import annotations

from config.settings import ACCIONES_HEADERS
from services.commercial_actions_service import (
    ensure_commercial_actions_schema,
    init_commercial_actions_sheet,
)
from services.sheets_service import SheetsService

# Legacy name used by cache/tests.
ACTIVITY_HEADERS = ACCIONES_HEADERS


def init_activity_sheet(sheets_service: SheetsService) -> None:
    init_commercial_actions_sheet(sheets_service)


def _ensure_activity_schema(sheets: SheetsService) -> None:
    ensure_commercial_actions_schema(sheets)
