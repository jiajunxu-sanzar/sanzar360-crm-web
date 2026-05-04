from __future__ import annotations

import pandas as pd

from models.contact import new_contact_row_dict
from services.sheets_service import SheetsService


def _aligned_contact_row(columns: pd.Index | list[str], row: dict[str, str]) -> pd.DataFrame:
    rec = {str(col): str(row.get(str(col), "") or "") for col in columns}
    return pd.DataFrame([rec])


def create_empty_contact(
    df: pd.DataFrame,
    sheets: SheetsService,
    *,
    nombre: str = "",
) -> tuple[pd.DataFrame, str]:
    row_dict = new_contact_row_dict()
    name_clean = (nombre or "").strip()
    if name_clean:
        row_dict["nombre"] = name_clean
    aligned = _aligned_contact_row(df.columns, row_dict)

    hdr = sheets.worksheet().row_values(1)
    if not hdr:
        new_df = pd.concat([df, aligned], ignore_index=True)
        sheets.save_contacts_df(new_df)
    else:
        sheets.append_contact_row(row_dict)
        new_df = pd.concat([df, aligned], ignore_index=True)
    return new_df, str(row_dict["contact_id"])


def save_contact_by_id(
    df: pd.DataFrame,
    *,
    row_idx: int,
    contact_id: str,
    values: dict[str, str],
    sheets: SheetsService,
) -> pd.DataFrame:
    new_df = df.copy()
    for column, value in values.items():
        if column in new_df.columns:
            new_df.at[row_idx, column] = value
    sheets.save_contact_rows_by_ids(new_df, {str(contact_id)})
    return new_df
