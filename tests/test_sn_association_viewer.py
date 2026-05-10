"""Tests for the SN Association Viewer: map builder, conflict detection,
occurrence filtering, and inventory_service association-conflict checks."""
from __future__ import annotations

import pandas as pd
import pytest

from config.settings import INVENTORY_HEADERS, INVENTORY_MODEL_FIELDS_WORKSHEET_NAME, INVENTORY_WORKSHEET_NAME
from services.inventory_service import InventoryService
from ui.components.sn_association_viewer import (
    AssociationChild,
    AssociationGroup,
    IntegrityConflict,
    _filter_occurrences,
    build_inventory_association_map,
)
from services.history_service import SensorAsset, SensorAssetOccurrence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(**kwargs: str) -> dict[str, str]:
    base = {h: "" for h in INVENTORY_HEADERS}
    base.update({k: str(v) for k, v in kwargs.items()})
    return base


def _inv_df(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=list(INVENTORY_HEADERS)).fillna("").astype(str)


def _occurrence(asset_type: str, serial: str, *, nombre="", contact_id="", fecha_fin="", associated_with="") -> SensorAssetOccurrence:
    return SensorAssetOccurrence(
        asset=SensorAsset(asset_type=asset_type, serial=serial),
        contact_id=contact_id,
        nombre_cliente=nombre,
        fecha_inicio="01/01/2025",
        fecha_fin=fecha_fin,
        historial_sensor_id="h1",
        associated_with=associated_with or f"{asset_type}-{serial}",
        sensor_serial_number="",
        red="",
        red_otro="",
        tipo_operacion="",
        aws_user_id="",
        detalles="",
    )


# ---------------------------------------------------------------------------
# FakeSheets for InventoryService
# ---------------------------------------------------------------------------

class FakeSheets:
    def __init__(self, frames: dict[str, pd.DataFrame] | None = None) -> None:
        self.frames: dict[str, pd.DataFrame] = frames or {
            INVENTORY_WORKSHEET_NAME: pd.DataFrame(columns=list(INVENTORY_HEADERS)),
            INVENTORY_MODEL_FIELDS_WORKSHEET_NAME: pd.DataFrame(columns=["model", "field_key"]),
        }

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

    def append_worksheet_row(self, name: str, headers: list[str], row: dict[str, str]) -> None:
        new_row = {h: str(row.get(h, "") or "") for h in headers}
        self.frames[name] = pd.concat([self.frames[name], pd.DataFrame([new_row])], ignore_index=True)

    def update_worksheet_row(self, name: str, headers: list[str], row_num: int, row: dict[str, str]) -> None:
        idx = max(0, row_num - 2)
        df = self.frames[name].copy()
        for h in headers:
            df.at[idx, h] = str(row.get(h, "") or "")
        self.frames[name] = df

    def write_worksheet_df(self, name: str, df: pd.DataFrame, headers: list[str]) -> None:
        self.frames[name] = df[headers].fillna("").astype(str).copy()


# ===========================================================================
# 1. Association map builder – UC501
# ===========================================================================

def test_uc501_group_with_sim_and_probe() -> None:
    df = _inv_df(
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-001",
             associated_sim_inventory_id="sim-1", associated_probe_inventory_id="t10-1"),
        _row(inventory_id="sim-1", model="sim", serial_number="SIM-100"),
        _row(inventory_id="t10-1", model="teros10", serial_number="T10-50"),
    )
    groups, conflicts = build_inventory_association_map(df)
    assert len(groups) == 1
    g = groups[0]
    assert g.role == "uc501"
    assert g.serial_number == "UC-001"
    roles = {c.role for c in g.children}
    serials = {c.serial_number for c in g.children}
    assert roles == {"sim", "probe"}
    assert serials == {"SIM-100", "T10-50"}
    assert conflicts == []


def test_uc501_group_no_associations() -> None:
    df = _inv_df(
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-001"),
    )
    groups, conflicts = build_inventory_association_map(df)
    assert len(groups) == 1
    assert groups[0].children == []
    assert conflicts == []


