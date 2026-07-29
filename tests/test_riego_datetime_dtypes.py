"""Tests de normalización datetime64 ns/us para merge_asof en umbrales."""
from __future__ import annotations

import pandas as pd
import pytest

from services.riego_umbrales import ParametrosDeteccion, _ensure_datetime64_ns


def test_parametros_deteccion_horas_min_estable_default_4h() -> None:
    assert ParametrosDeteccion().horas_min_estable == 4.0
    assert ParametrosDeteccion(horas_min_estable=8.0).horas_min_estable == 8.0


def test_ensure_datetime64_ns_from_ns() -> None:
    s = pd.to_datetime(["2024-01-01 00:00:00", "2024-01-01 01:00:00"]).astype("datetime64[ns]")
    out = _ensure_datetime64_ns(s)
    assert str(out.dtype) == "datetime64[ns]"
    assert len(out) == 2


def test_ensure_datetime64_ns_from_us() -> None:
    s = pd.to_datetime(["2024-01-01 00:00:00", "2024-01-01 01:00:00"])
    # En pandas reciente to_datetime puede ser [us]; forzamos us si hace falta.
    try:
        s = s.astype("datetime64[us]")
    except (TypeError, ValueError):
        pytest.skip("Este pandas no soporta datetime64[us]")
    assert "us" in str(s.dtype)
    out = _ensure_datetime64_ns(s)
    assert str(out.dtype) == "datetime64[ns]"


def test_merge_asof_ns_and_us_after_normalize() -> None:
    left = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-06-01 10:00:00", "2024-06-01 11:00:00"]).astype("datetime64[ns]"),
        "valor": [20.0, 21.0],
    })
    right = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-06-01 10:00:00", "2024-06-01 11:00:00"]),
        "et0": [0.1, 0.2],
    })
    try:
        right["timestamp"] = right["timestamp"].astype("datetime64[us]")
    except (TypeError, ValueError):
        pytest.skip("Este pandas no soporta datetime64[us]")

    left = left.copy()
    right = right.copy()
    left["timestamp"] = _ensure_datetime64_ns(left["timestamp"])
    right["timestamp"] = _ensure_datetime64_ns(right["timestamp"])

    merged = pd.merge_asof(
        left.sort_values("timestamp"),
        right.sort_values("timestamp"),
        on="timestamp",
        direction="nearest",
        tolerance=pd.Timedelta("1h"),
    )
    assert len(merged) == 2
    assert "et0" in merged.columns
    assert merged["et0"].notna().all()
