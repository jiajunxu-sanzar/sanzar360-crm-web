from __future__ import annotations

import pandas as pd

from pages.inventory import (
    SERIAL_NUMBER_QUOTES_HELP,
    UG67_SERIAL_NUMBER_QUOTES_HELP,
    _editable_field_keys,
    _field_help,
    _field_label,
    _form_field_keys,
    _inventory_row_by_id,
    _model_field_keys,
    _reconcile_selected_inventory_id,
    _row_contains_query,
)


def test_ug67_create_serial_number_shows_quotes_hint() -> None:
    assert _field_label("serial_number", model="ug67", mode="create") == "Serial number *"
    assert _field_help("serial_number", model="ug67", mode="create") == UG67_SERIAL_NUMBER_QUOTES_HELP
    assert _field_help("serial_number", model="ug67", mode="create") == SERIAL_NUMBER_QUOTES_HELP


def test_ug67_edit_serial_number_has_no_quotes_hint() -> None:
    assert _field_label("serial_number", model="ug67", mode="edit") == "Serial number"
    assert _field_help("serial_number", model="ug67", mode="edit") is None


def test_em500_create_serial_number_shows_quotes_hint() -> None:
    assert _field_label("serial_number", model="em500", mode="create") == "Serial number *"
    assert _field_help("serial_number", model="em500", mode="create") == SERIAL_NUMBER_QUOTES_HELP


def test_em500_edit_serial_number_has_no_quotes_hint() -> None:
    assert _field_label("serial_number", model="em500", mode="edit") == "Serial number"
    assert _field_help("serial_number", model="em500", mode="edit") is None


def test_other_models_serial_number_has_no_quotes_hint() -> None:
    assert _field_label("serial_number", model="uc501", mode="create") == "Serial number"
    assert _field_help("serial_number", model="uc501", mode="create") is None


def test_model_field_keys_sorts_order_index_as_numeric() -> None:
    model_fields_df = pd.DataFrame(
        [
            {"model": "uc501", "field_key": "brand", "order_index": "10", "active": "TRUE"},
            {"model": "uc501", "field_key": "serial_number", "order_index": "2", "active": "TRUE"},
            {"model": "uc501", "field_key": "supplier", "order_index": "1", "active": "TRUE"},
        ]
    )
    result = _model_field_keys("uc501", model_fields_df)
    assert result[:3] == ["supplier", "serial_number", "brand"]


def test_model_field_keys_adds_em500_gateway_when_catalog_missing() -> None:
    model_fields_df = pd.DataFrame(
        [
            {"model": "em500", "field_key": "serial_number", "order_index": "1", "active": "TRUE"},
            {"model": "em500", "field_key": "brand", "order_index": "2", "active": "TRUE"},
        ]
    )
    result = _model_field_keys("em500", model_fields_df)
    assert "associated_gateway_inventory_id" in result


def test_model_field_keys_hides_unused_em500_fields() -> None:
    model_fields_df = pd.DataFrame(
        [
            {"model": "em500", "field_key": "serial_number", "order_index": "1", "active": "TRUE"},
            {"model": "em500", "field_key": "gateway_config_name", "order_index": "2", "active": "TRUE"},
            {"model": "em500", "field_key": "ui_password", "order_index": "3", "active": "TRUE"},
        ]
    )
    result = _model_field_keys("em500", model_fields_df)
    assert "gateway_config_name" not in result
    assert "ui_password" not in result


def test_editable_field_keys_excludes_audit_fields() -> None:
    out = _editable_field_keys(["inventory_id", "model", "serial_number", "created_at", "updated_at"])
    assert out == ["model", "serial_number"]


def test_form_field_keys_hides_location_fields_only_in_edit_mode() -> None:
    fields = ["serial_number", "location_type", "location_contact_id", "brand"]
    assert _form_field_keys(fields, mode="create") == fields
    assert _form_field_keys(fields, mode="edit") == ["serial_number", "brand"]


def test_inventory_row_by_id_finds_exact_row() -> None:
    df = pd.DataFrame(
        [
            {"inventory_id": "a1", "model": "sim", "serial_number": "SIM-01"},
            {"inventory_id": "a2", "model": "teros10", "serial_number": "TE-01"},
        ]
    )
    row = _inventory_row_by_id(df, "a2")
    assert row is not None
    assert row["model"] == "teros10"
    assert row["serial_number"] == "TE-01"


def test_reconcile_selected_inventory_id_clears_non_visible() -> None:
    assert _reconcile_selected_inventory_id("inv-2", {"inv-1", "inv-3"}) == ""
    assert _reconcile_selected_inventory_id("inv-2", {"inv-2", "inv-3"}) == "inv-2"


def _sample_inv_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"inventory_id": "a1", "model": "sim", "serial_number": "SIM-01", "sim_eid_number": "8988"},
            {"inventory_id": "a2", "model": "teros10", "serial_number": "TE-01", "sim_eid_number": ""},
            {"inventory_id": "a3", "model": "uc501", "serial_number": "UC-7", "sim_eid_number": ""},
        ]
    )


def test_row_contains_query_empty_query_keeps_all_rows() -> None:
    df = _sample_inv_df()
    mask = _row_contains_query(df, "")
    assert mask.tolist() == [True, True, True]


def test_row_contains_query_matches_any_column_case_insensitive() -> None:
    df = _sample_inv_df()
    by_model = _row_contains_query(df, "teros")
    assert by_model.tolist() == [False, True, False]
    by_sn = _row_contains_query(df, "uc-7")
    assert by_sn.tolist() == [False, False, True]
    by_eid_partial = _row_contains_query(df, "8988")
    assert by_eid_partial.tolist() == [True, False, False]


def test_row_contains_query_returns_empty_mask_for_empty_df() -> None:
    mask = _row_contains_query(pd.DataFrame(columns=["model", "serial_number"]), "anything")
    assert mask.empty
    assert mask.dtype == bool
