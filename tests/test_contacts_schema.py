from __future__ import annotations

from unittest.mock import MagicMock

from config.settings import CANONICAL_COLUMNS
from services.contacts_schema import ensure_contacts_schema


class _FakeWorksheet:
    def __init__(
        self,
        *,
        row1: list[str],
        data_rows: list[list[str]] | None = None,
        update: MagicMock | None = None,
    ) -> None:
        self._row1 = row1
        self._data_rows = data_rows or []
        self.clear = MagicMock()
        self.update = update or MagicMock()

    def get_all_values(self) -> list[list[str]]:
        return [list(self._row1), *self._data_rows]


class _FakeSheetsService:
    def __init__(self, ws: _FakeWorksheet) -> None:
        self._ws = ws

    def worksheet(self, name: str | None = None) -> _FakeWorksheet:
        _ = name
        return self._ws


def test_appends_responsable_cliente_without_clearing_data() -> None:
    old_head = [c for c in CANONICAL_COLUMNS if c != "responsable_cliente"]
    data_rows = [["x"] * len(old_head)]
    ws = _FakeWorksheet(row1=old_head, data_rows=data_rows)
    sheets = _FakeSheetsService(ws)

    ensure_contacts_schema(sheets)  # type: ignore[arg-type]

    ws.clear.assert_not_called()
    ws.update.assert_called_once()
    new_head = ws.update.call_args[0][0][0]
    assert new_head == old_head + ["responsable_cliente"]


def test_sets_full_header_on_empty_worksheet() -> None:
    ws = _FakeWorksheet(row1=[])
    sheets = _FakeSheetsService(ws)

    ensure_contacts_schema(sheets)  # type: ignore[arg-type]

    ws.clear.assert_not_called()
    ws.update.assert_called_once_with([list(CANONICAL_COLUMNS)], "A1")


def test_no_op_when_header_already_complete() -> None:
    ws = _FakeWorksheet(row1=list(CANONICAL_COLUMNS), data_rows=[["a"] * len(CANONICAL_COLUMNS)])
    sheets = _FakeSheetsService(ws)

    ensure_contacts_schema(sheets)  # type: ignore[arg-type]

    ws.update.assert_not_called()
