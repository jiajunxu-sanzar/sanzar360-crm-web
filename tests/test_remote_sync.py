"""Tests para ``app.remote_sync``: poll throttled de Drive.modifiedTime."""
from __future__ import annotations

import pytest
import streamlit as st

from app import remote_sync
from app.state import DATA_CACHE_VERSION_KEYS


class _FakeSessionState(dict):
    """Dict accesible por atributo, sustituto de ``st.session_state`` en tests.

    Fuera de ``streamlit run`` el ``session_state`` real no persiste, por lo
    que parchearlo con un dict en memoria nos da semántica determinista.
    """

    def __getattr__(self, name: str):  # noqa: D401 - dict semantics
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value) -> None:
        self[name] = value


@pytest.fixture(autouse=True)
def fake_session_state(monkeypatch: pytest.MonkeyPatch) -> _FakeSessionState:
    fake = _FakeSessionState()
    monkeypatch.setattr(st, "session_state", fake, raising=False)
    monkeypatch.setattr(remote_sync.st, "session_state", fake, raising=False)
    return fake


@pytest.fixture
def time_holder() -> dict[str, float]:
    return {"now": 1000.0}


@pytest.fixture
def mtime_holder() -> dict[str, object]:
    return {"value": "2024-01-01T10:00:00.000Z", "calls": 0}


@pytest.fixture(autouse=True)
def _patch_clock_and_network(
    monkeypatch: pytest.MonkeyPatch,
    time_holder: dict[str, float],
    mtime_holder: dict[str, object],
) -> None:
    """Aísla ``remote_sync`` del reloj real y de la red."""
    monkeypatch.setattr(remote_sync, "_now", lambda: time_holder["now"])

    def fake_read() -> str:
        mtime_holder["calls"] = int(mtime_holder["calls"]) + 1  # type: ignore[arg-type]
        return str(mtime_holder["value"])

    monkeypatch.setattr(remote_sync, "_read_modified_time", fake_read)
    # ``st.cache_data.clear()`` puede no estar disponible fuera de Streamlit;
    # parcheamos a no-op para que las pruebas no dependan del runtime.
    monkeypatch.setattr(st.cache_data, "clear", lambda: None, raising=False)


def test_first_check_records_baseline_without_invalidating(
    fake_session_state: _FakeSessionState, mtime_holder: dict[str, object]
) -> None:
    invalidated = remote_sync.check_remote_changes()
    assert invalidated is False
    assert mtime_holder["calls"] == 1
    assert fake_session_state.get("_remote_sync_last_mtime") == mtime_holder["value"]


def test_subsequent_check_within_throttle_is_skipped(
    time_holder: dict[str, float], mtime_holder: dict[str, object]
) -> None:
    remote_sync.check_remote_changes()
    initial_calls = int(mtime_holder["calls"])  # type: ignore[arg-type]
    time_holder["now"] += remote_sync.POLL_INTERVAL_S - 1
    assert remote_sync.check_remote_changes() is False
    assert mtime_holder["calls"] == initial_calls, "no debería volver a Drive antes del throttle"


def test_change_after_throttle_invalidates_all_caches(
    fake_session_state: _FakeSessionState,
    time_holder: dict[str, float],
    mtime_holder: dict[str, object],
) -> None:
    remote_sync.check_remote_changes()
    for key in DATA_CACHE_VERSION_KEYS:
        fake_session_state[key] = 5

    time_holder["now"] += remote_sync.POLL_INTERVAL_S + 1
    mtime_holder["value"] = "2024-01-02T11:00:00.000Z"

    invalidated = remote_sync.check_remote_changes()
    assert invalidated is True
    for key in DATA_CACHE_VERSION_KEYS:
        assert fake_session_state[key] == 6


def test_same_mtime_after_throttle_does_not_invalidate(
    fake_session_state: _FakeSessionState,
    time_holder: dict[str, float],
) -> None:
    remote_sync.check_remote_changes()
    for key in DATA_CACHE_VERSION_KEYS:
        fake_session_state[key] = 5

    time_holder["now"] += remote_sync.POLL_INTERVAL_S + 1
    invalidated = remote_sync.check_remote_changes()
    assert invalidated is False
    for key in DATA_CACHE_VERSION_KEYS:
        assert fake_session_state[key] == 5


def test_force_bypasses_throttle(mtime_holder: dict[str, object]) -> None:
    remote_sync.check_remote_changes()
    before = int(mtime_holder["calls"])  # type: ignore[arg-type]
    remote_sync.check_remote_changes(force=True)
    assert mtime_holder["calls"] == before + 1


def test_network_failure_is_silent(
    fake_session_state: _FakeSessionState, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom() -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(remote_sync, "_read_modified_time", _boom)
    assert remote_sync.check_remote_changes() is False
    assert "_remote_sync_last_mtime" not in fake_session_state


def test_empty_modified_time_is_treated_as_unknown(
    fake_session_state: _FakeSessionState, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(remote_sync, "_read_modified_time", lambda: "")
    assert remote_sync.check_remote_changes() is False
    assert "_remote_sync_last_mtime" not in fake_session_state


def test_reset_state_clears_baseline_and_timestamp(
    fake_session_state: _FakeSessionState,
) -> None:
    remote_sync.check_remote_changes()
    assert "_remote_sync_last_mtime" in fake_session_state
    remote_sync.reset_remote_sync_state()
    assert "_remote_sync_last_mtime" not in fake_session_state
    assert "_remote_sync_last_check_ts" not in fake_session_state
