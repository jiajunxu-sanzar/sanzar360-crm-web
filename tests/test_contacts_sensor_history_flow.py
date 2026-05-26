"""Tests for the guided sensor history flow: availability filtering,
association loading, canonical string composition, inventory sync,
and solenoide format support."""
from __future__ import annotations

import pandas as pd
import pytest

from config.settings import INVENTORY_HEADERS, INVENTORY_MODEL_FIELDS_WORKSHEET_NAME, INVENTORY_WORKSHEET_NAME
from services.history_service import HistoryService, parse_sensor_assets
from services.inventory_service import InventoryService, RootAssetAssociations
from services.sheet_date_format import is_valid_sensor_serial_number, sensor_serial_number_summary_lines
from pages.contacts import (
    _collect_all_serials_from_sensor_sn,
    _extract_sim_sn,
    _extract_solenoide_sn,
    _extract_ug67_bundle,
    _infer_sensor_root_type,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(**kwargs: str) -> dict[str, str]:
    base = {h: "" for h in INVENTORY_HEADERS}
    base.update({k: str(v) for k, v in kwargs.items()})
    return base


def _inv_df(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=list(INVENTORY_HEADERS)).fillna("").astype(str)


SENSOR_HEADERS = (
    "historial_sensor_id", "contact_id", "nombre_cliente", "fecha_inicio",
    "fecha_fin", "sensor_serial_number", "cantidad_sensores", "tipo_operacion",
    "estado_sensor", "estado_cierre_sensor", "ultima_revision", "red",
    "red_otro", "cuenta_usuario", "projectiotid", "aws_user_id", "detalles",
    "created_at", "updated_at",
)


def _sensor_row(**kwargs: str) -> dict[str, str]:
    base = {h: "" for h in SENSOR_HEADERS}
    base.update(kwargs)
    return base


class FakeSheets:
    def __init__(self, inv_df: pd.DataFrame | None = None, sensor_rows: list[dict] | None = None) -> None:
        self.frames: dict[str, pd.DataFrame] = {
            INVENTORY_WORKSHEET_NAME: inv_df if inv_df is not None else pd.DataFrame(columns=list(INVENTORY_HEADERS)),
            INVENTORY_MODEL_FIELDS_WORKSHEET_NAME: pd.DataFrame(columns=["model", "field_key"]),
            "HistoricoSensores": pd.DataFrame(sensor_rows or [], columns=list(SENSOR_HEADERS)).fillna("").astype(str),
        }
        self._row_counters: dict[str, int] = {}

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
        return {str(row[id_header]).strip(): i + 2 for i, row in df.iterrows() if str(row.get(id_header, "")).strip()}

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


# ===========================================================================
# 1. Solenoide format: validator + parser + summary
# ===========================================================================

def test_solenoide_format_is_valid() -> None:
    assert is_valid_sensor_serial_number("solenoide-SOL001") is True


def test_solenoide_format_is_invalid_without_serial() -> None:
    assert is_valid_sensor_serial_number("solenoide-") is False


def test_sim_standalone_format_is_valid() -> None:
    assert is_valid_sensor_serial_number("sim-SIM001") is True


def test_sim_standalone_format_is_invalid_without_serial() -> None:
    assert is_valid_sensor_serial_number("sim-") is False


def test_sim_standalone_parse_sensor_assets() -> None:
    assets = parse_sensor_assets("sim-SIM001")
    assert len(assets) == 1
    asset, _ = assets[0]
    assert asset.asset_type == "sim"
    assert asset.serial == "SIM001"


def test_sim_standalone_summary_lines() -> None:
    lines = sensor_serial_number_summary_lines("sim-SIM001")
    assert any("SIM001" in line for line in lines)
    assert any("SIM individual" in line for line in lines)


def test_solenoide_parse_sensor_assets() -> None:
    assets = parse_sensor_assets("solenoide-SOL001")
    assert len(assets) == 1
    asset, assoc = assets[0]
    assert asset.asset_type == "solenoide"
    assert asset.serial == "SOL001"


def test_solenoide_summary_lines() -> None:
    lines = sensor_serial_number_summary_lines("solenoide-SOL001")
    assert any("SOL001" in line for line in lines)
    assert any("Solenoide" in line for line in lines)


# ===========================================================================
# 2. contacts.py helper functions
# ===========================================================================

def test_infer_sensor_root_type_uc501() -> None:
    assert _infer_sensor_root_type("uc501-UC001-T10-SIM001") == "uc501"


def test_infer_sensor_root_type_ug67() -> None:
    assert _infer_sensor_root_type("ug67-UG001-SIM900,em500-EM001") == "ug67"


def test_infer_sensor_root_type_solenoide() -> None:
    assert _infer_sensor_root_type("solenoide-SOL001") == "solenoide"


def test_infer_sensor_root_type_sim() -> None:
    assert _infer_sensor_root_type("sim-SIM001") == "sim"


def test_infer_sensor_root_type_empty_defaults_to_uc501() -> None:
    assert _infer_sensor_root_type("") == "uc501"


def test_extract_ug67_bundle() -> None:
    ug_sn, sim_sn = _extract_ug67_bundle("ug67-UG001-SIM900,em500-EM001")
    assert ug_sn == "UG001"
    assert sim_sn == "SIM900"


def test_extract_ug67_bundle_empty() -> None:
    ug_sn, sim_sn = _extract_ug67_bundle("")
    assert ug_sn == ""
    assert sim_sn == ""


def test_extract_solenoide_sn() -> None:
    assert _extract_solenoide_sn("solenoide-SOL001") == "SOL001"


def test_extract_solenoide_sn_empty() -> None:
    assert _extract_solenoide_sn("") == ""


def test_extract_sim_sn() -> None:
    assert _extract_sim_sn("sim-SIM001") == "SIM001"


def test_extract_sim_sn_empty() -> None:
    assert _extract_sim_sn("") == ""


def test_collect_all_serials_uc501() -> None:
    serials = _collect_all_serials_from_sensor_sn("uc501-UC001-T10-SIM001")
    assert "UC001" in serials
    assert "T10" in serials
    assert "SIM001" in serials
    assert len(serials) == 3


def test_collect_all_serials_ug67_with_children() -> None:
    serials = _collect_all_serials_from_sensor_sn("ug67-UG001-SIM900,em500-EM001,uc512-UC5001")
    assert "UG001" in serials
    assert "SIM900" in serials
    assert "EM001" in serials
    assert "UC5001" in serials


def test_collect_all_serials_solenoide() -> None:
    serials = _collect_all_serials_from_sensor_sn("solenoide-SOL001")
    assert serials == ["SOL001"]


# ===========================================================================
# 3. InventoryService.available_root_assets_for_history
# ===========================================================================

def test_available_filters_out_assigned_to_client() -> None:
    sheets = FakeSheets(inv_df=pd.DataFrame([
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A", location_type="cliente"),
        _row(inventory_id="uc-2", model="uc501", serial_number="UC-B", location_type="oficina"),
    ]))
    svc = InventoryService(sheets)
    options = svc.available_root_assets_for_history(("uc501",), inv_df=sheets.frames[INVENTORY_WORKSHEET_NAME])
    serials = [o.serial_number for o in options]
    assert "UC-A" not in serials
    assert "UC-B" in serials


def test_available_filters_out_open_history_serials() -> None:
    sheets = FakeSheets(inv_df=pd.DataFrame([
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A", location_type="por_definir"),
        _row(inventory_id="uc-2", model="uc501", serial_number="UC-B", location_type="por_definir"),
    ]))
    svc = InventoryService(sheets)
    open_serials = {"uc-a"}  # lowercase serial
    options = svc.available_root_assets_for_history(
        ("uc501",), open_serials=open_serials, inv_df=sheets.frames[INVENTORY_WORKSHEET_NAME]
    )
    serials = [o.serial_number for o in options]
    assert "UC-A" not in serials
    assert "UC-B" in serials


def test_available_includes_all_when_no_filter() -> None:
    sheets = FakeSheets(inv_df=pd.DataFrame([
        _row(inventory_id="ug-1", model="ug67", serial_number="UG-A"),
        _row(inventory_id="ug-2", model="ug67", serial_number="UG-B"),
    ]))
    svc = InventoryService(sheets)
    options = svc.available_root_assets_for_history(("ug67",), inv_df=sheets.frames[INVENTORY_WORKSHEET_NAME])
    assert len(options) == 2


def test_available_solenoide_filtered() -> None:
    sheets = FakeSheets(inv_df=pd.DataFrame([
        _row(inventory_id="sol-1", model="solenoide", serial_number="SOL-A", location_type="cliente"),
        _row(inventory_id="sol-2", model="solenoide", serial_number="SOL-B", location_type="oficina"),
    ]))
    svc = InventoryService(sheets)
    options = svc.available_root_assets_for_history(("solenoide",), inv_df=sheets.frames[INVENTORY_WORKSHEET_NAME])
    serials = [o.serial_number for o in options]
    assert "SOL-A" not in serials
    assert "SOL-B" in serials


# ===========================================================================
# 4. InventoryService.associations_for_root_asset
# ===========================================================================

def test_associations_uc501_has_sim_and_probe() -> None:
    sheets = FakeSheets(inv_df=pd.DataFrame([
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-001",
             associated_sim_inventory_id="sim-1", associated_probe_inventory_id="t10-1"),
        _row(inventory_id="sim-1", model="sim", serial_number="SIM-X"),
        _row(inventory_id="t10-1", model="teros10", serial_number="T10-X"),
    ]))
    svc = InventoryService(sheets)
    assoc = svc.associations_for_root_asset("uc-1", inv_df=sheets.frames[INVENTORY_WORKSHEET_NAME])
    assert assoc.sim is not None
    assert assoc.sim.serial_number == "SIM-X"
    assert assoc.probe is not None
    assert assoc.probe.serial_number == "T10-X"
    assert assoc.sensors == ()