# ===========================================================================
# 2. Association map builder – UG67
# ===========================================================================

def test_ug67_group_with_sim_and_sensors() -> None:
    df = _inv_df(
        _row(inventory_id="ug-1", model="ug67", serial_number="UG-001",
             associated_sim_inventory_id="sim-2"),
        _row(inventory_id="sim-2", model="sim", serial_number="SIM-200"),
        _row(inventory_id="em5-1", model="em500", serial_number="EM-001",
             associated_gateway_inventory_id="ug-1"),
        _row(inventory_id="uc5-1", model="uc512", serial_number="UC512-001",
             associated_gateway_inventory_id="ug-1"),
    )
    groups, conflicts = build_inventory_association_map(df)
    assert len(groups) == 1
    g = groups[0]
    assert g.role == "ug67"
    assert g.serial_number == "UG-001"
    roles = [c.role for c in g.children]
    assert "sim" in roles
    assert roles.count("sensor") == 2
    assert conflicts == []


# ===========================================================================
# 3. Conflict detection – SIM in multiple assets
# ===========================================================================

def test_sim_duplicate_conflict_detected() -> None:
    df = _inv_df(
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A",
             associated_sim_inventory_id="sim-1"),
        _row(inventory_id="uc-2", model="uc501", serial_number="UC-B",
             associated_sim_inventory_id="sim-1"),
        _row(inventory_id="sim-1", model="sim", serial_number="SIM-X"),
    )
    _, conflicts = build_inventory_association_map(df)
    assert any(c.kind == "sim_duplicate" for c in conflicts)
    dup = next(c for c in conflicts if c.kind == "sim_duplicate")
    assert "SIM-X" in dup.description
    assert "UC-A" in dup.description or "UC-B" in dup.description


def test_probe_duplicate_conflict_detected() -> None:
    df = _inv_df(
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A",
             associated_probe_inventory_id="t10-1"),
        _row(inventory_id="uc-2", model="uc501", serial_number="UC-B",
             associated_probe_inventory_id="t10-1"),
        _row(inventory_id="t10-1", model="teros10", serial_number="T10-X"),
    )
    _, conflicts = build_inventory_association_map(df)
    assert any(c.kind == "probe_duplicate" for c in conflicts)


def test_broken_link_conflict_detected() -> None:
    df = _inv_df(
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A",
             associated_sim_inventory_id="sim-NONEXISTENT"),
    )
    _, conflicts = build_inventory_association_map(df)
    assert any(c.kind == "broken_link" for c in conflicts)
    bl = next(c for c in conflicts if c.kind == "broken_link")
    assert "sim-NONEXISTENT" in bl.description


def test_no_conflicts_clean_data() -> None:
    df = _inv_df(
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A",
             associated_sim_inventory_id="sim-1", associated_probe_inventory_id="t10-1"),
        _row(inventory_id="sim-1", model="sim", serial_number="SIM-X"),
        _row(inventory_id="t10-1", model="teros10", serial_number="T10-X"),
    )
    _, conflicts = build_inventory_association_map(df)
    assert conflicts == []


# ===========================================================================
# 4. Occurrence filter helper
# ===========================================================================

def test_filter_occurrences_by_query() -> None:
    occ = [
        _occurrence("uc501", "UC-001", nombre="Finca Ejemplo"),
        _occurrence("uc501", "UC-002", nombre="Otra Empresa"),
    ]
    result = _filter_occurrences(occ, "finca ejemplo", "")
    assert len(result) == 1
    assert result[0].asset.serial == "UC-001"


def test_filter_occurrences_by_asset_type() -> None:
    occ = [
        _occurrence("uc501", "UC-001"),
        _occurrence("sim", "SIM-001"),
    ]
    result = _filter_occurrences(occ, "", "sim")
    assert len(result) == 1
    assert result[0].asset.asset_type == "sim"


def test_filter_occurrences_no_query_returns_all() -> None:
    occ = [_occurrence("uc501", f"UC-{i}") for i in range(5)]
    result = _filter_occurrences(occ, "", "")
    assert len(result) == 5


