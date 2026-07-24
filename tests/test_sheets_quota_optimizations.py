"""Tests de las optimizaciones de cuota de la Fase 1 (julio 2026).

Cubren: parseo de ``updatedRange`` del append, lectura multi-hoja en una
llamada (``values.batchGet``), índice de filas ligero (columna de ids en vez de
hoja completa), verificación de escritura leyendo una sola fila y el
mantenimiento local del índice en ``HistoryService``.
"""

from __future__ import annotations

import pandas as pd

from services.history_service import HISTORY_SPECS, HistoryService
from services.sheets_service import SheetsService


# ---------------------------------------------------------------------------
# _row_number_from_append_response
# ---------------------------------------------------------------------------


def test_row_number_parses_quoted_sheet_range() -> None:
    resp = {"updates": {"updatedRange": "'Historico Sensores'!A42:R42"}}
    assert SheetsService._row_number_from_append_response(resp) == 42


def test_row_number_parses_single_cell_range() -> None:
    resp = {"updates": {"updatedRange": "Contacts!A5"}}
    assert SheetsService._row_number_from_append_response(resp) == 5


def test_row_number_handles_missing_or_bad_response() -> None:
    assert SheetsService._row_number_from_append_response(None) == -1
    assert SheetsService._row_number_from_append_response({}) == -1
    assert SheetsService._row_number_from_append_response({"updates": {}}) == -1
    assert SheetsService._row_number_from_append_response("no-dict") == -1


# ---------------------------------------------------------------------------
# _values_to_df
# ---------------------------------------------------------------------------


def test_values_to_df_pads_short_rows_and_adds_required_headers() -> None:
    values = [["a", "b", "c"], ["1", "2"], ["4", "5", "6", "EXTRA"]]
    df = SheetsService._values_to_df(values, ["a", "b", "c", "d"])
    assert list(df.columns)[:3] == ["a", "b", "c"]
    assert "d" in df.columns
    assert df.iloc[0]["c"] == ""          # fila corta rellenada
    assert df.iloc[1]["c"] == "6"         # fila larga truncada al ancho de cabecera
    assert len(df) == 2


def test_values_to_df_empty_returns_requested_columns() -> None:
    df = SheetsService._values_to_df([], ["x", "y"])
    assert list(df.columns) == ["x", "y"]
    assert df.empty


# ---------------------------------------------------------------------------
# read_worksheets_batch — una única llamada para varias pestañas
# ---------------------------------------------------------------------------


class _FakeSpreadsheet:
    def __init__(self, data_by_sheet: dict[str, list[list[str]]]) -> None:
        self._data = data_by_sheet
        self.batch_calls: list[list[str]] = []

    def values_batch_get(self, ranges: list[str]):
        self.batch_calls.append(list(ranges))
        value_ranges = []
        for rng in ranges:
            name = rng.strip("'")
            value_ranges.append({"values": self._data.get(name, [])})
        return {"valueRanges": value_ranges}


def _service_with_fake_spreadsheet(data: dict[str, list[list[str]]]) -> tuple[SheetsService, _FakeSpreadsheet]:
    service = SheetsService()
    fake = _FakeSpreadsheet(data)
    service._spreadsheet = fake  # evita autenticación real
    return service, fake


def test_read_worksheets_batch_single_api_call() -> None:
    service, fake = _service_with_fake_spreadsheet(
        {
            "HojaA": [["id", "x"], ["1", "a"]],
            "HojaB": [["id", "y"], ["2", "b"], ["3", "c"]],
        }
    )
    frames = service.read_worksheets_batch(["HojaA", "HojaB"], {"HojaA": ["id", "x"], "HojaB": ["id", "y"]})
    assert len(fake.batch_calls) == 1
    assert frames["HojaA"].iloc[0]["x"] == "a"
    assert len(frames["HojaB"]) == 2


def test_read_worksheets_batch_missing_sheet_yields_empty_frame() -> None:
    service, _ = _service_with_fake_spreadsheet({"HojaA": [["id"], ["1"]]})
    frames = service.read_worksheets_batch(["HojaA", "NoExiste"], {"NoExiste": ["id", "z"]})
    assert list(frames["NoExiste"].columns) == ["id", "z"]
    assert frames["NoExiste"].empty


# ---------------------------------------------------------------------------
# Índice ligero + verificación por fila única
# ---------------------------------------------------------------------------


