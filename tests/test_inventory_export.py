"""Tests for inventory association map PDF export helpers."""
from __future__ import annotations

import pandas as pd

from config.settings import INVENTORY_HEADERS
from services.inventory_export import build_association_map_pdf_bytes, collect_individual_inventory_rows
from ui.components.sn_association_viewer import build_inventory_association_map


def _row(**kwargs: str) -> dict[str, str]:
    base = {h: "" for h in INVENTORY_HEADERS}
    base.update({k: str(v) for k, v in kwargs.items()})
    return base


def test_collect_individuals_includes_lonely_em500() -> None:
    rows_df = pd.DataFrame(
        [
            _row(
                inventory_id="gw1",
                model="ug67",
                serial_number="UG001",
                location_type="cliente",
                location_detail="ClienteA",
                associated_sim_inventory_id="sim1",
            ),
            _row(
                inventory_id="sim1",
                model="sim",
                serial_number="SIM888",
                sim_eid_number="E999",
                location_type="por_definir",
            ),
            _row(
                inventory_id="e5",
                model="em500",
                serial_number="EM_SINGLE",
                location_type="oficina",
                location_detail="oficina",
                associated_gateway_inventory_id="",
            ),
            _row(
                inventory_id="e5_linked",
                model="em500",
                serial_number="EM_CHILD",
                location_type="cliente",
                location_detail="X",
                associated_gateway_inventory_id="gw1",
            ),
        ]
    ).fillna("").astype(str)
    groups, _ = build_inventory_association_map(rows_df)
    individuals = collect_individual_inventory_rows(rows_df, groups)
    ind_ids = [r["inventory_id"] for r in individuals]
    assert "e5" in ind_ids
    assert "e5_linked" not in ind_ids
    assert "gw1" not in ind_ids
    assert "sim1" not in ind_ids


def test_build_association_map_pdf_bytes_returns_pdf() -> None:
    rows = pd.DataFrame(
        [_row(inventory_id="u1", model="uc501", serial_number="UCX", location_type="por_definir")]
    ).fillna("").astype(str)
    content, fname = build_association_map_pdf_bytes(rows)
    assert fname.endswith(".pdf")
    assert len(content) >= 500
    assert content[:4] == b"%PDF"
