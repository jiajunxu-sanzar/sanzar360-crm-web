"""Tests for próxima acción dashboard filter helpers."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from services.proxima_accion_stats import (
    apply_dash_bucket_date_filter,
    filter_by_persona_proxima_accion,
    next_action_bucket_counts,
)


def _sample_df() -> pd.DataFrame:
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    return pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "persona_proxima_accion": "David Ortiz",
                "proxima_accion_fecha": yesterday.strftime("%d/%m/%Y"),
            },
            {
                "contact_id": "c2",
                "persona_proxima_accion": "David Ortiz",
                "proxima_accion_fecha": today.strftime("%d/%m/%Y"),
            },
            {
                "contact_id": "c3",
                "persona_proxima_accion": "Marco Ruano",
                "proxima_accion_fecha": today.strftime("%d/%m/%Y"),
            },
            {
                "contact_id": "c4",
                "persona_proxima_accion": "David Ortiz",
                "proxima_accion_fecha": tomorrow.strftime("%d/%m/%Y"),
            },
        ]
    )


def test_filter_by_persona_proxima_accion() -> None:
    df = _sample_df()
    filtered = filter_by_persona_proxima_accion(df, "David Ortiz")
    assert set(filtered["contact_id"].tolist()) == {"c1", "c2", "c4"}


def test_filter_by_persona_empty_returns_all() -> None:
    df = _sample_df()
    assert len(filter_by_persona_proxima_accion(df, "")) == 4


def test_next_action_bucket_counts_respects_persona_scope() -> None:
    today = date.today()
    df = _sample_df()
    scoped = filter_by_persona_proxima_accion(df, "David Ortiz")
    counts = next_action_bucket_counts(scoped, today=today)
    assert counts == {"past": 1, "today": 1, "tomorrow": 1}


def test_apply_dash_bucket_with_persona() -> None:
    today = date.today()
    df = _sample_df()
    scoped = filter_by_persona_proxima_accion(df, "David Ortiz")
    today_rows = apply_dash_bucket_date_filter(scoped, "today", today=today)
    assert list(today_rows["contact_id"]) == ["c2"]
