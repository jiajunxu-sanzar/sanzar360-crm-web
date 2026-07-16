from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd

from config.settings import CANONICAL_COLUMNS
from services.clientes_board import (
    VER_TODOS,
    filter_clientes_board,
    is_visto_hoy,
    sort_clientes_board,
    values_for_flag,
    values_for_visto_toggle,
)
from services.contacts_schema import ensure_contacts_schema


class _FakeWorksheet:
    def __init__(
        self,
        *,
        row1: list[str],
        data_rows: list[list[str]] | None = None,
        update: MagicMock | None = None,
    ) -> None:
        self._row1 = row1
        self._data_rows = data_rows or []
        self.clear = MagicMock()
        self.update = update or MagicMock()

    def get_all_values(self) -> list[list[str]]:
        return [list(self._row1), *self._data_rows]


class _FakeSheetsService:
    def __init__(self, ws: _FakeWorksheet) -> None:
        self._ws = ws

    def worksheet(self, name: str | None = None) -> _FakeWorksheet:
        _ = name
        return self._ws


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "nombre": "Beta Agrícola",
                "tipo_relacion": "Cliente",
                "responsable_cliente": "Ana",
                "visto_cliente_fecha": "",
                "umbrales_activadas": "FALSE",
                "suelo_seco": "FALSE",
            },
            {
                "contact_id": "c2",
                "nombre": "Alfa Potencial",
                "tipo_relacion": "Potencial cliente",
                "responsable_cliente": "Ana",
                "visto_cliente_fecha": "2026-07-16",
                "umbrales_activadas": "TRUE",
                "suelo_seco": "FALSE",
            },
            {
                "contact_id": "c3",
                "nombre": "Captación X",
                "tipo_relacion": "Captación",
                "responsable_cliente": "Ana",
                "visto_cliente_fecha": "",
                "umbrales_activadas": "FALSE",
                "suelo_seco": "FALSE",
            },
            {
                "contact_id": "c4",
                "nombre": "Otro Cliente",
                "tipo_relacion": "Cliente",
                "responsable_cliente": "Bruno",
                "visto_cliente_fecha": "",
                "umbrales_activadas": "FALSE",
                "suelo_seco": "TRUE",
            },
        ]
    )


def test_schema_appends_clientes_columns_without_clearing() -> None:
    new_cols = ["tipo_relacion", "umbrales_activadas", "suelo_seco", "visto_cliente_fecha"]
    old_head = [c for c in CANONICAL_COLUMNS if c not in new_cols]
    data_rows = [["x"] * len(old_head)]
    ws = _FakeWorksheet(row1=old_head, data_rows=data_rows)
    sheets = _FakeSheetsService(ws)

    ensure_contacts_schema(sheets)  # type: ignore[arg-type]

    ws.clear.assert_not_called()
    ws.update.assert_called_once()
    new_head = ws.update.call_args[0][0][0]
    assert new_head == old_head + new_cols


def test_filter_clientes_board_excludes_captacion() -> None:
    filtered = filter_clientes_board(_sample_df(), VER_TODOS)
    ids = set(filtered["contact_id"].tolist())
    assert ids == {"c1", "c2", "c4"}
    assert "c3" not in ids


def test_filter_clientes_board_by_responsable() -> None:
    filtered = filter_clientes_board(_sample_df(), "Ana")
    assert set(filtered["contact_id"].tolist()) == {"c1", "c2"}


def test_filter_clientes_board_ver_todos() -> None:
    filtered = filter_clientes_board(_sample_df(), VER_TODOS)
    assert len(filtered) == 3


def test_is_visto_hoy() -> None:
    today = date(2026, 7, 16)
    assert is_visto_hoy("2026-07-16", today=today) is True
    assert is_visto_hoy("2026-07-15", today=today) is False
    assert is_visto_hoy("", today=today) is False
    assert is_visto_hoy(None, today=today) is False


def test_sort_clientes_board_unseen_first_then_tipo_then_name() -> None:
    today = date(2026, 7, 16)
    board = filter_clientes_board(_sample_df(), VER_TODOS)
    sorted_df = sort_clientes_board(board, today=today)
    # unseen first: c1 (Cliente Beta), c4 (Cliente Otro); then seen c2
    assert sorted_df["contact_id"].tolist() == ["c1", "c4", "c2"]


def test_values_for_visto_toggle() -> None:
    today = date(2026, 7, 16)
    assert values_for_visto_toggle(checked=True, today=today) == {"visto_cliente_fecha": "2026-07-16"}
    assert values_for_visto_toggle(checked=False, today=today) == {"visto_cliente_fecha": ""}


def test_values_for_flag() -> None:
    assert values_for_flag("umbrales_activadas", checked=True) == {"umbrales_activadas": "TRUE"}
    assert values_for_flag("suelo_seco", checked=False) == {"suelo_seco": "FALSE"}


def test_clientes_visible_to_sales_not_employee() -> None:
    from app import navigation

    assert "Clientes" in navigation.PAGES
    assert "Clientes" in navigation.PAGE_MENU_LABELS
    assert "Clientes" in navigation.PAGES_REQUIRING_CONTACTS
    assert "Clientes" in navigation.pages_for_role(navigation.ROLE_SALES)
    assert "Clientes" in navigation.pages_for_role(navigation.ROLE_AGRO_TEAM)
    assert "Clientes" not in navigation.pages_for_role(navigation.ROLE_EMPLOYEE)
