from __future__ import annotations

import pandas as pd

from models.contact import new_contact_row_dict
from services.contact_write_consistency import WriteVerificationResult, verify_contact_write_with_retry
from services.sheets_service import SheetsService


def _aligned_contact_row(columns: pd.Index | list[str], row: dict[str, str]) -> pd.DataFrame:
    rec = {str(col): str(row.get(str(col), "") or "") for col in columns}
    return pd.DataFrame([rec])


def create_empty_contact(
    df: pd.DataFrame,
    sheets: SheetsService,
    *,
    nombre: str = "",
) -> tuple[pd.DataFrame, str, WriteVerificationResult]:
    row_dict = new_contact_row_dict()
    name_clean = (nombre or "").strip()
    if name_clean:
        row_dict["nombre"] = name_clean
    aligned = _aligned_contact_row(df.columns, row_dict)

    hdr = sheets.worksheet().row_values(1)
    contact_id = str(row_dict["contact_id"])
    if not hdr:
        new_df = pd.concat([df, aligned], ignore_index=True)
        sheets.save_contacts_df(new_df)
    else:
        sheets.append_contact_row(row_dict)
        if not sheets.contact_id_exists_on_contacts_sheet(contact_id):
            raise RuntimeError("No se pudo confirmar el nuevo contacto en Google Sheets. Inténtalo de nuevo.")
        new_df = pd.concat([df, aligned], ignore_index=True)
    verify = verify_contact_write_with_retry(
        sheets=sheets,
        contact_id=contact_id,
        expected_subset={"contact_id": contact_id, "nombre": str(row_dict.get("nombre", "") or "")},
        operation="create",
    )
    return new_df, contact_id, verify


def save_contact_by_id(
    df: pd.DataFrame,
    *,
    row_idx: int,
    contact_id: str,
    values: dict[str, str],
    sheets: SheetsService,
) -> tuple[pd.DataFrame, WriteVerificationResult]:
    target_id = str(contact_id or "").strip()
    incoming_id = str(values.get("contact_id", "") or "").strip()
    if incoming_id != target_id:
        raise RuntimeError("Inconsistencia de contacto: el contact_id de la ficha no coincide con el registro a guardar.")
    new_df = df.copy()
    for column, value in values.items():
        if column in new_df.columns:
            new_df.at[row_idx, column] = value
    after_id = str(new_df.at[row_idx, "contact_id"] if "contact_id" in new_df.columns else "").strip()
    if after_id != target_id:
        raise RuntimeError("Inconsistencia de contacto: se alteró el contact_id al preparar el guardado.")
    sheets.save_contact_rows_by_ids(new_df, {target_id})
    verify = verify_contact_write_with_retry(
        sheets=sheets,
        contact_id=target_id,
        expected_subset=values,
        operation="update",
    )
    return new_df, verify
