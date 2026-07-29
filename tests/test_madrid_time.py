"""Tests del reloj Europe/Madrid del CRM."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from services.madrid_time import (
    TZ_MADRID,
    madrid_dd_mm_yyyy,
    madrid_hh_mm,
    now_madrid,
    today_madrid,
)


def test_tz_is_europe_madrid() -> None:
    assert TZ_MADRID == ZoneInfo("Europe/Madrid")


def test_now_madrid_is_aware_and_madrid() -> None:
    now = now_madrid()
    assert now.tzinfo is not None
    assert now.tzinfo == TZ_MADRID


def test_today_and_formats_match_now() -> None:
    now = now_madrid()
    assert today_madrid() == now.date()
    assert madrid_dd_mm_yyyy() == now.strftime("%d/%m/%Y")
    assert madrid_hh_mm() == now.strftime("%H:%M")


def test_madrid_ahead_of_utc_in_summer(monkeypatch) -> None:
    """En CEST, Madrid es UTC+2: 12:00 UTC → 14:00 Madrid."""
    fixed = datetime(2026, 7, 29, 12, 0, tzinfo=ZoneInfo("UTC"))

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz is not None else fixed.replace(tzinfo=None)

    monkeypatch.setattr("services.madrid_time.datetime", _FixedDatetime)
    assert madrid_hh_mm() == "14:00"
    assert madrid_dd_mm_yyyy() == "29/07/2026"
