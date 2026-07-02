from __future__ import annotations

import pandas as pd

from services.contact_sensor_overview import (
    OVERVIEW_COLUMNS,
    filter_by_sensor_overview,
    semaforo_by_contact_id,
    semaforo_display_prefix,
)


def _contacts_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"contact_id": "c1", "nombre": "Uno"},
            {"contact_id": "c2", "nombre": "Dos"},
            {"contact_id": "c3", "nombre": "Tres"},
        ]
    )


def _overview_df() -> pd.DataFrame:
    rows = [
        {col: "" for col in OVERVIEW_COLUMNS}
        for _ in range(3)
    ]
    rows[0].update({"contact_id": "c1", "semaforo": "verde"})
    rows[1].update({"contact_id": "c2", "semaforo": "amarillo"})
    rows[2].update({"contact_id": "c3", "semaforo": "sin_sensores"})
    return pd.DataFrame(rows, columns=OVERVIEW_COLUMNS)


def test_filter_off_returns_unchanged() -> None:
    df = _contacts_df()
    overview = _overview_df()
    out = filter_by_sensor_overview(df, overview, only_with_sensors=False)
    assert len(out) == 3
    assert list(out["contact_id"]) == ["c1", "c2", "c3"]


def test_filter_keeps_verde_and_amarillo() -> None:
    df = _contacts_df()
    overview = _overview_df()
    out = filter_by_sensor_overview(df, overview, only_with_sensors=True)
    assert list(out["contact_id"]) == ["c1", "c2"]


def test_filter_empty_overview() -> None:
    df = _contacts_df()
    out = filter_by_sensor_overview(df, pd.DataFrame(columns=OVERVIEW_COLUMNS), only_with_sensors=True)
    assert out.empty


def test_semaforo_by_contact_id() -> None:
    mapping = semaforo_by_contact_id(_overview_df())
    assert mapping == {"c1": "verde", "c2": "amarillo", "c3": "sin_sensores"}


def test_semaforo_display_prefix() -> None:
    assert semaforo_display_prefix("verde", is_lost=False) == "🟢 "
    assert semaforo_display_prefix("amarillo", is_lost=False) == "🟡 "
    assert semaforo_display_prefix("sin_sensores", is_lost=False) == ""
    assert semaforo_display_prefix("verde", is_lost=True) == ""