class _FakeWorksheet:
    """Worksheet mínimo: matriz en memoria con contadores de lecturas."""

    def __init__(self, rows: list[list[str]]) -> None:
        self.rows = rows
        self.get_all_values_calls = 0
        self.col_values_calls = 0
        self.row_values_calls = 0

    def get_all_values(self):
        self.get_all_values_calls += 1
        return [list(r) for r in self.rows]

    def col_values(self, col: int):
        self.col_values_calls += 1
        idx = col - 1
        return [str(r[idx]) if idx < len(r) else "" for r in self.rows]

    def row_values(self, row: int):
        self.row_values_calls += 1
        idx = row - 1
        return list(self.rows[idx]) if idx < len(self.rows) else []


class _SingleSheetService(SheetsService):
    """SheetsService cuyo ``worksheet()`` devuelve un fake en memoria."""

    def __init__(self, fake_ws: _FakeWorksheet) -> None:
        super().__init__()
        self._fake_ws = fake_ws

    def worksheet(self, name: str | None = None):  # type: ignore[override]
        return self._fake_ws


def _contacts_ws() -> _FakeWorksheet:
    return _FakeWorksheet(
        [
            ["contact_id", "nombre", "estado"],
            ["c-1", "Uno", "Cliente"],
            ["c-2", "Dos", "Contacto inicial"],
        ]
    )


def test_get_contact_row_fast_reads_single_row_not_full_sheet() -> None:
    ws = _contacts_ws()
    service = _SingleSheetService(ws)
    row = service.get_contact_row_fast("c-2")
    assert row is not None
    assert row["nombre"] == "Dos"
    assert ws.get_all_values_calls == 0  # nunca la hoja completa
    assert ws.col_values_calls == 1      # índice construido con la columna de ids
    assert ws.row_values_calls >= 1


def test_get_contact_row_fast_recovers_from_stale_index() -> None:
    ws = _contacts_ws()
    service = _SingleSheetService(ws)
    service._worksheet_headers_cache[service.config.google_worksheet_name or "Contacts"] = [
        "contact_id",
        "nombre",
        "estado",
    ]
    service._contacts_row_by_cid = {"c-2": 2}  # índice desfasado (apunta a c-1)
    row = service.get_contact_row_fast("c-2")
    assert row is not None
    assert row["contact_id"] == "c-2"
    assert row["nombre"] == "Dos"


def test_verify_contact_subset_uses_fast_row_read() -> None:
    ws = _contacts_ws()
    service = _SingleSheetService(ws)
    assert service.verify_contact_subset("c-1", {"nombre": "Uno"}) is True
    assert service.verify_contact_subset("c-1", {"nombre": "Otro"}) is False
    assert ws.get_all_values_calls == 0


# ---------------------------------------------------------------------------
# HistoryService: índice mantenido localmente (sin relecturas)
# ---------------------------------------------------------------------------

SENSOR_HEADERS = (
    "historial_sensor_id",
    "contact_id",
    "nombre_cliente",
    "fecha_inicio",
    "fecha_fin",
    "sensor_serial_number",
    "cantidad_sensores",
    "tipo_operacion",
    "estado_sensor",
    "estado_cierre_sensor",
    "ultima_revision",
    "red",
    "red_otro",
    "cuenta_usuario",
    "projectiotid",
    "aws_user_id",
    "detalles",
    "created_at",
    "updated_at",
)


class _CountingHistorySheets:
    """Fake de SheetsService para HistoryService con contadores de llamadas."""

    def __init__(self) -> None:
        self.frames: dict[str, pd.DataFrame] = {}
        self.row_numbers_calls = 0
        self.read_worksheet_calls = 0

    def get_or_create_worksheet(self, name: str, headers: list[str]) -> None:
        if name not in self.frames:
            self.frames[name] = pd.DataFrame(columns=headers)

    def read_worksheet_df(self, name: str, headers: list[str]) -> pd.DataFrame:
        self.read_worksheet_calls += 1
        df = self.frames.get(name, pd.DataFrame(columns=headers)).copy()
        for h in headers:
            if h not in df.columns:
                df[h] = ""
        return df[headers].fillna("").astype(str)

    def row_numbers_by_id(self, name: str, id_header: str) -> dict[str, int]:
        self.row_numbers_calls += 1
        df = self.frames.get(name, pd.DataFrame()).fillna("").astype(str)
        if df.empty or id_header not in df.columns:
            return {}
        return {
            str(row[id_header]).strip(): i + 2
            for i, row in df.iterrows()
            if str(row.get(id_header, "")).strip()
        }

    def append_worksheet_row(self, name: str, headers: list[str], row: dict) -> int:
        new_row = {h: str(row.get(h, "") or "") for h in headers}
        self.frames[name] = pd.concat(
            [self.frames.get(name, pd.DataFrame(columns=headers)), pd.DataFrame([new_row])],
            ignore_index=True,
        )
        return len(self.frames[name]) + 1  # simula updatedRange del API real

    def update_worksheet_row(self, name: str, headers: list[str], row_num: int, row: dict) -> None:
        idx = max(0, row_num - 2)
        df = self.frames[name].copy()
        for h in headers:
            df.at[idx, h] = str(row.get(h, "") or "")
        self.frames[name] = df

    def delete_rows_where_column_equals(self, worksheet_title: str, column_name: str, value: str) -> int:
        df = self.frames.get(worksheet_title)
        if df is None or column_name not in df.columns:
            return 0
        mask = df[column_name].astype(str).str.strip() == str(value).strip()
        removed = int(mask.sum())
        self.frames[worksheet_title] = df.loc[~mask].copy()
        return removed