def test_associations_ug67_has_sim_and_children() -> None:
    sheets = FakeSheets(inv_df=pd.DataFrame([
        _row(inventory_id="ug-1", model="ug67", serial_number="UG-001",
             associated_sim_inventory_id="sim-2"),
        _row(inventory_id="sim-2", model="sim", serial_number="SIM-200"),
        _row(inventory_id="em5-1", model="em500", serial_number="EM-001",
             associated_gateway_inventory_id="ug-1"),
        _row(inventory_id="uc5-1", model="uc512", serial_number="UC512-001",
             associated_gateway_inventory_id="ug-1"),
    ]))
    svc = InventoryService(sheets)
    assoc = svc.associations_for_root_asset("ug-1", inv_df=sheets.frames[INVENTORY_WORKSHEET_NAME])
    assert assoc.sim is not None
    assert assoc.sim.serial_number == "SIM-200"
    assert len(assoc.sensors) == 2
    child_serials = {c.serial_number for c in assoc.sensors}
    assert child_serials == {"EM-001", "UC512-001"}


def test_associations_no_sim_returns_none() -> None:
    sheets = FakeSheets(inv_df=pd.DataFrame([
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-001"),
    ]))
    svc = InventoryService(sheets)
    assoc = svc.associations_for_root_asset("uc-1", inv_df=sheets.frames[INVENTORY_WORKSHEET_NAME])
    assert assoc.sim is None
    assert assoc.probe is None
    assert assoc.sensors == ()


