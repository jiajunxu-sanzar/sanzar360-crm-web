from __future__ import annotations

import pandas as pd
import streamlit as st

if not hasattr(st, "dialog"):
    st.dialog = lambda *_args, **_kwargs: (lambda fn: fn)  # type: ignore[attr-defined]
from pages.inventory import _editable_field_keys, _inventory_row_by_id, _model_field_keys, _reconcile_selected_inventory_id


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


def test_editable_field_keys_excludes_audit_fields() -> None:
    out = _editable_field_keys(["inventory_id", "model", "serial_number", "created_at", "updated_at"])
    assert out == ["model", "serial_number"]


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
