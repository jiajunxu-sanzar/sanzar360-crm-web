from __future__ import annotations

from unittest.mock import MagicMock

import gspread

from config.settings import ACCIONES_HEADERS
from services.commercial_actions_service import ensure_commercial_actions_schema


class _FakeWorksheet:
    def __init__(
        self,
        *,
        row1: list[str],
        data_rows: list[list[str]] | None = None,
        clear: MagicMock | None = None,
        update: MagicMock | None = None,
    ) -> None:
        self._row1 = row1
        self._data_rows = data_rows or []
        self.clear = clear or MagicMock()
        self.update = update or MagicMock()

    def row_values(self, row_number: int) -> list[str]:
        if row_number == 1:
            return list(self._row1)
        return []

    def get_all_values(self) -> list[list[str]]:
        return [list(self._row1), *self._data_rows]


class _FakeSpreadsheet:
    def __init__(self, ws: _FakeWorksheet | None = None) -> None:
        self._ws = ws
        self.add_worksheet = MagicMock(return_value=_FakeWorksheet(row1=[]))

    def worksheet(self, name: str) -> _FakeWorksheet:
        if self._ws is None:
            raise gspread.WorksheetNotFound(name)
        return self._ws


class _FakeSheetsService:
    def __init__(self, spreadsheet: _FakeSpreadsheet) -> None:
        self._spreadsheet = spreadsheet

    def spreadsheet(self) -> _FakeSpreadsheet:
        return self._spreadsheet


def test_creates_worksheet_when_missing() -> None:
    spreadsheet = _FakeSpreadsheet(ws=None)
    sheets = _FakeSheetsService(spreadsheet)

    ensure_commercial_actions_schema(sheets)  # type: ignore[arg-type]

    spreadsheet.add_worksheet.assert_called_once()
    created_ws = spreadsheet.add_worksheet.return_value
    created_ws.update.assert_called_once_with([list(ACCIONES_HEADERS)], "A1")
    created_ws.clear.assert_not_called()


def test_does_not_clear_when_header_mismatch_with_data() -> None:
    old_head = ["col_a", "col_b", "col_c"]
    data_rows = [["1", "Alice", "x"], ["2", "Bob", "y"], ["3", "Carol", "z"], ["4", "Dan", "w"], ["5", "Eve", "v"]]
    ws = _FakeWorksheet(row1=old_head, data_rows=data_rows)
    sheets = _FakeSheetsService(_FakeSpreadsheet(ws=ws))

    ensure_commercial_actions_schema(sheets)  # type: ignore[arg-type]

    ws.clear.assert_not_called()
    ws.update.assert_not_called()


def test_sets_header_on_empty_worksheet() -> None:
    ws = _FakeWorksheet(row1=["wrong", "headers"])
    sheets = _FakeSheetsService(_FakeSpreadsheet(ws=ws))

    ensure_commercial_actions_schema(sheets)  # type: ignore[arg-type]

    ws.clear.assert_not_called()
    ws.update.assert_called_once_with([list(ACCIONES_HEADERS)], "A1")


def test_appends_missing_headers_when_existing_are_subset() -> None:
    partial = list(ACCIONES_HEADERS[:3])
    data_rows = [["a", "b", "c"]]
    ws = _FakeWorksheet(row1=partial, data_rows=data_rows)
    sheets = _FakeSheetsService(_FakeSpreadsheet(ws=ws))

    ensure_commercial_actions_schema(sheets)  # type: ignore[arg-type]

    ws.clear.assert_not_called()
    ws.update.assert_called_once()
    new_head = ws.update.call_args[0][0][0]
    assert new_head[:3] == partial
    assert new_head == partial + list(ACCIONES_HEADERS[3:])