# ===========================================================================
# 5. HistoryService.open_asset_serials
# ===========================================================================

def test_open_asset_serials_includes_open_entries() -> None:
    sensor_rows = [
        _sensor_row(historial_sensor_id="h1", sensor_serial_number="uc501-UC001-T10-SIM001", estado_cierre_sensor="abierto"),
    ]
    sheets = FakeSheets(sensor_rows=sensor_rows)
    hist = HistoryService(sheets)
    open_set = hist.open_asset_serials()
    assert "uc001" in open_set
    assert "sim001" in open_set
    assert "t10" in open_set


def test_open_asset_serials_excludes_closed_entries() -> None:
    sensor_rows = [
        _sensor_row(historial_sensor_id="h1", sensor_serial_number="uc501-UC001-T10-SIM001", estado_cierre_sensor="cerrado"),
    ]
    sheets = FakeSheets(sensor_rows=sensor_rows)
    hist = HistoryService(sheets)
    open_set = hist.open_asset_serials()
    assert "uc001" not in open_set


def test_open_asset_serials_excludes_the_editing_record() -> None:
    sensor_rows = [
        _sensor_row(historial_sensor_id="h1", sensor_serial_number="uc501-UC001-T10-SIM001", estado_cierre_sensor="abierto"),
    ]
    sheets = FakeSheets(sensor_rows=sensor_rows)
    hist = HistoryService(sheets)
    open_set = hist.open_asset_serials(exclude_historial_id="h1")
    # Record h1 excluded → serial should not be blocked
    assert "uc001" not in open_set


