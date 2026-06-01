"""Commercial follow-up rows stored in the Acciones worksheet."""
from __future__ import annotations

import logging

import gspread

from config.settings import ACCIONES_HEADERS, CONFIG
from services.sheets_service import SheetsService

log = logging.getLogger(__name__)


def acciones_worksheet_name() -> str:
    return CONFIG.google_activity_log_worksheet_name


def ensure_commercial_actions_schema(sheets: SheetsService) -> None:
    """Ensure row 1 matches ACCIONES_HEADERS (clears sheet if headers drift)."""
    name = acciones_worksheet_name()
    spreadsheet = sheets.spreadsheet()
    expected = list(ACCIONES_HEADERS)
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


def init_commercial_actions_sheet(sheets_service: SheetsService) -> None:
    try:
        ensure_commercial_actions_schema(sheets_service)
    except Exception:
        log.warning("init_commercial_actions_sheet failed", exc_info=True)
