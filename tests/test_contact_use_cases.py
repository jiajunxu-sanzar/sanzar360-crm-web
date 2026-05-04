import pandas as pd

from config.settings import CANONICAL_COLUMNS
from models.contact import empty_contacts_dataframe
from services.contact_use_cases import create_empty_contact, save_contact_by_id


class _FakeSheets:
    """Minimal Sheets facade for tests (bootstrap vs append contact creation)."""

    def __init__(self, simulate_sheet_headers: bool = False) -> None:
        self.simulate_sheet_headers = simulate_sheet_headers
        self.saved_full: pd.DataFrame | None = None
        self.saved_partial_ids: set[str] | None = None
        self.appended_contact_rows: list[list[str]] = []

    def worksheet(self) -> "_FakeSheets":
        return self

    def row_values(self, row: int) -> list[str]:
        if row != 1:
            return []
        if not self.simulate_sheet_headers:
            return []
        return list(CANONICAL_COLUMNS)

    def append_row(self, values: list[str], *, value_input_option: str = "") -> None:
        self.appended_contact_rows.append(list(values))

    def col_values(self, col: int) -> list[str]:
        _ = col
        return ["h"] + ["v"] * len(self.appended_contact_rows)

    def save_contacts_df(self, df: pd.DataFrame) -> None:
        self.saved_full = df.copy()

    def save_contact_rows_by_ids(self, df: pd.DataFrame, contact_ids: set[str]) -> None:
        self.saved_full = df.copy()
        self.saved_partial_ids = set(contact_ids)

    def append_contact_row(self, row: dict[str, str]) -> None:
        headers = self.row_values(1)
        if not headers:
            raise RuntimeError("test fake: append without headers")
        self.append_row([str(row.get(h, "") or "") for h in headers], value_input_option="USER_ENTERED")


def test_create_empty_contact_bootstraps_when_no_sheet_headers() -> None:
    sheets = _FakeSheets(simulate_sheet_headers=False)
    df = empty_contacts_dataframe()
    new_df, contact_id = create_empty_contact(df, sheets)  # type: ignore[arg-type]
    assert len(new_df) == 1
    assert contact_id
    assert sheets.saved_full is not None
    assert len(sheets.saved_full) == 1
    assert not sheets.appended_contact_rows


def test_create_empty_contact_appends_when_headers_exist() -> None:
    sheets = _FakeSheets(simulate_sheet_headers=True)
    df = empty_contacts_dataframe()
    new_df, contact_id = create_empty_contact(df, sheets)  # type: ignore[arg-type]
    assert len(new_df) == 1
    assert contact_id
    assert sheets.saved_full is None
    assert len(sheets.appended_contact_rows) == 1
    assert len(sheets.appended_contact_rows[0]) == len(CANONICAL_COLUMNS)


def test_create_empty_contact_sets_nombre() -> None:
    sheets = _FakeSheets(simulate_sheet_headers=False)
    df = empty_contacts_dataframe()
    new_df, contact_id = create_empty_contact(df, sheets, nombre="  Mi cliente  ")  # type: ignore[arg-type]
    assert new_df.iloc[-1]["nombre"] == "Mi cliente"
    assert contact_id == str(new_df.iloc[-1]["contact_id"])


def test_save_contact_by_id_updates_dataframe_and_calls_partial_save() -> None:
    sheets = _FakeSheets(simulate_sheet_headers=False)
    df = empty_contacts_dataframe()
    new_df, contact_id = create_empty_contact(df, sheets)  # type: ignore[arg-type]
    row_idx = new_df.index[0]
    updated = save_contact_by_id(
        new_df,
        row_idx=row_idx,
        contact_id=contact_id,
        values={"nombre": "Cliente Demo", "municipio": "Sevilla"},
        sheets=sheets,  # type: ignore[arg-type]
    )
    assert updated.loc[row_idx, "nombre"] == "Cliente Demo"
    assert updated.loc[row_idx, "municipio"] == "Sevilla"
    assert sheets.saved_partial_ids == {contact_id}