def test_history_add_row_verifies_id_and_keeps_row_number() -> None:
    sheets = _CountingHistorySheets()
    service = HistoryService(sheets)  # type: ignore[arg-type]
    row = service.add_row("sensores", {"contact_id": "c-1", "sensor_serial_number": "SN 123"})
    # Tras el append se verifica el id (1 lectura de columna), no un get_all_values.
    assert sheets.row_numbers_calls == 1
    row_id = row["historial_sensor_id"]
    assert service._row_numbers["sensores"][row_id] > 1


def test_history_add_row_raises_if_id_not_in_sheets() -> None:
    class _NoPersistSheets(_CountingHistorySheets):
        def append_worksheet_row(self, name: str, headers: list[str], row: dict) -> int:
            return 99  # simula append OK pero no persiste en frames

        def row_numbers_by_id(self, name: str, id_header: str) -> dict[str, int]:
            self.row_numbers_calls += 1
            return {}

    service = HistoryService(_NoPersistSheets())  # type: ignore[arg-type]
    try:
        service.add_row("campanas", {"contact_id": "c-1", "nombre_campana": "X"})
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "No se confirmó el guardado" in str(exc)


def test_history_delete_row_shifts_index_locally() -> None:
    sheets = _CountingHistorySheets()
    service = HistoryService(sheets)  # type: ignore[arg-type]
    first = service.add_row("sensores", {"contact_id": "c-1", "sensor_serial_number": "SN A"})
    second = service.add_row("sensores", {"contact_id": "c-2", "sensor_serial_number": "SN B"})
    first_num = service._row_numbers["sensores"][first["historial_sensor_id"]]
    second_num = service._row_numbers["sensores"][second["historial_sensor_id"]]
    assert second_num == first_num + 1
    baseline_calls = sheets.row_numbers_calls
    service.delete_row("sensores", first["historial_sensor_id"])
    assert sheets.row_numbers_calls == baseline_calls  # sin relectura
    assert first["historial_sensor_id"] not in service._row_numbers["sensores"]
    assert service._row_numbers["sensores"][second["historial_sensor_id"]] == second_num - 1


class _BatchHistorySheets(_CountingHistorySheets):
    def __init__(self) -> None:
        super().__init__()
        self.batch_calls: list[list[str]] = []

    def read_worksheets_batch(
        self, names: list[str], headers_by_name: dict[str, list[str]] | None = None
    ) -> dict[str, pd.DataFrame]:
        self.batch_calls.append(list(names))
        headers_by_name = headers_by_name or {}
        return {
            name: self.read_worksheet_df_no_count(name, headers_by_name.get(name, []))
            for name in names
        }

    def read_worksheet_df_no_count(self, name: str, headers: list[str]) -> pd.DataFrame:
        df = self.frames.get(name, pd.DataFrame(columns=headers)).copy()
        for h in headers:
            if h not in df.columns:
                df[h] = ""
        return df[headers].fillna("").astype(str) if headers else df.fillna("").astype(str)


def test_history_lazy_load_batches_only_requested_kind() -> None:
    sheets = _BatchHistorySheets()
    service = HistoryService(sheets)  # type: ignore[arg-type]
    service.rows("sensores")
    assert len(sheets.batch_calls) == 1
    assert sheets.batch_calls[0] == [HISTORY_SPECS["sensores"].worksheet_name]
    service.rows("campanas")
    assert len(sheets.batch_calls) == 2
    assert sheets.batch_calls[1] == [HISTORY_SPECS["campanas"].worksheet_name]
    service.rows("sensores")  # ya cargado
    assert len(sheets.batch_calls) == 2
    assert sheets.read_worksheet_calls == 0


def test_history_load_kinds_batches_requested_together() -> None:
    sheets = _BatchHistorySheets()
    service = HistoryService(sheets)  # type: ignore[arg-type]
    service.load_kinds(["sensores", "incidencias"])
    assert len(sheets.batch_calls) == 1
    names = sheets.batch_calls[0]
    assert HISTORY_SPECS["sensores"].worksheet_name in names
    assert HISTORY_SPECS["incidencias"].worksheet_name in names
    assert len(names) == 2
    service.rows("sensores")
    service.rows("incidencias")
    assert len(sheets.batch_calls) == 1


