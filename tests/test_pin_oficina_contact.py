from __future__ import annotations

import pandas as pd

from pages.contacts import filter_open_sensor_history, pin_oficina_contact_first


def test_pin_oficina_moves_to_first() -> None:
    df = pd.DataFrame(
        [
            {"contact_id": "c1", "nombre": "Cliente A"},
            {"contact_id": "c2", "nombre": "Oficina"},
            {"contact_id": "c3", "nombre": "Cliente B"},
        ]
    )
    out = pin_oficina_contact_first(df)
    assert list(out["contact_id"]) == ["c2", "c1", "c3"]


def test_pin_oficina_case_insensitive() -> None:
    df = pd.DataFrame(
        [
            {"contact_id": "c1", "nombre": "Zeta"},
            {"contact_id": "c2", "nombre": "  oficina  "},
        ]
    )
    out = pin_oficina_contact_first(df)
    assert out.iloc[0]["contact_id"] == "c2"


def test_pin_oficina_no_match_unchanged() -> None:
    df = pd.DataFrame(
        [
            {"contact_id": "c1", "nombre": "Alpha"},
            {"contact_id": "c2", "nombre": "Beta"},
        ]
    )
    out = pin_oficina_contact_first(df)
    assert list(out["contact_id"]) == ["c1", "c2"]


def test_pin_oficina_multiple_keep_relative_order() -> None:
    df = pd.DataFrame(
        [
            {"contact_id": "c1", "nombre": "Cliente"},
            {"contact_id": "c2", "nombre": "Oficina"},
            {"contact_id": "c3", "nombre": "oficina"},
            {"contact_id": "c4", "nombre": "Otro"},
        ]
    )
    out = pin_oficina_contact_first(df)
    assert list(out["contact_id"]) == ["c2", "c3", "c1", "c4"]


def test_pin_oficina_empty() -> None:
    assert pin_oficina_contact_first(pd.DataFrame()).empty


def test_filter_open_sensor_history() -> None:
    rows = [
        {"historial_sensor_id": "h1", "estado_cierre_sensor": "abierto"},
        {"historial_sensor_id": "h2", "estado_cierre_sensor": "cerrado"},
        {"historial_sensor_id": "h3", "estado_cierre_sensor": ""},
        {"historial_sensor_id": "h4", "estado_cierre_sensor": "CERRADO"},
    ]
    open_rows = filter_open_sensor_history(rows)
    assert [r["historial_sensor_id"] for r in open_rows] == ["h1", "h3"]
