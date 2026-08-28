"""Servicio de la pestana 'Licitaciones' del Google Sheet.

Sigue el mismo patron que ``ComprasService``: cada operacion cuesta como
mucho una lectura ligera (columna de ids) mas una escritura puntual — la hoja
completa nunca se reescribe entera salvo la primera vez que se crea la
pestana (``ensure_structure``). Ver ``licitaciones-ventana-crm-diseno.md`` en
el proyecto de Claude para el diseno completo.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd

from config.settings import (
    LICITACIONES_HEADERS,
    LICITACIONES_URGENTE_DIAS_HABILES,
    LICITACIONES_WORKSHEET_NAME,
)
from services.sheets_service import SheetsService

ID_COLUMN = "id"
FECHA_FIN_COLUMN = "fecha_fin_presentacion"


def parse_fecha(value: str) -> date | None:
    """Interpreta ``fecha_fin_presentacion`` en formato ISO o DD/MM/AAAA."""
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    return None


def dias_habiles_restantes(fecha_fin: str, *, hoy: date | None = None) -> int | None:
    """Dias habiles (lunes a viernes) entre hoy y ``fecha_fin``.

    ``None`` si la fecha no se pudo interpretar. Negativo si ya caduco.
    No excluye festivos nacionales, solo fines de semana — pendiente de
    decidir con Marco (ver licitaciones-ventana-crm-diseno.md).
    """
    parsed = parse_fecha(fecha_fin)
    if parsed is None:
        return None
    today = hoy or date.today()
    if parsed < today:
        return -int(np.busday_count(parsed, today))
    return int(np.busday_count(today, parsed))


def es_urgente(fecha_fin: str, *, hoy: date | None = None) -> bool:
    """True si vence en <= LICITACIONES_URGENTE_DIAS_HABILES dias habiles (y no ha caducado)."""
    dias = dias_habiles_restantes(fecha_fin, hoy=hoy)
    return dias is not None and 0 <= dias <= LICITACIONES_URGENTE_DIAS_HABILES


def esta_caducada(fecha_fin: str, *, hoy: date | None = None) -> bool:
    """True si ``fecha_fin`` ya paso (estrictamente anterior a hoy)."""
    parsed = parse_fecha(fecha_fin)
    if parsed is None:
        return False
    return parsed < (hoy or date.today())


class LicitacionesService:
    def __init__(self, sheets: SheetsService) -> None:
        self._sheets = sheets

    def ensure_structure(self) -> None:
        self._sheets.get_or_create_worksheet(LICITACIONES_WORKSHEET_NAME, list(LICITACIONES_HEADERS))

    def licitaciones_df(self) -> pd.DataFrame:
        self.ensure_structure()
        return self._sheets.read_worksheet_df(LICITACIONES_WORKSHEET_NAME, list(LICITACIONES_HEADERS))

    def descartar(self, licitacion_id: str) -> bool:
        """Elimina la fila directamente de la hoja (no se guarda descartado en ningun sitio)."""
        self.ensure_structure()
        clean_id = str(licitacion_id or "").strip()
        if not clean_id:
            return False
        removed = self._sheets.delete_rows_where_column_equals(
            LICITACIONES_WORKSHEET_NAME, ID_COLUMN, clean_id
        )
        return removed > 0

    def guardar_prioridad(self, current_row: dict[str, str], prioridad: str, nota: str) -> bool:
        """Actualiza ``prioridad``/``nota_prioridad`` preservando el resto de la fila.

        ``current_row`` debe venir del DataFrame ya cargado en memoria (evita
        una lectura extra a Sheets solo para conocer el resto de columnas).
        """
        self.ensure_structure()
        clean_id = str(current_row.get(ID_COLUMN, "") or "").strip()
        if not clean_id:
            return False
        row_num = self._sheets.row_numbers_by_id(LICITACIONES_WORKSHEET_NAME, ID_COLUMN).get(clean_id)
        if row_num is None:
            return False
        row = {h: str(current_row.get(h, "") or "") for h in LICITACIONES_HEADERS}
        row["prioridad"] = str(prioridad or "").strip()
        row["nota_prioridad"] = str(nota or "").strip()
        self._sheets.update_worksheet_row(LICITACIONES_WORKSHEET_NAME, list(LICITACIONES_HEADERS), row_num, row)
        return True

    def limpiar_caducadas(self, df: pd.DataFrame) -> int:
        """Borra en un unico lote las filas cuya fecha_fin_presentacion ya paso.

        ``df`` debe ser el DataFrame ya cargado en memoria (no dispara una
        lectura completa adicional); cuesta 1 lectura ligera de la columna de
        ids mas, solo si hay caducadas, 1 escritura en lote (``batchUpdate``).
        """
        self.ensure_structure()
        if df.empty or FECHA_FIN_COLUMN not in df.columns:
            return 0
        caducadas_ids = [
            str(row.get(ID_COLUMN, "") or "").strip()
            for _, row in df.iterrows()
            if esta_caducada(str(row.get(FECHA_FIN_COLUMN, "") or ""))
        ]
        caducadas_ids = [i for i in caducadas_ids if i]
        if not caducadas_ids:
            return 0
        row_numbers = self._sheets.row_numbers_by_id(LICITACIONES_WORKSHEET_NAME, ID_COLUMN)
        rows_to_delete = [row_numbers[i] for i in caducadas_ids if i in row_numbers]
        return self._sheets.delete_rows_by_row_numbers(LICITACIONES_WORKSHEET_NAME, rows_to_delete)
