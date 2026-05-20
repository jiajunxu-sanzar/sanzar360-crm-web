"""Tests for history table search and selection/filter interaction."""
from __future__ import annotations

import pandas as pd
import pytest
import streamlit as st

from ui.components.history import clear_history_table_selection, history_table_search_key
from ui.components.tables import filter_dataframe


class _FakeSessionState(dict):
    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value) -> None:
        self[name] = value


@pytest.fixture
def fake_session_state(monkeypatch: pytest.MonkeyPatch) -> _FakeSessionState:
    fake = _FakeSessionState()
    monkeypatch.setattr(st, "session_state", fake, raising=False)
    return fake


def test_history_table_search_key() -> None:
    assert history_table_search_key("c1", "campanas") == "hist_table_search_c1_campanas"


def test_filter_dataframe_matches_any_column() -> None:
    df = pd.DataFrame(
        [
            {"nombre_campana": "Olivo norte", "cultivo": "olivo", "parcela": "P1"},
            {"nombre_campana": "Almendro sur", "cultivo": "almendro", "parcela": "P2"},
        ]
    )
    filtered = filter_dataframe(df, "olivo", list(df.columns))
    assert len(filtered) == 1
    assert filtered.iloc[0]["nombre_campana"] == "Olivo norte"


def test_filtered_selection_maps_to_original_row_index() -> None:
    df = pd.DataFrame(
        [
            {"historial_sensor_id": "h1", "sensor_serial_number": "uc501-A"},
            {"historial_sensor_id": "h2", "sensor_serial_number": "uc501-B"},
            {"historial_sensor_id": "h3", "sensor_serial_number": "ug67-C"},
        ]
    )
    filtered = filter_dataframe(df, "ug67", list(df.columns))
    assert list(filtered.index) == [2]
    filtered_pos = 0
    assert int(filtered.index[filtered_pos]) == 2


def test_clear_selection_preserves_search_query(fake_session_state: _FakeSessionState) -> None:
    fake_session_state["hist_table_search_c1_sensores"] = "UC501"
    fake_session_state["hist_table_version_c1_sensores"] = 0
    fake_session_state["hist_table_select_c1_sensores_v0"] = {"selection": {"rows": [0]}}

    clear_history_table_selection("c1", "sensores")

    assert fake_session_state["hist_table_search_c1_sensores"] == "UC501"
    assert fake_session_state.get("hist_table_version_c1_sensores") == 1
