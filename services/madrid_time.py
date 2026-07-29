"""Reloj del CRM fijo a Europe/Madrid (independiente de la TZ del servidor)."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ_MADRID = ZoneInfo("Europe/Madrid")


def now_madrid() -> datetime:
    return datetime.now(TZ_MADRID)


def today_madrid() -> date:
    return now_madrid().date()


def madrid_hh_mm() -> str:
    return now_madrid().strftime("%H:%M")


def madrid_dd_mm_yyyy() -> str:
    return today_madrid().strftime("%d/%m/%Y")
