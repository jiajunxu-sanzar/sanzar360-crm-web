from __future__ import annotations

import pandas as pd

from config.settings import INVENTORY_HEADERS, INVENTORY_MODEL_FIELD_HEADERS, INVENTORY_MODEL_FIELDS_WORKSHEET_NAME, INVENTORY_WORKSHEET_NAME
from services.inventory_service import (
    InventoryService,
    format_inventory_serial_with_quotes,
    normalize_field_key,
    normalize_inventory_serial_for_match,
    normalize_model_name,
)


class FakeSheets:
    def __init__(self) -> None:
        self.frames: dict[str, pd.DataFrame] = {
            INVENTORY_WORKSHEET_NAME: pd.DataFrame(columns=list(INVENTORY_HEADERS)),
            INVENTORY_MODEL_FIELDS_WORKSHEET_NAME: pd.DataFrame(columns=list(INVENTORY_MODEL_FIELD_HEADERS)),
        }
        self.read_calls = 0

    def get_or_create_worksheet(self, name: str, headers: list[str]) -> None:
        if name not in self.frames:
            self.frames[name] = pd.DataFrame(columns=headers)

    def read_worksheet_df(self, name: str, headers: list[str]) -> pd.DataFrame:
        self.read_calls += 1
        df = self.frames.get(name, pd.DataFrame(columns=headers)).copy()
        for h in headers:
            if h not in df.columns:
                df[h] = ""
        return df[headers].fillna("").astype(str)

    def row_numbers_by_id(self, name: str, id_header: str) -> dict[str, int]:
        df = self.frames[name].fillna("").astype(str)
        out: dict[str, int] = {}
        for i, row in df.iterrows():
            value = str(row.get(id_header, "")).strip()
            if value:
                out[value] = i + 2
        return out

    def append_worksheet_row(self, name: str, headers: list[str], row: dict[str, str]) -> None:
        self.frames[name] = pd.concat([self.frames[name], pd.DataFrame([{h: str(row.get(h, "") or "") for h in headers}])], ignore_index=True)

    def update_worksheet_row(self, name: str, headers: list[str], row_num: int, row: dict[str, str]) -> None:
        idx = max(0, row_num - 2)
        df = self.frames[name].copy()
        for h in headers:
            df.at[idx, h] = str(row.get(h, "") or "")
        self.frames[name] = df

    def write_worksheet_df(self, name: str, df: pd.DataFrame, headers: list[str]) -> None:
        self.frames[name] = df[headers].fillna("").astype(str).copy()


def _row_with_headers(**kwargs: str) -> dict[str, str]:
    return {h: str(kwargs.get(h, "") or "") for h in INVENTORY_HEADERS}


def test_normalize_helpers() -> None:
    assert normalize_model_name(" Teros-10 ") == "teros10"
    assert normalize_model_name("Teros 10") == "teros10"
    assert normalize_field_key(" Associated_SIM_Inventory_ID ") == "associated_sim_inventory_id"
    assert normalize_inventory_serial_for_match('"6222E3615254 "') == "6222e3615254"
    assert normalize_inventory_serial_for_match("6222E3615254") == "6222e3615254"


def test_format_inventory_serial_with_quotes() -> None:
    assert format_inventory_serial_with_quotes("6222E3615254") == '"6222E3615254"'
    assert format_inventory_serial_with_quotes('"6222E3615254"') == '"6222E3615254"'
    assert format_inventory_serial_with_quotes("'6222E3615254'") == "'6222E3615254'"
    assert format_inventory_serial_with_quotes("  ") == ""
    assert format_inventory_serial_with_quotes("") == ""


def test_asset_options_by_models_handles_model_variants() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame(
        [
            _row_with_headers(inventory_id="i1", model="teros10", serial_number="T10-A"),
            _row_with_headers(inventory_id="i2", model="Teros 10", serial_number="T10-B"),
            _row_with_headers(inventory_id="i3", model="TEROS-10", serial_number="T10-C"),
            _row_with_headers(inventory_id="i4", model="sim", serial_number="SIM-1"),
        ]
    )
    options = svc.asset_options_by_models(("teros10",))
    serials = [x.serial_number for x in options]
    assert sorted(serials) == ["T10-A", "T10-B", "T10-C"]


