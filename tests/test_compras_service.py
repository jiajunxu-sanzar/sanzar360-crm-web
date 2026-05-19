from __future__ import annotations

import json

import pandas as pd
import pytest

from config.settings import COMPRAS_HEADERS, COMPRAS_WORKSHEET_NAME
from services.compras_service import (
    ComprasService,
    PoLineItem,
    PoLineasPayload,
    parse_po_lineas_json,
    serialize_po_lineas_json,
    validate_compra_row,
)


class FakeSheets:
    def __init__(self) -> None:
        self.frames: dict[str, pd.DataFrame] = {
            COMPRAS_WORKSHEET_NAME: pd.DataFrame(columns=list(COMPRAS_HEADERS)),
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
        out: dict[str, int] = {}
        for i, row in df.iterrows():
            value = str(row.get(id_header, "")).strip()
            if value:
                out[value] = i + 2
        return out

    def append_worksheet_row(self, name: str, headers: list[str], row: dict[str, str]) -> None:
        self.frames[name] = pd.concat(
            [self.frames[name], pd.DataFrame([{h: str(row.get(h, "") or "") for h in headers}])],
            ignore_index=True,
        )

    def update_worksheet_row(self, name: str, headers: list[str], row_num: int, row: dict[str, str]) -> None:
        idx = max(0, row_num - 2)
        df = self.frames[name].copy()
        for h in headers:
            df.at[idx, h] = str(row.get(h, "") or "")
        self.frames[name] = df

    def write_worksheet_df(self, name: str, df: pd.DataFrame, headers: list[str]) -> None:
        self.frames[name] = df[headers].fillna("").astype(str).copy()


def _row(**kwargs: str) -> dict[str, str]:
    return {h: str(kwargs.get(h, "") or "") for h in COMPRAS_HEADERS}


def test_parse_po_lineas_json_array_and_object() -> None:
    array_raw = json.dumps([{"item_no": "1", "description": "UC501", "qty": 2, "unit_price": 100}])
    payload_array = parse_po_lineas_json(array_raw)
    assert len(payload_array.items) == 1
    assert payload_array.items[0].description == "UC501"
    assert payload_array.tax_pct == 0.0

    object_raw = serialize_po_lineas_json(
        PoLineasPayload(
            items=(PoLineItem("1", "SIM", 10, 5.5),),
            tax_pct=21.0,
            shipping=15.0,
            comments="Urgent",
        )
    )
    payload_object = parse_po_lineas_json(object_raw)
    assert payload_object.items[0].description == "SIM"
    assert payload_object.tax_pct == 21.0
    assert payload_object.shipping == 15.0
    assert payload_object.comments == "Urgent"


def test_validate_compra_row_requires_reception_date_when_received() -> None:
    errors = validate_compra_row(_row(estado="recibida", fecha_recepcion=""))
    assert any("fecha_recepcion" in e for e in errors)

    ok = validate_compra_row(_row(estado="recibida", fecha_recepcion="20/12/2025"))
    assert ok == []


def test_upsert_compra_preserves_created_at_on_update() -> None:
    sheets = FakeSheets()
    svc = ComprasService(sheets)
    compra_id = svc.upsert_compra(
        _row(compra_id="c-1", descripcion="Sensores", estado="comparando", created_at="01/01/2024")
    )
    assert compra_id == "c-1"
    svc.upsert_compra(
        _row(compra_id="c-1", descripcion="Sensores actualizados", estado="pendiente", created_at="")
    )
    saved = sheets.frames[COMPRAS_WORKSHEET_NAME].fillna("").astype(str)
    row = saved[saved["compra_id"] == "c-1"].iloc[0]
    assert row["created_at"] == "01/01/2024"
    assert row["descripcion"] == "Sensores actualizados"
    assert row["estado"] == "pendiente"


def test_delete_compra_by_id() -> None:
    sheets = FakeSheets()
    svc = ComprasService(sheets)
    svc.upsert_compra(_row(compra_id="c-1", descripcion="A", estado="comparando"))
    svc.upsert_compra(_row(compra_id="c-2", descripcion="B", estado="comparando"))
    df = svc.compras_df()
    assert svc.delete_compra_by_id("c-1", df=df)
    remaining = svc.compras_df()
    ids = remaining["compra_id"].astype(str).tolist()
    assert "c-1" not in ids
    assert "c-2" in ids


def test_upsert_rejects_invalid_estado() -> None:
    sheets = FakeSheets()
    svc = ComprasService(sheets)
    with pytest.raises(ValueError, match="Estado inválido"):
        svc.upsert_compra(_row(estado="desconocido"))


def test_is_pending_and_completed() -> None:
    assert ComprasService.is_pending("en_transito")
    assert ComprasService.is_pending("comparando")
    assert not ComprasService.is_pending("recibida")
    assert ComprasService.is_completed("recibida")
    assert not ComprasService.is_completed("pendiente")
