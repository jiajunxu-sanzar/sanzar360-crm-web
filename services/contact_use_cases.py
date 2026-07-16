from __future__ import annotations

from datetime import date

import pandas as pd

from config.contact_estado import normalize_contact_estado
from config.settings import CONTACT_ESTADO_DEFAULT
from models.contact import new_contact_row_dict
from services.contact_write_consistency import WriteVerificationResult, verify_contact_write_with_retry
from services.sheets_service import SheetsService


def _today_estado() -> str:
    return date.today().strftime("%d/%m/%Y")


def _apply_estado_fields_on_save(
    df: pd.DataFrame,
    row_idx: int,
    values: dict[str, str],
) -> dict[str, str]:
    updated = dict(values)
    old_estado = str(df.at[row_idx, "estado"] if "estado" in df.columns else "")
    new_estado = normalize_contact_estado(str(updated.get("estado", old_estado) or old_estado))
    if new_estado:
        updated["estado"] = new_estado
    old_normalized = normalize_contact_estado(old_estado)
    if new_estado and new_estado != old_normalized:
        updated["fecha_estado"] = _today_estado()
    return updated


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
    if not str(row_dict.get("estado", "") or "").strip():
        row_dict["estado"] = CONTACT_ESTADO_DEFAULT
    if not str(row_dict.get("fecha_estado", "") or "").strip():
        row_dict["fecha_estado"] = _today_estado()
    aligned = _aligned_contact_row(df.columns, row_dict)

    headers_reader = getattr(sheets, "worksheet_headers", None)
    hdr = headers_reader() if callable(headers_reader) else sheets.worksheet().row_values(1)
    contact_id = str(row_dict["contact_id"])
    if not hdr:
        new_df = pd.concat([df, aligned], ignore_index=True)
        sheets.save_contacts_df(new_df)
    else:
        appended_row = sheets.append_contact_row(row_dict)
        # La respuesta del append ya confirma la fila escrita (updatedRange):
        # sólo si no se pudo parsear (stubs / respuestas antiguas) se relee.
        confirmed_by_response = isinstance(appended_row, int) and appended_row > 1
        if not confirmed_by_response and not sheets.contact_id_exists_on_contacts_sheet(contact_id):
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
    values = _apply_estado_fields_on_save(df, row_idx, values)
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