def test_upsert_inventory_preserves_created_at_on_update() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    inv_id = svc.upsert_inventory(
        _row_with_headers(inventory_id="inv-1", model="uc501", serial_number="UC-1", created_at="01/01/2024")
    )
    assert inv_id == "inv-1"
    svc.upsert_inventory(
        _row_with_headers(inventory_id="inv-1", model="uc501", serial_number="UC-1-updated", created_at="")
    )
    saved = sheets.frames[INVENTORY_WORKSHEET_NAME].fillna("").astype(str)
    row = saved[saved["inventory_id"] == "inv-1"].iloc[0]
    assert row["created_at"] == "01/01/2024"
    assert row["serial_number"] == "UC-1-updated"


def test_upsert_model_field_matches_normalized_keys() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    svc.upsert_model_field(
        {
            "model": "UC501",
            "field_key": "Associated_SIM_Inventory_ID",
            "field_label": "SIM",
            "field_type": "text",
            "required": "FALSE",
            "options_csv": "",
            "help_text": "",
            "order_index": "1",
            "active": "TRUE",
            "created_at": "",
            "updated_at": "",
        }
    )
    svc.upsert_model_field(
        {
            "model": " uc501 ",
            "field_key": "associated_sim_inventory_id",
            "field_label": "SIM updated",
            "field_type": "text",
            "required": "FALSE",
            "options_csv": "",
            "help_text": "",
            "order_index": "2",
            "active": "TRUE",
            "created_at": "",
            "updated_at": "",
        }
    )
    df = sheets.frames[INVENTORY_MODEL_FIELDS_WORKSHEET_NAME].fillna("").astype(str)
    assert len(df) == 1
    assert df.iloc[0]["field_label"] == "SIM updated"


def test_delete_model_fields_hard_removes_only_target_model() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_MODEL_FIELDS_WORKSHEET_NAME] = pd.DataFrame(
        [
            {"model": "uc501", "field_key": "serial_number"},
            {"model": "UC501", "field_key": "brand"},
            {"model": "sim", "field_key": "serial_number"},
        ]
    )
    removed = svc.delete_model_fields_hard("uc501")
    assert removed == 2
    left = sheets.frames[INVENTORY_MODEL_FIELDS_WORKSHEET_NAME].fillna("").astype(str)
    assert set(left["model"].str.lower().tolist()) == {"sim"}


def test_count_inventory_by_model_uses_normalized_match() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame(
        [
            _row_with_headers(inventory_id="i1", model="teros10", serial_number="T1"),
            _row_with_headers(inventory_id="i2", model="Teros 10", serial_number="T2"),
            _row_with_headers(inventory_id="i3", model="sim", serial_number="S1"),
        ]
    )
    assert svc.count_inventory_by_model("TEROS-10") == 2


def test_delete_inventory_by_id_removes_exact_row() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame(
        [
            _row_with_headers(inventory_id="i1", model="sim", serial_number="S1"),
            _row_with_headers(inventory_id="i2", model="teros10", serial_number="T1"),
        ]
    )
    deleted = svc.delete_inventory_by_id("i1")
    assert deleted is True
    left = sheets.frames[INVENTORY_WORKSHEET_NAME].fillna("").astype(str)
    assert left["inventory_id"].tolist() == ["i2"]


def test_delete_inventory_by_id_returns_false_when_missing() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame(
        [
            _row_with_headers(inventory_id="i1", model="sim", serial_number="S1"),
        ]
    )
    deleted = svc.delete_inventory_by_id("missing-id")
    assert deleted is False
    left = sheets.frames[INVENTORY_WORKSHEET_NAME].fillna("").astype(str)
    assert left["inventory_id"].tolist() == ["i1"]


