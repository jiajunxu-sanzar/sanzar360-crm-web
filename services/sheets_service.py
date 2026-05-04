from __future__ import annotations

from pathlib import Path
from typing import Any

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from app.secrets import service_account_info
from app.telemetry import timed
from config.settings import CANONICAL_COLUMNS, CONFIG, PROJECT_ROOT
from models.contact import empty_contacts_dataframe

SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)


class SheetsService:
    def __init__(self, config=CONFIG) -> None:
        self.config = config
        self._spreadsheet: Any | None = None
        self._contacts_row_by_cid: dict[str, int] = {}

    def _credentials(self) -> Credentials:
        info = service_account_info()
        if info:
            return Credentials.from_service_account_info(info, scopes=SCOPES)
        path = Path(self.config.google_service_account_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return Credentials.from_service_account_file(path, scopes=SCOPES)

    def client(self) -> gspread.Client:
        return gspread.authorize(self._credentials())

    def spreadsheet(self):
        if self._spreadsheet is None:
            if not self.config.google_sheet_id:
                raise RuntimeError("GOOGLE_SHEET_ID no está configurado.")
            self._spreadsheet = self.client().open_by_key(self.config.google_sheet_id)
        return self._spreadsheet

    def worksheet(self, name: str | None = None):
        name = name or self.config.google_worksheet_name
        return self.spreadsheet().worksheet(name)

    def get_or_create_worksheet(self, name: str, headers: list[str]):
        spreadsheet = self.spreadsheet()
        try:
            worksheet = spreadsheet.worksheet(name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=name, rows=1000, cols=max(1, len(headers)))
            worksheet.update([headers], "A1")
            return worksheet
        current = worksheet.row_values(1)
        if not current:
            worksheet.update([headers], "A1")
        else:
            missing = [header for header in headers if header not in current]
            if missing:
                worksheet.update([current + missing], "A1")
        return worksheet

    def load_contacts_df(self) -> pd.DataFrame:
        with timed("sheets.load_contacts_df"):
            values = self.worksheet().get_all_records()
        if not values:
            return empty_contacts_dataframe()
        df = pd.DataFrame(values).fillna("")
        for column in CANONICAL_COLUMNS:
            if column not in df.columns:
                df[column] = ""
        df = df.astype(str)
        self._rebuild_contact_index(df)
        return df

    def _rebuild_contact_index(self, df: pd.DataFrame) -> None:
        self._contacts_row_by_cid = {}
        if "contact_id" not in df.columns:
            return
        for idx, contact_id in enumerate(df["contact_id"].astype(str).tolist(), start=2):
            if contact_id:
                self._contacts_row_by_cid[contact_id] = idx

    def save_contacts_df(self, df: pd.DataFrame) -> None:
        df = df.fillna("").astype(str)
        for column in CANONICAL_COLUMNS:
            if column not in df.columns:
                df[column] = ""
        headers = list(df.columns)
        rows = [headers] + df[headers].values.tolist()
        with timed("sheets.save_contacts_df_full"):
            self.worksheet().clear()
            self.worksheet().update(rows, "A1")
        self._rebuild_contact_index(df)

    def append_contact_row(self, row: dict[str, str]) -> None:
        """Append a single Contacts row aligned to worksheet row 1 headers.

        Does not clear the sheet. Caller must ensure headers already exist."""
        worksheet = self.worksheet()
        headers = worksheet.row_values(1)
        if not headers:
            raise RuntimeError("append_contact_row requires an existing header row.")
        values = [str(row.get(header, "") or "") for header in headers]
        with timed("sheets.append_contact_row"):
            worksheet.append_row(values, value_input_option="USER_ENTERED")
        cid = str(row.get("contact_id", "") or "").strip()
        if cid:
            self._contacts_row_by_cid[cid] = len(worksheet.col_values(1))

    def save_contact_rows_by_ids(self, df: pd.DataFrame, contact_ids: set[str]) -> None:
        if not contact_ids:
            return
        worksheet = self.worksheet()
        headers = worksheet.row_values(1)
        if not headers:
            self.save_contacts_df(df)
            return
        if not self._contacts_row_by_cid:
            self._rebuild_contact_index(df)
        updates: list[dict[str, Any]] = []
        for contact_id in contact_ids:
            matches = df[df["contact_id"].astype(str) == str(contact_id)]
            if matches.empty:
                continue
            row_num = self._contacts_row_by_cid.get(str(contact_id))
            if not row_num:
                self.save_contacts_df(df)
                return
            row = matches.iloc[0]
            values = [str(row.get(header, "")) for header in headers]
            updates.append({"range": f"A{row_num}", "values": [values]})
        if updates:
            with timed("sheets.save_contact_rows_by_ids", rows=len(updates)):
                worksheet.batch_update(updates)

    def read_worksheet_df(self, name: str, headers: list[str] | None = None) -> pd.DataFrame:
        worksheet = self.get_or_create_worksheet(name, headers or [])
        with timed("sheets.read_worksheet_df", worksheet=name):
            records = worksheet.get_all_records()
        df = pd.DataFrame(records).fillna("")
        if headers:
            for header in headers:
                if header not in df.columns:
                    df[header] = ""
        return df.astype(str) if not df.empty else pd.DataFrame(columns=headers or [])

    def write_worksheet_df(self, name: str, df: pd.DataFrame, headers: list[str]) -> None:
        worksheet = self.get_or_create_worksheet(name, headers)
        df = df.fillna("").astype(str)
        for header in headers:
            if header not in df.columns:
                df[header] = ""
        rows = [headers] + df[headers].values.tolist()
        with timed("sheets.write_worksheet_df_full", worksheet=name, rows=max(0, len(rows) - 1)):
            worksheet.clear()
            worksheet.update(rows, "A1")

    def append_worksheet_row(self, name: str, headers: list[str], row: dict[str, Any]) -> int:
        worksheet = self.get_or_create_worksheet(name, headers)
        values = [str(row.get(header, "") or "") for header in headers]
        with timed("sheets.append_worksheet_row", worksheet=name):
            worksheet.append_row(values, value_input_option="USER_ENTERED")
            return len(worksheet.col_values(1))

    def update_worksheet_row(self, name: str, headers: list[str], row_number: int, row: dict[str, Any]) -> None:
        worksheet = self.get_or_create_worksheet(name, headers)
        values = [str(row.get(header, "") or "") for header in headers]
        with timed("sheets.update_worksheet_row", worksheet=name):
            worksheet.update(f"A{row_number}", [values])

    def row_numbers_by_id(self, name: str, id_column: str) -> dict[str, int]:
        worksheet = self.get_or_create_worksheet(name, [id_column])
        with timed("sheets.row_numbers_by_id", worksheet=name):
            values = worksheet.get_all_values()
        if not values:
            return {}
        header = values[0]
        if id_column not in header:
            return {}
        idx = header.index(id_column)
        out: dict[str, int] = {}
        for row_number, row in enumerate(values[1:], start=2):
            row_id = str(row[idx] if idx < len(row) else "").strip()
            if row_id:
                out[row_id] = row_number
        return out

    def _get_worksheet_existing(self, title: str) -> Any | None:
        """Return the tab or ``None`` if it does not exist (does not create a new sheet)."""
        try:
            return self.spreadsheet().worksheet(title)
        except gspread.WorksheetNotFound:
            return None

    @staticmethod
    def _column_index_in_header(header_row: list[str], column_name: str) -> int | None:
        want = (column_name or "").strip().lower()
        for i, raw in enumerate(header_row):
            if str(raw).strip().lower() == want:
                return i
        return None

    def _batch_delete_row_numbers(self, worksheet: Any, row_numbers_1based: list[int]) -> None:
        """Single Sheets API ``batchUpdate`` with ``deleteDimension`` (bottom rows first)."""
        unique_desc = sorted(set(row_numbers_1based), reverse=True)
        if not unique_desc:
            return
        sheet_id = worksheet.id
        requests: list[dict[str, Any]] = []
        for row in unique_desc:
            start_idx = row - 1
            requests.append(
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": start_idx,
                            "endIndex": row,
                        }
                    }
                }
            )
        with timed("sheets.batch_delete_rows", rows=len(unique_desc)):
            self.spreadsheet().batch_update({"requests": requests})

    def delete_rows_where_column_equals(
        self,
        worksheet_title: str,
        column_name: str,
        value: str,
    ) -> int:
        """Elimina filas de datos donde ``column_name`` coincide con ``value`` (sin recrear la hoja).

        No crea la pestaña si falta. Cuenta como ~1 lectura + 1 escritura por llamada (batch de baja).
        Devuelve cuántas filas se borraron.
        """
        ws = self._get_worksheet_existing(worksheet_title)
        if ws is None:
            return 0
        target = str(value).strip()
        with timed("sheets.delete_rows_where_read", worksheet=worksheet_title):
            values = ws.get_all_values()
        if len(values) < 2:
            return 0
        header = [str(h) for h in values[0]]
        col_idx = self._column_index_in_header(header, column_name)
        if col_idx is None:
            return 0
        rows_to_delete: list[int] = []
        for row_number in range(2, len(values) + 1):
            row = values[row_number - 1]
            cell = str(row[col_idx] if col_idx < len(row) else "").strip()
            if cell == target:
                rows_to_delete.append(row_number)
        if not rows_to_delete:
            return 0
        self._batch_delete_row_numbers(ws, rows_to_delete)
        return len(rows_to_delete)

    def contact_id_exists_on_contacts_sheet(self, contact_id: str) -> bool:
        """Una sola lectura ligera para comprobar si el id está en la pestaña de contactos."""
        ws = self._get_worksheet_existing(self.config.google_worksheet_name)
        if ws is None:
            return False
        target = str(contact_id).strip()
        with timed("sheets.contact_id_exists", worksheet=self.config.google_worksheet_name):
            values = ws.get_all_values()
        if len(values) < 2:
            return False
        col_idx = self._column_index_in_header([str(h) for h in values[0]], "contact_id")
        if col_idx is None:
            return False
        for row in values[1:]:
            cell = str(row[col_idx] if col_idx < len(row) else "").strip()
            if cell == target:
                return True
        return False
