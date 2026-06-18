"""Tests for próxima acción dashboard filter helpers."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from services.proxima_accion_stats import (
    apply_dash_bucket_date_filter,
    filter_by_contact_estado,
    filter_by_persona_proxima_accion,
    filter_by_responsable_cliente,
    next_action_bucket_counts,
)


def _sample_df() -> pd.DataFrame:
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    day_after_tomorrow = today + timedelta(days=2)
    return pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "persona_proxima_accion": "David Ortiz",
                "proxima_accion_fecha": yesterday.strftime("%d/%m/%Y"),
                "estado": "Nuevo contacto",
                "responsable_cliente": "David Ortiz",
            },
            {
                "contact_id": "c2",
                "persona_proxima_accion": "David Ortiz",
                "proxima_accion_fecha": today.strftime("%d/%m/%Y"),
                "estado": "Contacto inicial",
                "responsable_cliente": "Marco Ruano",
            },
            {
                "contact_id": "c3",
                "persona_proxima_accion": "Marco Ruano",
                "proxima_accion_fecha": today.strftime("%d/%m/%Y"),
                "estado": "Piloto activo",
                "responsable_cliente": "",
            },
            {
                "contact_id": "c4",
                "persona_proxima_accion": "David Ortiz",
                "proxima_accion_fecha": tomorrow.strftime("%d/%m/%Y"),
                "estado": "Nuevo contacto",
                "responsable_cliente": "David Ortiz",
            },
            {
                "contact_id": "c5",
                "persona_proxima_accion": "David Ortiz",
                "proxima_accion_fecha": day_after_tomorrow.strftime("%d/%m/%Y"),
                "estado": "Piloto aceptado",
                "responsable_cliente": "David Ortiz",
            },
        ]
    )


def test_filter_by_persona_proxima_accion() -> None:
    df = _sample_df()
    filtered = filter_by_persona_proxima_accion(df, "David Ortiz")
    assert set(filtered["contact_id"].tolist()) == {"c1", "c2", "c4", "c5"}


def test_filter_by_persona_empty_returns_all() -> None:
    df = _sample_df()
    assert len(filter_by_persona_proxima_accion(df, "")) == 5


def test_filter_by_contact_estado_empty_returns_all() -> None:
    df = _sample_df()
    assert len(filter_by_contact_estado(df, "")) == 5


def test_filter_by_contact_estado_matches_canonical() -> None:
    df = _sample_df()
    filtered = filter_by_contact_estado(df, "Piloto activo")
    assert list(filtered["contact_id"]) == ["c3"]


def test_filter_by_contact_estado_normalizes_legacy_value() -> None:
    df = pd.DataFrame(
        [
            {
                "contact_id": "legacy",
                "estado": "En Contacto",
                "proxima_accion_fecha": "01/01/2099",
            }
        ]
    )
    filtered = filter_by_contact_estado(df, "Contacto inicial")
    assert len(filtered) == 1


def test_filter_by_responsable_cliente_empty_returns_all() -> None:
    df = _sample_df()
    assert len(filter_by_responsable_cliente(df, "")) == 5


def test_filter_by_responsable_cliente_matches_exact_name() -> None:
    df = _sample_df()
    filtered = filter_by_responsable_cliente(df, "David Ortiz")
    assert set(filtered["contact_id"].tolist()) == {"c1", "c4", "c5"}


def test_filter_by_responsable_cliente_excludes_unassigned() -> None:
    df = _sample_df()
    filtered = filter_by_responsable_cliente(df, "Marco Ruano")
    assert list(filtered["contact_id"]) == ["c2"]


def test_next_action_bucket_counts_respects_persona_scope() -> None:
    today = date.today()
    df = _sample_df()
    scoped = filter_by_persona_proxima_accion(df, "David Ortiz")
    counts = next_action_bucket_counts(scoped, today=today)
    assert counts == {"past": 1, "today": 1, "tomorrow": 1, "future": 1}


def test_apply_dash_bucket_with_persona() -> None:
    today = date.today()
    df = _sample_df()
    scoped = filter_by_persona_proxima_accion(df, "David Ortiz")
    today_rows = apply_dash_bucket_date_filter(scoped, "today", today=today)
    assert list(today_rows["contact_id"]) == ["c2"]


def test_apply_dash_bucket_future() -> None:
    today = date.today()
    tomorrow = today + timedelta(days=1)
    future_day = today + timedelta(days=2)
    df = pd.DataFrame(
        [
            {
                "contact_id": "tomorrow",
                "proxima_accion_fecha": tomorrow.strftime("%d/%m/%Y"),
            },
            {
                "contact_id": "future",
                "proxima_accion_fecha": future_day.strftime("%d/%m/%Y"),
            },
        ]
    )
    future_rows = apply_dash_bucket_date_filter(df, "future", today=today)
    assert list(future_rows["contact_id"]) == ["future"]
    tomorrow_rows = apply_dash_bucket_date_filter(df, "tomorrow", today=today)
    assert list(tomorrow_rows["contact_id"]) == ["tomorrow"]


def test_bucket_filter_accepts_iso_proxima_fecha() -> None:
    today = date.today()
    df = pd.DataFrame(
        [
            {
                "contact_id": "c_iso",
                "persona_proxima_accion": "David Ortiz",
                "proxima_accion_fecha": today.strftime("%Y-%m-%d"),
            }
        ]
    )
    counts = next_action_bucket_counts(df, today=today)
    assert counts["today"] == 1
    filtered = apply_dash_bucket_date_filter(df, "today", today=today)
    assert len(filtered) == 1
