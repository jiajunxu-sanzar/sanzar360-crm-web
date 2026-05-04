"""Append-only activity log rows to the configured Google Sheet tab."""
from __future__ import annotations

import logging
from datetime import datetime

import gspread

from config.settings import CONFIG
from services.sheets_service import SheetsService

log = logging.getLogger(__name__)

ACTIVITY_HEADERS = ("fecha_accion", "contact_id", "nombre_contacto", "tipo_accion", "detalle", "persona")


def _activity_ws_name() -> str:
    return CONFIG.google_activity_log_worksheet_name


def _ensure_activity_schema(sheets: SheetsService) -> None:
    """Guarantee row 1 matches ACTIVITY_HEADERS exactly (order + names).

    If headers drift (old schema, merged columns from get_or_create_worksheet),
    the sheet is cleared and only the canonical header row is rewritten — existing
    rows are dropped (migration trade-off)."""
    name = _activity_ws_name()
    spreadsheet = sheets.spreadsheet()
    expected = list(ACTIVITY_HEADERS)
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=1000, cols=max(1, len(expected)))
        ws.update([expected], "A1")
        log.info("Acciones: created worksheet %r with header row.", name)
        return
    row1 = ws.row_values(1)
    head = [str(c).strip() for c in row1[: len(expected)]]
    if head != expected:
        ws.clear()
        ws.update([expected], "A1")
        log.info("Acciones: normalized header row on worksheet %r.", name)


def init_activity_sheet(sheets_service: SheetsService) -> None:
    """Ensure the activity worksheet exists with correct headers."""
    try:
        _ensure_activity_schema(sheets_service)
    except Exception:
        log.warning("init_activity_sheet failed", exc_info=True)


def append_activity(
    sheets_service: SheetsService,
    *,
    contact_id: str,
    nombre_contacto: str,
    tipo_accion: str,
    detalle: str = "",
    persona: str = "",
) -> None:
    """Append one row via API append_row (no full-sheet read/write round-trip)."""
    try:
        _ensure_activity_schema(sheets_service)
        row = {
            "fecha_accion": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "contact_id": contact_id,
            "nombre_contacto": nombre_contacto,
            "tipo_accion": tipo_accion,
            "detalle": detalle,
            "persona": persona,
        }
        ws = sheets_service.spreadsheet().worksheet(_activity_ws_name())
        values = [str(row.get(h, "") or "") for h in ACTIVITY_HEADERS]
        ws.append_row(values, value_input_option="USER_ENTERED")
    except Exception:
        log.warning("append_activity failed", exc_info=True)
