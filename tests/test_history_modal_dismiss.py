"""Tests for history modal dismiss callbacks (active_modal cleanup)."""
from __future__ import annotations

import pytest
import streamlit as st

from pages.contacts import _clear_sensor_picker_state, _on_dismiss_history_add, _on_dismiss_history_edit
from ui.components.history import clear_history_table_selection, history_table_selection_key


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


def test_history_table_selection_key_uses_version(fake_session_state: _FakeSessionState) -> None:
    fake_session_state["hist_table_version_c1_sensores"] = 2
    assert history_table_selection_key("c1", "sensores") == "hist_table_select_c1_sensores_v2"


def test_clear_history_table_selection_bumps_version(fake_session_state: _FakeSessionState) -> None:
    fake_session_state["hist_table_version_c1_sensores"] = 0
    fake_session_state["hist_table_select_c1_sensores_v0"] = {"selection": {"rows": [0]}}

    clear_history_table_selection("c1", "sensores")

    assert fake_session_state.get("hist_table_version_c1_sensores") == 1
    assert "hist_table_select_c1_sensores_v0" not in fake_session_state
    assert history_table_selection_key("c1", "sensores") == "hist_table_select_c1_sensores_v1"


def test_dismiss_edit_clears_active_modal_and_selection(fake_session_state: _FakeSessionState) -> None:
    fake_session_state["active_modal"] = {
        "type": "edit_history",
        "kind": "sensores",
        "contact_id": "c1",
        "row_id": "h1",
    }
    fake_session_state["hist_table_version_c1_sensores"] = 0
    fake_session_state["hist_table_select_c1_sensores_v0"] = {"selection": {"rows": [0]}}
    fake_session_state["sensores_h1_sensor_uc501_sn"] = "UC001"

    _on_dismiss_history_edit()

    assert fake_session_state.get("active_modal") is None
    assert "hist_table_select_c1_sensores_v0" not in fake_session_state
    assert fake_session_state.get("hist_table_version_c1_sensores") == 1
    assert "sensores_h1_sensor_uc501_sn" not in fake_session_state


def test_dismiss_edit_does_not_clear_other_kind_selection(fake_session_state: _FakeSessionState) -> None:
    fake_session_state["active_modal"] = {
        "type": "edit_history",
        "kind": "sensores",
        "contact_id": "c1",
        "row_id": "h1",
    }
    fake_session_state["hist_table_version_c1_campanas"] = 0
    fake_session_state["hist_table_select_c1_campanas_v0"] = {"selection": {"rows": [1]}}

    _on_dismiss_history_edit()

    assert fake_session_state.get("active_modal") is None
    assert "hist_table_select_c1_campanas_v0" in fake_session_state


def test_dismiss_add_clears_active_modal(fake_session_state: _FakeSessionState) -> None:
    fake_session_state["active_modal"] = {
        "type": "add_history",
        "kind": "incidencias",
        "contact_id": "c2",
    }

    _on_dismiss_history_add()

    assert fake_session_state.get("active_modal") is None


def test_dismiss_add_clears_sensor_picker_state(fake_session_state: _FakeSessionState) -> None:
    fake_session_state["active_modal"] = {
        "type": "add_history",
        "kind": "sensores",
        "contact_id": "c2",
    }
    fake_session_state["sensores_new_sensor_uc501_sn"] = "UC001"

    _on_dismiss_history_add()

    assert fake_session_state.get("active_modal") is None
    assert "sensores_new_sensor_uc501_sn" not in fake_session_state


def test_dismiss_edit_ignores_add_modal(fake_session_state: _FakeSessionState) -> None:
    fake_session_state["active_modal"] = {
        "type": "add_history",
        "kind": "campanas",
        "contact_id": "c1",
    }

    _on_dismiss_history_edit()

    assert fake_session_state["active_modal"]["type"] == "add_history"


def test_dismiss_add_ignores_edit_modal(fake_session_state: _FakeSessionState) -> None:
    fake_session_state["active_modal"] = {
        "type": "edit_history",
        "kind": "suscripciones",
        "contact_id": "c1",
        "row_id": "s1",
    }

    _on_dismiss_history_add()

    assert fake_session_state["active_modal"]["type"] == "edit_history"


def test_dismiss_edit_prevents_cross_kind_reopen(fake_session_state: _FakeSessionState) -> None:
    """After dismissing sensores edit, campañas interaction must not reopen sensores modal."""
    fake_session_state["active_modal"] = {
        "type": "edit_history",
        "kind": "sensores",
        "contact_id": "c1",
        "row_id": "h1",
    }
    fake_session_state["show_history_sensores_c1"] = True
    fake_session_state["show_history_campanas_c1"] = True

    _on_dismiss_history_edit()

    assert fake_session_state.get("active_modal") is None


def test_clear_sensor_picker_state_removes_widget_keys(fake_session_state: _FakeSessionState) -> None:
    prefix = "sensores_h1"
    fake_session_state[f"{prefix}_sensor_uc501_sn"] = "UC001"
    fake_session_state[f"{prefix}_is_uc501"] = True
    fake_session_state[f"{prefix}_sensor_serial_number"] = "uc501-UC001-T10-SIM001"

    _clear_sensor_picker_state(prefix)

    assert f"{prefix}_sensor_uc501_sn" not in fake_session_state
    assert f"{prefix}_is_uc501" not in fake_session_state
    assert f"{prefix}_sensor_serial_number" not in fake_session_state