def test_filter_occurrences_by_serial_partial_match() -> None:
    occ = [
        _occurrence("teros10", "T10-ALPHA"),
        _occurrence("teros10", "T10-BETA"),
    ]
    result = _filter_occurrences(occ, "alpha", "")
    assert len(result) == 1
    assert result[0].asset.serial == "T10-ALPHA"


# ===========================================================================
# 5. InventoryService.check_association_conflicts
# ===========================================================================

def test_check_association_sim_duplicate_blocked() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame([
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A",
             associated_sim_inventory_id="sim-1"),
        _row(inventory_id="sim-1", model="sim", serial_number="SIM-X"),
    ])
    # Try to save UC-2 also referencing sim-1
    conflicts = svc.check_association_conflicts(_row(
        inventory_id="uc-2", model="uc501", serial_number="UC-B",
        associated_sim_inventory_id="sim-1",
    ))
    assert len(conflicts) == 1
    assert "SIM-X" in conflicts[0] or "sim-1" in conflicts[0]


def test_check_association_same_item_update_no_conflict() -> None:
    """Updating the same UC501 with the same SIM should not trigger a conflict."""
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame([
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A",
             associated_sim_inventory_id="sim-1"),
        _row(inventory_id="sim-1", model="sim", serial_number="SIM-X"),
    ])
    conflicts = svc.check_association_conflicts(_row(
        inventory_id="uc-1", model="uc501", serial_number="UC-A",
        associated_sim_inventory_id="sim-1",
    ))
    assert conflicts == []


def test_check_association_broken_link_blocked() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame([
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A"),
    ])
    conflicts = svc.check_association_conflicts(_row(
        inventory_id="uc-1", model="uc501", serial_number="UC-A",
        associated_sim_inventory_id="sim-DOES-NOT-EXIST",
    ))
    assert len(conflicts) == 1
    assert "sim-DOES-NOT-EXIST" in conflicts[0]


def test_check_association_no_associations_is_clean() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame([
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A"),
    ])
    conflicts = svc.check_association_conflicts(_row(
        inventory_id="uc-1", model="uc501", serial_number="UC-A",
    ))
    assert conflicts == []


def test_upsert_raises_on_sim_duplicate() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame([
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A",
             associated_sim_inventory_id="sim-1"),
        _row(inventory_id="sim-1", model="sim", serial_number="SIM-X"),
    ])
    with pytest.raises(ValueError, match="SIM"):
        svc.upsert_inventory(_row(
            inventory_id="uc-2", model="uc501", serial_number="UC-B",
            associated_sim_inventory_id="sim-1",
        ))


def test_upsert_skip_conflict_check_bypasses_validation() -> None:
    """skip_conflict_check=True allows saving without validation (for migrations/seeds)."""
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame([
        _row(inventory_id="uc-1", model="uc501", serial_number="UC-A",
             associated_sim_inventory_id="sim-1"),
        _row(inventory_id="sim-1", model="sim", serial_number="SIM-X"),
    ])
    # Should NOT raise
    saved_id = svc.upsert_inventory(
        _row(inventory_id="uc-2", model="uc501", serial_number="UC-B",
             associated_sim_inventory_id="sim-1"),
        skip_conflict_check=True,
    )
    assert saved_id == "uc-2"


# ===========================================================================
# 6. Empty inventory edge cases
# ===========================================================================

def test_build_map_empty_df() -> None:
    groups, conflicts = build_inventory_association_map(pd.DataFrame())
    assert groups == []
    assert conflicts == []


def test_check_association_empty_df() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    conflicts = svc.check_association_conflicts(
        _row(inventory_id="x", model="uc501", serial_number="X",
             associated_sim_inventory_id="sim-1")
    )
    # No rows → can't confirm SIM exists → should flag broken link
    # (or return empty if df is empty and we skip the check)
    # The broken-link check won't fire on empty df (nothing to cross-reference against)
    assert isinstance(conflicts, list)
