from __future__ import annotations

import pandas as pd

from services.history_service import (
    HistoryService,
    count_sensor_assets,
    parse_sensor_asset_occurrences,
    parse_sensor_assets,
)

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


def _sensor_row(**kwargs: str) -> dict[str, str]:
    base = {h: "" for h in SENSOR_HEADERS}
    base.update(kwargs)
    return base


class FakeSheets:
    def __init__(self, sensor_rows: list[dict] | None = None) -> None:
        self.frames = {
            "HistoricoSensores": pd.DataFrame(sensor_rows or [], columns=list(SENSOR_HEADERS))
            .fillna("")
            .astype(str),
        }
        self.deleted_calls: list[tuple[str, str, str]] = []

    def get_or_create_worksheet(self, name: str, headers: list[str]) -> None:
        if name not in self.frames:
            self.frames[name] = pd.DataFrame(columns=headers)

    def read_worksheet_df(self, name: str, headers: list[str]) -> pd.DataFrame:
        df = self.frames.get(name, pd.DataFrame(columns=headers)).copy()
        for h in headers:
            if h not in df.columns:
                df[h] = ""
        return df[headers].fillna("").astype(str)

    def row_numbers_by_id(self, name: str, id_header: str) -> dict[str, int]:
        df = self.frames[name].fillna("").astype(str)
        return {
            str(row[id_header]).strip(): i + 2
            for i, row in df.iterrows()
            if str(row.get(id_header, "")).strip()
        }

    def append_worksheet_row(self, name: str, headers: list[str], row: dict) -> None:
        new_row = {h: str(row.get(h, "") or "") for h in headers}
        self.frames[name] = pd.concat([self.frames[name], pd.DataFrame([new_row])], ignore_index=True)

    def update_worksheet_row(self, name: str, headers: list[str], row_num: int, row: dict) -> None:
        idx = max(0, row_num - 2)
        df = self.frames[name].copy()
        for h in headers:
            df.at[idx, h] = str(row.get(h, "") or "")
        self.frames[name] = df

    def write_worksheet_df(self, name: str, df: pd.DataFrame, headers: list[str]) -> None:
        self.frames[name] = df[headers].fillna("").astype(str).copy()

    def delete_rows_where_column_equals(self, worksheet_title: str, column_name: str, value: str) -> int:
        self.deleted_calls.append((worksheet_title, column_name, str(value)))
        if worksheet_title not in self.frames:
            return 0
        df = self.frames[worksheet_title].copy()
        if column_name not in df.columns:
            return 0
        mask = df[column_name].astype(str).str.strip() == str(value).strip()
        removed = int(mask.sum())
        self.frames[worksheet_title] = df.loc[~mask].copy()
        return removed


def _office_closed_row() -> dict[str, str]:
    return _sensor_row(
        historial_sensor_id="h-office",
        contact_id="cid-office",
        nombre_cliente="oficina",
        fecha_inicio="19/05/2026",
        fecha_fin="19/05/2035",
        sensor_serial_number="uc501-6772F19975900001-T1000083818-8988228066680501197",
        estado_cierre_sensor="cerrado",
    )


def _new_client_candidate() -> dict[str, str]:
    return {
        "contact_id": "cid-new",
        "nombre_cliente": "Nuevo Cliente",
        "fecha_inicio": "20/05/2026",
        "fecha_fin": "20/05/2027",
        "sensor_serial_number": "uc501-6772F19975900001-T1000083818-8988228066680501197",
    }


def test_parse_sensor_assets_extracts_physical_assets() -> None:
    assets = parse_sensor_assets("uc501-UC001-TE001-SIM001")
    keys = {asset.key for asset, _ in assets}
    assert ("uc501", "uc001") in keys
    assert ("teros10", "te001") in keys
    assert ("sim", "sim001") in keys
    assert count_sensor_assets("uc501-UC001-TE001-SIM001") == 3


def test_parse_sensor_assets_uc501_gateway_only() -> None:
    assets = parse_sensor_assets("uc501-6772F19007800001")
    assert len(assets) == 1
    assert assets[0][0].asset_type == "uc501"
    assert assets[0][0].serial == "6772F19007800001"
    assert count_sensor_assets("uc501-6772F19007800001") == 1


def test_parse_sensor_asset_occurrences_includes_context() -> None:
    rows = [
        {
            "contact_id": "c1",
            "nombre_cliente": "Demo",
            "fecha_inicio": "01/01/2026",
            "sensor_serial_number": "uc512-UCDEM00341",
            "aws_user_id": "aws-demo",
        }
    ]
    occurrences = parse_sensor_asset_occurrences(rows)
    assert len(occurrences) == 1
    assert occurrences[0].asset.asset_type == "uc512"
    assert occurrences[0].aws_user_id == "aws-demo"


def test_sensor_assignment_conflicts_ignores_closed_history_in_other_contact() -> None:
    sheets = FakeSheets(sensor_rows=[_office_closed_row()])
    hist = HistoryService(sheets)
    conflicts = hist.sensor_assignment_conflicts(_new_client_candidate())
    assert conflicts == []


def test_sensor_assignment_conflicts_blocks_open_history_in_other_contact() -> None:
    open_row = _office_closed_row()
    open_row["estado_cierre_sensor"] = "abierto"
    open_row["historial_sensor_id"] = "h-office-open"
    sheets = FakeSheets(sensor_rows=[open_row])
    hist = HistoryService(sheets)
    conflicts = hist.sensor_assignment_conflicts(_new_client_candidate())
    assert len(conflicts) == 3
    assert all(c.nombre_cliente == "oficina" for c in conflicts)
    conflict_types = {c.asset.asset_type for c in conflicts}
    assert conflict_types == {"uc501", "teros10", "sim"}


def test_delete_row_uses_targeted_delete_without_full_rewrite() -> None:
    rows = [
        _sensor_row(historial_sensor_id="h-1", contact_id="cid-1", nombre_cliente="Cliente 1"),
        _sensor_row(historial_sensor_id="h-2", contact_id="cid-2", nombre_cliente="Cliente 2"),
    ]
    sheets = FakeSheets(sensor_rows=rows)
    hist = HistoryService(sheets)

    hist.delete_row("sensores", "h-1")

    assert sheets.deleted_calls == [("HistoricoSensores", "historial_sensor_id", "h-1")]
    remaining_ids = sheets.frames["HistoricoSensores"]["historial_sensor_id"].astype(str).tolist()
    assert remaining_ids == ["h-2"]
