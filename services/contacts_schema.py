"""Ensure Contacts worksheet header includes all CANONICAL_COLUMNS without clearing data."""
from __future__ import annotations

import logging

from config.settings import CANONICAL_COLUMNS, CONFIG
from services.sheets_service import SheetsService

log = logging.getLogger(__name__)


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


def ensure_contacts_schema(sheets: SheetsService) -> None:
    """Append missing canonical columns to row 1; never clear existing contact rows."""
    expected = list(CANONICAL_COLUMNS)
    ws = sheets.worksheet()
    # Camino rápido: solo la fila 1 (1 llamada ligera). El caso habitual es que
    # el esquema ya esté correcto; antes se descargaba la hoja COMPLETA aquí.
    head = _normalize_header_row(ws.row_values(1))
    if head == expected:
        return

    # Solo si hay discrepancia se lee la hoja completa para decidir con datos.
    all_values = ws.get_all_values()
    head = _normalize_header_row(all_values[0] if all_values else [])
    if head == expected:
        return

    has_data = _worksheet_has_data_rows(all_values)
    if not has_data:
        ws.update([expected], "A1")
        log.info("Contacts: set header row on empty worksheet %r.", CONFIG.google_worksheet_name)
        return

    missing = [column for column in expected if column not in head]
    if not missing:
        log.error(
            "Contacts worksheet %r header mismatch (got %r, expected %r). "
            "Existing data was preserved; fix row 1 manually or migrate via CSV.",
            CONFIG.google_worksheet_name,
            head,
            expected,
        )
        return

    new_head = head + missing
    ws.update([new_head], "A1")
    log.info(
        "Contacts: appended missing headers %s on worksheet %r.",
        missing,
        CONFIG.google_worksheet_name,
    )


def init_contacts_schema(sheets_service: SheetsService) -> None:
    try:
        ensure_contacts_schema(sheets_service)
    except Exception:
        log.warning("init_contacts_schema failed", exc_info=True)