def test_delete_inventory_by_id_uses_injected_df_without_extra_reads() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    inv_df = pd.DataFrame(
        [
            _row_with_headers(inventory_id="i1", model="sim", serial_number="S1"),
            _row_with_headers(inventory_id="i2", model="teros10", serial_number="T1"),
        ]
    )
    sheets.frames[INVENTORY_WORKSHEET_NAME] = inv_df.copy()
    before_reads = sheets.read_calls
    deleted = svc.delete_inventory_by_id("i2", inv_df=inv_df)
    after_reads = sheets.read_calls
    assert deleted is True
    assert after_reads == before_reads


def test_check_association_gateway_allows_multiple_sensors_same_ug67() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame(
        [
            _row_with_headers(inventory_id="ug-1", model="ug67", serial_number="UG-A"),
            _row_with_headers(
                inventory_id="em-1",
                model="em500",
                serial_number="EM-A",
                associated_gateway_inventory_id="ug-1",
            ),
        ]
    )
    conflicts = svc.check_association_conflicts(
        _row_with_headers(
            inventory_id="em-2",
            model="em500",
            serial_number="EM-B",
            associated_gateway_inventory_id="ug-1",
        )
    )
    assert conflicts == []


def test_check_association_gateway_must_be_ug67() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame(
        [
            _row_with_headers(inventory_id="uc-1", model="uc501", serial_number="UC-A"),
        ]
    )
    conflicts = svc.check_association_conflicts(
        _row_with_headers(
            inventory_id="em-1",
            model="em500",
            serial_number="EM-A",
            associated_gateway_inventory_id="uc-1",
        )
    )
    assert len(conflicts) == 1
    assert "debe ser un UG67" in conflicts[0]


def test_set_location_for_serials_matches_quoted_inventory_serial() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame(
        [
            _row_with_headers(
                inventory_id="ug-1",
                model="ug67",
                serial_number='"6222E3615254"',
                location_type="oficina",
            ),
        ]
    )
    svc.set_location_for_serials(
        ["6222E3615254"],
        location_type="cliente",
        location_contact_id="cid-primaram",
        location_detail="Primaram",
    )
    row = sheets.frames[INVENTORY_WORKSHEET_NAME].iloc[0]
    assert row["location_type"] == "cliente"
    assert row["location_contact_id"] == "cid-primaram"
    assert row["location_detail"] == "Primaram"


def test_available_root_assets_blocks_quoted_serial_when_open_serial_unquoted() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame(
        [
            _row_with_headers(
                inventory_id="ug-1",
                model="ug67",
                serial_number='"6222E3615254"',
                location_type="oficina",
            ),
        ]
    )
    options = svc.available_root_assets_for_history(
        ("ug67",),
        open_serials={"6222e3615254"},
        inv_df=sheets.frames[INVENTORY_WORKSHEET_NAME],
    )
    assert options == []


def test_reconcile_locations_releases_serial_without_open_assignment() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame(
        [
            _row_with_headers(
                inventory_id="ug-1",
                model="ug67",
                serial_number='"6222E3615254"',
                location_type="cliente",
                location_contact_id="cid-old",
                location_detail="Old Client",
            ),
        ]
    )
    svc.reconcile_locations_for_serials(["6222E3615254"], {}, default_location_type="por_definir")
    row = sheets.frames[INVENTORY_WORKSHEET_NAME].iloc[0]
    assert row["location_type"] == "por_definir"
    assert row["location_contact_id"] == ""
    assert row["location_detail"] == ""


def test_reconcile_locations_preserves_remaining_open_assignment() -> None:
    sheets = FakeSheets()
    svc = InventoryService(sheets)
    sheets.frames[INVENTORY_WORKSHEET_NAME] = pd.DataFrame(
        [
            _row_with_headers(
                inventory_id="ug-1",
                model="ug67",
                serial_number='"6222E3615254"',
                location_type="cliente",
                location_contact_id="cid-old",
                location_detail="Old Client",
            ),
        ]
    )
    svc.reconcile_locations_for_serials(
        ["6222E3615254"],
        {"6222e3615254": {"contact_id": "cid-new", "nombre_cliente": "New Client"}},
    )
    row = sheets.frames[INVENTORY_WORKSHEET_NAME].iloc[0]
    assert row["location_type"] == "cliente"
    assert row["location_contact_id"] == "cid-new"
    assert row["location_detail"] == "New Client"