def test_open_asset_serials_solenoide_open() -> None:
    sensor_rows = [
        _sensor_row(historial_sensor_id="h1", sensor_serial_number="solenoide-SOL001", estado_cierre_sensor="abierto"),
    ]
    sheets = FakeSheets(sensor_rows=sensor_rows)
    hist = HistoryService(sheets)
    open_set = hist.open_asset_serials()
    assert "sol001" in open_set


def test_open_sensor_assignment_rows_for_serials_uses_open_remaining_owner() -> None:
    sensor_rows = [
        _sensor_row(
            historial_sensor_id="old",
            contact_id="cid-old",
            nombre_cliente="Old",
            fecha_inicio="01/01/2025",
            sensor_serial_number='ug67-"6222E3615254"-SIM900',
            estado_cierre_sensor="abierto",
            updated_at="01/01/2025",
        ),
        _sensor_row(
            historial_sensor_id="new",
            contact_id="cid-new",
            nombre_cliente="New",
            fecha_inicio="01/02/2025",
            sensor_serial_number="ug67-6222E3615254-SIM900",
            estado_cierre_sensor="abierto",
            updated_at="01/02/2025",
        ),
        _sensor_row(
            historial_sensor_id="closed",
            contact_id="cid-closed",
            nombre_cliente="Closed",
            fecha_inicio="01/03/2025",
            sensor_serial_number="ug67-6222E3615254-SIM900",
            estado_cierre_sensor="cerrado",
            updated_at="01/03/2025",
        ),
    ]
    sheets = FakeSheets(sensor_rows=sensor_rows)
    hist = HistoryService(sheets)
    assignments = hist.open_sensor_assignment_rows_for_serials(["6222E3615254"], exclude_historial_sensor_id="old")
    owner = assignments["6222e3615254"]
    assert owner["historial_sensor_id"] == "new"
    assert owner["contact_id"] == "cid-new"


# ===========================================================================
# 6. _collect_all_serials + inventory sync (unit-level)
# ===========================================================================

def test_sync_ug67_marks_all_serials_as_client() -> None:
    inv_df = pd.DataFrame([
        _row(inventory_id="ug-1", model="ug67", serial_number="UG001", location_type="oficina"),
        _row(inventory_id="sim-1", model="sim", serial_number="SIM900", location_type="oficina"),
        _row(inventory_id="em-1", model="em500", serial_number="EM001", location_type="oficina"),
    ])
    sheets = FakeSheets(inv_df=inv_df)
    svc = InventoryService(sheets)
    serials = _collect_all_serials_from_sensor_sn("ug67-UG001-SIM900,em500-EM001")
    assert set(serials) == {"UG001", "SIM900", "EM001"}
    svc.set_location_for_serials(serials, location_type="cliente", location_contact_id="cid-123")
    result = sheets.frames[INVENTORY_WORKSHEET_NAME]
    for _, r in result.iterrows():
        assert r["location_type"] == "cliente"
        assert r["location_contact_id"] == "cid-123"


def test_sync_solenoide_marks_serial_as_client() -> None:
    inv_df = pd.DataFrame([
        _row(inventory_id="sol-1", model="solenoide", serial_number="SOL001", location_type="oficina"),
    ])
    sheets = FakeSheets(inv_df=inv_df)
    svc = InventoryService(sheets)
    serials = _collect_all_serials_from_sensor_sn("solenoide-SOL001")
    assert serials == ["SOL001"]
    svc.set_location_for_serials(serials, location_type="cliente", location_contact_id="cid-456")
    result = sheets.frames[INVENTORY_WORKSHEET_NAME]
    assert result.iloc[0]["location_type"] == "cliente"


def test_sync_closing_ug67_releases_inventory() -> None:
    inv_df = pd.DataFrame([
        _row(inventory_id="ug-1", model="ug67", serial_number="UG001", location_type="cliente", location_contact_id="cid-1"),
        _row(inventory_id="sim-1", model="sim", serial_number="SIM900", location_type="cliente", location_contact_id="cid-1"),
    ])
    sheets = FakeSheets(inv_df=inv_df)
    svc = InventoryService(sheets)
    serials = _collect_all_serials_from_sensor_sn("ug67-UG001-SIM900")
    svc.set_location_for_serials(serials, location_type="por_definir", location_contact_id="")
    result = sheets.frames[INVENTORY_WORKSHEET_NAME]
    for _, r in result.iterrows():
        assert r["location_type"] == "por_definir"
        assert r["location_contact_id"] == ""