# ---------------------------------------------------------------------------
# Append/update alineado al orden real de la fila 1
# ---------------------------------------------------------------------------


class _WritableFakeWorksheet:
    """Worksheet en memoria con update/append_row para tests de escritura."""

    def __init__(self, header_row: list[str]) -> None:
        self.rows: list[list[str]] = [list(header_row)]
        self.appended: list[list[str]] = []
        self.header_updates: list[list[str]] = []

    def row_values(self, row: int) -> list[str]:
        idx = row - 1
        return list(self.rows[idx]) if 0 <= idx < len(self.rows) else []

    def update(self, values, range_name="A1", value_input_option=None):  # noqa: ANN001
        if str(range_name).upper().startswith("A1") and values and isinstance(values[0], list):
            # Cabeceras (fila 1) o actualización de una fila completa.
            if range_name in ("A1",) or str(range_name) == "A1":
                self.rows[0] = list(values[0])
                self.header_updates.append(list(values[0]))
                return
            # A{n} — actualizar fila n
            try:
                row_num = int(str(range_name)[1:].split(":")[0])
            except ValueError:
                row_num = 1
            while len(self.rows) < row_num:
                self.rows.append([])
            self.rows[row_num - 1] = list(values[0])
            return
        if values and isinstance(values[0], list):
            self.rows[0] = list(values[0])
            self.header_updates.append(list(values[0]))

    def append_row(self, values, value_input_option=None):  # noqa: ANN001
        vals = [str(v) for v in values]
        self.appended.append(vals)
        self.rows.append(vals)
        last = len(self.rows)
        return {"updates": {"updatedRange": f"Sheet!A{last}:Z{last}"}}


class _WriteAlignService(SheetsService):
    def __init__(self, ws: _WritableFakeWorksheet) -> None:
        super().__init__()
        self._ws = ws

    def get_or_create_worksheet(self, name: str, headers: list[str]):  # type: ignore[override]
        return self._ws


def test_append_worksheet_row_follows_sheet_header_order_not_code_order() -> None:
    """Reproduce el bug: orden del código ≠ fila 1 → valores en columnas locas."""
    # Orden real de HistoricoCampanas (producción).
    sheet_order = [
        "historial_campana_id",
        "contact_id",
        "nombre_cliente",
        "nombre_campana",
        "fecha_campana_inicio",
        "historial_sensor_id",
        "estado_cierre_campana",
    ]
    # Orden "del código" distinto (sensor/estado antes que nombre_campana).
    code_order = [
        "historial_campana_id",
        "contact_id",
        "nombre_cliente",
        "historial_sensor_id",
        "estado_cierre_campana",
        "nombre_campana",
        "fecha_campana_inicio",
    ]
    ws = _WritableFakeWorksheet(sheet_order)
    service = _WriteAlignService(ws)
    service.append_worksheet_row(
        "HistoricoCampanas",
        code_order,
        {
            "historial_campana_id": "hc-1",
            "contact_id": "c-1",
            "nombre_cliente": "Ana",
            "nombre_campana": "Campaña primavera",
            "fecha_campana_inicio": "01/03/2026",
            "historial_sensor_id": "hs-9",
            "estado_cierre_campana": "abierto",
        },
    )
    assert len(ws.appended) == 1
    written = ws.appended[0]
    assert written[sheet_order.index("nombre_campana")] == "Campaña primavera"
    assert written[sheet_order.index("historial_sensor_id")] == "hs-9"
    assert written[sheet_order.index("estado_cierre_campana")] == "abierto"
    # Sin el fix, nombre_campana habría caído donde está historial_sensor_id.
    assert written[sheet_order.index("historial_sensor_id")] != "Campaña primavera"


def test_append_adds_missing_required_headers_with_title() -> None:
    ws = _WritableFakeWorksheet(["historial_campana_id", "contact_id", "nombre_campana"])
    service = _WriteAlignService(ws)
    service.append_worksheet_row(
        "HistoricoCampanas",
        ["historial_campana_id", "contact_id", "nombre_campana", "latitud", "longitud"],
        {
            "historial_campana_id": "hc-2",
            "contact_id": "c-2",
            "nombre_campana": "X",
            "latitud": "40.1",
            "longitud": "-3.7",
        },
    )
    assert ws.rows[0][-2:] == ["latitud", "longitud"]
    assert "" not in ws.rows[0]
    written = ws.appended[0]
    assert written[ws.rows[0].index("latitud")] == "40.1"
    assert written[ws.rows[0].index("longitud")] == "-3.7"
