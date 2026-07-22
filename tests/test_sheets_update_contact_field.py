from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from services.sheets_service import SheetsService


class _FakeWorksheet:
    def __init__(self, *, headers: list[str], id_column_values: list[str]) -> None:
        self._headers = headers
        self._id_column_values = id_column_values
        self.update = MagicMock()

    def row_values(self, row: int) -> list[str]:
        if row == 1:
            return list(self._headers)
        return []

    def col_values(self, col_1based: int) -> list[str]:
        # col_1based corresponde a la columna "contact_id" en estos tests.
        return ["contact_id"] + self._id_column_values


def _service_with_worksheet(ws: _FakeWorksheet) -> SheetsService:
    svc = SheetsService.__new__(SheetsService)  # evita __init__ (no crea credenciales reales)
    svc.config = SimpleNamespace(google_worksheet_name="Contacts")
    svc._spreadsheet = None
    svc._contacts_row_by_cid = {}
    svc._worksheet_headers_cache = {}
    svc._worksheet_cache = {"Contacts": ws}
    svc.worksheet = lambda name=None: ws  # type: ignore[method-assign]
    return svc


def test_update_contact_field_writes_single_cell() -> None:
    headers = ["contact_id", "nombre", "correo", "newsletter_suscrito"]
    ws = _FakeWorksheet(headers=headers, id_column_values=["c1", "c2", "c3"])
    svc = _service_with_worksheet(ws)

    ok = svc.update_contact_field("c2", "newsletter_suscrito", "no")

    assert ok is True
    ws.update.assert_called_once()
    args, kwargs = ws.update.call_args
    values, cell_range = args[0], args[1]
    assert values == [["no"]]
    # c2 es la segunda fila de datos -> fila 3 de la hoja (1=header, 2=c1, 3=c2)
    assert cell_range == "D3"
    assert kwargs.get("value_input_option") == "RAW"


def test_update_contact_field_returns_false_for_unknown_column() -> None:
    headers = ["contact_id", "nombre", "correo"]
    ws = _FakeWorksheet(headers=headers, id_column_values=["c1"])
    svc = _service_with_worksheet(ws)

    ok = svc.update_contact_field("c1", "no_existe", "no")

    assert ok is False
    ws.update.assert_not_called()


def test_update_contact_field_returns_false_for_unknown_contact() -> None:
    headers = ["contact_id", "nombre", "newsletter_suscrito"]
    ws = _FakeWorksheet(headers=headers, id_column_values=["c1", "c2"])
    svc = _service_with_worksheet(ws)

    ok = svc.update_contact_field("no-existe", "newsletter_suscrito", "no")

    assert ok is False
    ws.update.assert_not_called()


def test_column_letter_beyond_z() -> None:
    assert SheetsService._column_letter(0) == "A"
    assert SheetsService._column_letter(25) == "Z"
    assert SheetsService._column_letter(26) == "AA"
    assert SheetsService._column_letter(27) == "AB"
