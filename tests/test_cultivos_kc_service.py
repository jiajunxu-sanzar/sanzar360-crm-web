from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from config.settings import CULTIVOS_KC_HEADERS, CULTIVOS_KC_WORKSHEET_NAME
from services.cultivos_kc_service import CultivosKcService
from services.riego_umbrales import validar_cultivo


class FakeSheets:
    def __init__(self) -> None:
        self.frames: dict[str, pd.DataFrame] = {
            CULTIVOS_KC_WORKSHEET_NAME: pd.DataFrame(columns=list(CULTIVOS_KC_HEADERS)),
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


def _cultivo(**kwargs: str) -> dict[str, str]:
    base = {
        "nombre": "viña - uva",
        "L1": "30",
        "L2": "90",
        "L3": "130",
        "L4": "210",
        "kc_ini": "0.3",
        "kc_med": "0.7",
        "kc_fin": "0.45",
        "p_tabla": "0.4",
    }
    base.update(kwargs)
    return base


def test_validar_cultivo_requires_nombre() -> None:
    with pytest.raises(ValueError, match="nombre"):
        validar_cultivo(_cultivo(nombre=""))


def test_validar_cultivo_requires_ordered_stages() -> None:
    with pytest.raises(ValueError, match="L1 ≤ L2 ≤ L3 ≤ L4"):
        validar_cultivo(_cultivo(L1="100", L2="50", L3="130", L4="210"))


def test_validar_cultivo_ok() -> None:
    validar_cultivo(_cultivo())


def test_upsert_create_sets_audit_fields() -> None:
    sheets = FakeSheets()
    svc = CultivosKcService(sheets)
    cid = svc.upsert_cultivo(_cultivo(), actor_name="Ana", mode="create")
    assert cid
    row = sheets.frames[CULTIVOS_KC_WORKSHEET_NAME].iloc[0]
    assert row["nombre"] == "viña - uva"
    assert row["creado_por"] == "Ana"
    assert row["created_at"] == date.today().strftime("%d/%m/%Y")
    assert row["updated_at"] == date.today().strftime("%d/%m/%Y")
    assert str(row["cultivo_kc_id"]).strip() == cid


def test_upsert_blocks_duplicate_nombre_on_create() -> None:
    sheets = FakeSheets()
    svc = CultivosKcService(sheets)
    svc.upsert_cultivo(_cultivo(), actor_name="Ana", mode="create")
    with pytest.raises(ValueError, match="Ya existe"):
        svc.upsert_cultivo(_cultivo(nombre="Viña - Uva"), actor_name="Ana", mode="create")


def test_upsert_edit_allows_same_nombre_and_preserves_created() -> None:
    sheets = FakeSheets()
    svc = CultivosKcService(sheets)
    cid = svc.upsert_cultivo(_cultivo(), actor_name="Ana", mode="create")
    sheets.frames[CULTIVOS_KC_WORKSHEET_NAME].at[0, "created_at"] = "01/01/2024"
    sheets.frames[CULTIVOS_KC_WORKSHEET_NAME].at[0, "creado_por"] = "Ana"
    svc.upsert_cultivo(
        {**_cultivo(nombre="viña - uva", L4="220"), "cultivo_kc_id": cid},
        actor_name="Bruno",
        mode="edit",
    )
    row = sheets.frames[CULTIVOS_KC_WORKSHEET_NAME].iloc[0]
    assert float(row["L4"]) == 220.0
    assert row["creado_por"] == "Ana"
    assert row["created_at"] == "01/01/2024"
    assert row["updated_at"] == date.today().strftime("%d/%m/%Y")


def test_upsert_edit_blocks_other_duplicate_nombre() -> None:
    sheets = FakeSheets()
    svc = CultivosKcService(sheets)
    cid_a = svc.upsert_cultivo(_cultivo(nombre="A"), actor_name="Ana", mode="create")
    svc.upsert_cultivo(_cultivo(nombre="B"), actor_name="Ana", mode="create")
    with pytest.raises(ValueError, match="Ya existe"):
        svc.upsert_cultivo(
            {**_cultivo(nombre="B"), "cultivo_kc_id": cid_a},
            actor_name="Ana",
            mode="edit",
        )


def test_delete_cultivo_by_id() -> None:
    sheets = FakeSheets()
    svc = CultivosKcService(sheets)
    cid = svc.upsert_cultivo(_cultivo(), actor_name="Ana", mode="create")
    assert svc.delete_cultivo_by_id(cid)
    assert svc.cultivos_df().empty


def test_seed_if_empty_once() -> None:
    sheets = FakeSheets()
    svc = CultivosKcService(sheets)
    assert svc.seed_if_empty(actor_name="sistema") is True
    assert svc.seed_if_empty(actor_name="sistema") is False
    assert len(svc.list_cultivos()) == 1
    assert svc.list_cultivos()[0]["nombre"] == "viña - uva"
    assert svc.list_cultivos()[0]["p_tabla"] == 0.4
