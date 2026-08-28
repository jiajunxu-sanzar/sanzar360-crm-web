"""Tests de LicitacionesService: logica de fechas y orquestacion de borrado/guardado.

Verifica que descartar/guardar_prioridad/limpiar_caducadas nunca disparan una
lectura de la hoja completa: solo lecturas ligeras de la columna de ids
(row_numbers_by_id) mas, cuando aplica, una escritura puntual o un borrado en
lote.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from config.settings import LICITACIONES_HEADERS, LICITACIONES_WORKSHEET_NAME
from services.licitaciones_service import (
    LicitacionesService,
    dias_habiles_restantes,
    es_urgente,
    esta_caducada,
    parse_fecha,
)

# ---------------------------------------------------------------------------
# Logica pura de fechas (sin Sheets) — lunes de referencia fijo
# ---------------------------------------------------------------------------

_LUNES = date(2026, 8, 31)


def test_parse_fecha_acepta_iso_y_dd_mm_yyyy() -> None:
    assert parse_fecha("2026-09-01") == date(2026, 9, 1)
    assert parse_fecha("01/09/2026") == date(2026, 9, 1)
    assert parse_fecha("") is None
    assert parse_fecha("no-es-una-fecha") is None


def test_dias_habiles_restantes_excluye_fin_de_semana() -> None:
    assert dias_habiles_restantes("2026-09-04", hoy=_LUNES) == 4  # viernes misma semana
    assert dias_habiles_restantes("2026-09-07", hoy=_LUNES) == 5  # lunes siguiente (salta finde)


def test_dias_habiles_restantes_negativo_si_ya_caduco() -> None:
    assert dias_habiles_restantes("2026-08-28", hoy=_LUNES) == -1


def test_es_urgente_umbral_3_dias_habiles() -> None:
    assert es_urgente("2026-09-01", hoy=_LUNES) is True   # martes: 1 dia habil
    assert es_urgente("2026-09-03", hoy=_LUNES) is True   # jueves: 3 dias habiles
    assert es_urgente("2026-09-04", hoy=_LUNES) is False  # viernes: 4 dias habiles
    assert es_urgente("2026-08-27", hoy=_LUNES) is False  # ya caducada, no "urgente"


def test_esta_caducada() -> None:
    assert esta_caducada("2026-08-27", hoy=_LUNES) is True
    assert esta_caducada("2026-08-31", hoy=_LUNES) is False  # hoy mismo, aun vigente
    assert esta_caducada("2026-09-01", hoy=_LUNES) is False


# ---------------------------------------------------------------------------
# LicitacionesService: orquestacion con un SheetsService falso
# ---------------------------------------------------------------------------


class _FakeSheets:
    """Fake minimo de SheetsService con contadores de llamadas."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df
        self.get_all_values_calls = 0
        self.row_numbers_by_id_calls = 0
        self.deleted_by_column: list[tuple[str, str, str]] = []
        self.deleted_by_row_numbers: list[tuple[str, list[int]]] = []
        self.updated_rows: list[tuple[str, int, dict]] = []

    def get_or_create_worksheet(self, name: str, headers: list[str]) -> None:
        return None

    def read_worksheet_df(self, name: str, headers: list[str]) -> pd.DataFrame:
        return self._df.copy()

    def row_numbers_by_id(self, name: str, id_column: str) -> dict[str, int]:
        self.row_numbers_by_id_calls += 1
        return {str(row[id_column]): i + 2 for i, row in self._df.iterrows()}

    def delete_rows_where_column_equals(self, worksheet_title: str, column_name: str, value: str) -> int:
        self.deleted_by_column.append((worksheet_title, column_name, value))
        return 1 if value in set(self._df[column_name].astype(str)) else 0

    def delete_rows_by_row_numbers(self, worksheet_title: str, row_numbers: list[int]) -> int:
        self.deleted_by_row_numbers.append((worksheet_title, list(row_numbers)))
        return len(row_numbers)

    def update_worksheet_row(self, name: str, headers: list[str], row_number: int, row: dict) -> None:
        self.updated_rows.append((name, row_number, dict(row)))

    def get_all_values(self):  # no deberia llamarse nunca desde LicitacionesService
        self.get_all_values_calls += 1
        return []


def _sample_df() -> pd.DataFrame:
    caducada = (date.today() - timedelta(days=10)).isoformat()
    vigente = (date.today() + timedelta(days=10)).isoformat()
    rows = [
        {**{h: "" for h in LICITACIONES_HEADERS}, "id": "L1", "titulo": "Uno", "fecha_fin_presentacion": vigente},
        {**{h: "" for h in LICITACIONES_HEADERS}, "id": "L2", "titulo": "Dos", "fecha_fin_presentacion": caducada},
    ]
    return pd.DataFrame(rows)


def test_descartar_borra_por_id_sin_leer_hoja_completa() -> None:
    sheets = _FakeSheets(_sample_df())
    service = LicitacionesService(sheets)  # type: ignore[arg-type]
    assert service.descartar("L1") is True
    assert sheets.deleted_by_column == [(LICITACIONES_WORKSHEET_NAME, "id", "L1")]
    assert sheets.get_all_values_calls == 0


def test_guardar_prioridad_preserva_el_resto_de_columnas() -> None:
    sheets = _FakeSheets(_sample_df())
    service = LicitacionesService(sheets)  # type: ignore[arg-type]
    current_row = _sample_df().iloc[0].to_dict()
    assert service.guardar_prioridad(current_row, "aplicar", "Encaja perfecto") is True
    assert len(sheets.updated_rows) == 1
    _, row_number, saved = sheets.updated_rows[0]
    assert saved["titulo"] == "Uno"  # resto de la fila intacto
    assert saved["prioridad"] == "aplicar"
    assert saved["nota_prioridad"] == "Encaja perfecto"


def test_limpiar_caducadas_borra_en_un_unico_lote_sin_leer_hoja_completa() -> None:
    sheets = _FakeSheets(_sample_df())
    service = LicitacionesService(sheets)  # type: ignore[arg-type]
    removed = service.limpiar_caducadas(_sample_df())
    assert removed == 1
    assert sheets.get_all_values_calls == 0
    assert len(sheets.deleted_by_row_numbers) == 1
    _, row_numbers = sheets.deleted_by_row_numbers[0]
    assert row_numbers == [3]  # L2 es la 2a fila de datos -> fila 3 (cabecera + 1-based)


def test_limpiar_caducadas_no_hace_nada_si_no_hay_caducadas() -> None:
    df = _sample_df()
    df = df[df["id"] == "L1"].reset_index(drop=True)
    sheets = _FakeSheets(df)
    service = LicitacionesService(sheets)  # type: ignore[arg-type]
    assert service.limpiar_caducadas(df) == 0
    assert sheets.deleted_by_row_numbers == []
