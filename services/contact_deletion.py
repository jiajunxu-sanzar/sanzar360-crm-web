"""Borrado total de un contacto en Google Sheets (fila + históricos + log de acciones).

Usa borrado por filas vía ``batchUpdate`` (deleteDimension) en lugar de reescribir
hojas enteras, para reducir peticiones a la API de Sheets y evitar errores 429.
"""

from __future__ import annotations

from app.cache import history_service, inventory_service
from config.settings import CONFIG
from services.history_service import HISTORY_SPECS, sensor_serials_from_sensor_serial_number
from services.sheets_service import SheetsService


def delete_contact_and_related_data(sheets: SheetsService, contact_id: str) -> None:
    """Elimina la fila del contacto y todas las filas relacionadas en otras hojas.

    - Pestaña principal de contactos
    - HistoricoSensores, HistoricoCampanas, HistoricoSuscripciones, HistoricoIncidencias
    - Log de actividad (Acciones)

    No es transaccional: si falla a mitad, parte de los cambios puede haberse guardado ya.
    """
    cid = str(contact_id or "").strip()
    if not cid:
        raise ValueError("contact_id vacío")

    if not sheets.contact_id_exists_on_contacts_sheet(cid):
        raise ValueError(
            f"No existe el contacto {cid!r} en la hoja de contactos "
            "(revisa espacios/formato de contact_id y que la columna sea 'contact_id')."
        )

    hist = history_service()
    affected_sensor_serials: list[str] = []
    for row in hist.rows_for_contact("sensores", cid):
        if str(row.get("estado_cierre_sensor", "") or "").strip().lower() == "cerrado":
            continue
        affected_sensor_serials.extend(
            sensor_serials_from_sensor_serial_number(str(row.get("sensor_serial_number", "") or ""))
        )
    open_assignments = hist.open_sensor_assignment_rows_for_serials(
        affected_sensor_serials,
        exclude_contact_id=cid,
    )

    for spec in HISTORY_SPECS.values():
        sheets.delete_rows_where_column_equals(spec.worksheet_name, "contact_id", cid)

    removed = sheets.delete_rows_where_column_equals(
        CONFIG.google_worksheet_name, "contact_id", cid
    )
    if removed < 1:
        raise RuntimeError(
            "No se pudo eliminar la fila del contacto "
            "(revisa que la columna se llame 'contact_id' y que el id no tenga espacios)."
        )

    if affected_sensor_serials:
        inventory_service().reconcile_locations_for_serials(
            affected_sensor_serials,
            open_assignments,
            default_location_type="por_definir",
        )

    hist.invalidate_all()
