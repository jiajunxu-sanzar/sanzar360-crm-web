"""Commercial follow-up rows stored in the Acciones worksheet."""
from __future__ import annotations

import logging

import gspread

from config.settings import ACCIONES_HEADERS, CONFIG
from services.sheets_service import SheetsService

log = logging.getLogger(__name__)


def acciones_worksheet_name() -> str:
    return CONFIG.google_activity_log_worksheet_name


def _normalize_header_row(row_values: list[str]) -> list[str]:
    head = [str(c).strip() for c in row_values]
    while head and not head[-1]:
        head.pop()
    return head


def _worksheet_has_data_rows(all_values: list[list[str]]) -> bool:
    if len(all_values) <= 1:
        return False
    for row in all_values[1:]:
        if any(str(cell).strip() for cell in row):
            return True
    return False


def ensure_commercial_actions_schema(sheets: SheetsService) -> None:
    """Ensure row 1 matches ACCIONES_HEADERS without deleting existing data."""
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

    all_values = ws.get_all_values()
    head = _normalize_header_row(all_values[0] if all_values else [])
    if head == expected:
        return

    has_data = _worksheet_has_data_rows(all_values)
    if not has_data:
        ws.update([expected], "A1")
        log.info("Acciones: set header row on empty worksheet %r.", name)
        return

    missing = [column for column in expected if column not in head]
    if missing and set(head).issubset(set(expected)):
        new_head = head + missing
        ws.update([new_head], "A1")
        log.info("Acciones: appended missing headers %s on worksheet %r.", missing, name)
        return

    log.error(
        "Acciones worksheet %r header mismatch (got %r, expected %r). "
        "Existing data was preserved; fix row 1 manually or migrate via CSV.",
        name,
        head,
        expected,
    )


def init_commercial_actions_sheet(sheets_service: SheetsService) -> None:
    try:
        ensure_commercial_actions_schema(sheets_service)
    except Exception:
        log.warning("init_commercial_actions_sheet failed", exc_info=True)
