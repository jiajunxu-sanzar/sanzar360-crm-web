"""Agregaciones para el dashboard «Acciones» (seguimiento comercial)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from services.contact_proxima_index import _parse_contact_datetime


@dataclass(frozen=True)
class CommercialWeekSummary:
    week_start: date
    week_end: date
    total_contacts: int
    exitosos: int
    fallidos: int
    by_person: pd.DataFrame  # persona_contacto, total, exitosos, fallidos


def _parse_row_datetime(row: dict[str, str]) -> datetime | None:
    return _parse_contact_datetime(
        str(row.get("fecha_contacto", "") or ""),
        str(row.get("hora_contacto", "") or ""),
    )


def current_iso_week_bounds(today: date | None = None) -> tuple[date, date]:
    d = today or date.today()
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def summarize_commercial_week(df: pd.DataFrame, *, today: date | None = None) -> CommercialWeekSummary:
    ws, we = current_iso_week_bounds(today)
    empty_person = pd.DataFrame(columns=["persona_contacto", "total", "exitosos", "fallidos"])
    if df.empty or "fecha_contacto" not in df.columns:
        return CommercialWeekSummary(week_start=ws, week_end=we, total_contacts=0, exitosos=0, fallidos=0, by_person=empty_person)

    work = df.fillna("").astype(str).copy()
    in_week: list[dict[str, str]] = []
    for row in work.to_dict("records"):
        when = _parse_row_datetime(row)
        if when is None:
            continue
        d = when.date()
        if ws <= d <= we:
            in_week.append(row)

    if not in_week:
        return CommercialWeekSummary(week_start=ws, week_end=we, total_contacts=0, exitosos=0, fallidos=0, by_person=empty_person)

    sub = pd.DataFrame(in_week)
    exitosos = int((sub["resultado_contacto"].str.lower() == "exitoso").sum())
    fallidos = int((sub["resultado_contacto"].str.lower() == "fallido").sum())
    sub["_p"] = sub["persona_contacto"].fillna("").astype(str).str.strip()
    sub.loc[sub["_p"] == "", "_p"] = "(sin persona)"
    agg = (
        sub.groupby("_p", dropna=False)
        .agg(
            total=("resultado_contacto", "count"),
            exitosos=("resultado_contacto", lambda s: int((s.str.lower() == "exitoso").sum())),
            fallidos=("resultado_contacto", lambda s: int((s.str.lower() == "fallido").sum())),
        )
        .reset_index()
        .rename(columns={"_p": "persona_contacto"})
        .sort_values("total", ascending=False)
    )
    return CommercialWeekSummary(
        week_start=ws,
        week_end=we,
        total_contacts=len(sub),
        exitosos=exitosos,
        fallidos=fallidos,
        by_person=agg,
    )


def success_rate_by_canal(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "canal_contacto" not in df.columns:
        return pd.DataFrame(columns=["canal_contacto", "total", "exitosos", "tasa_exito"])
    sub = df.fillna("").astype(str)
    sub["_c"] = sub["canal_contacto"].str.strip().str.lower()
    sub = sub[sub["_c"] != ""]
    if sub.empty:
        return pd.DataFrame(columns=["canal_contacto", "total", "exitosos", "tasa_exito"])
    agg = (
        sub.groupby("_c", dropna=False)
        .agg(
            total=("resultado_contacto", "count"),
            exitosos=("resultado_contacto", lambda s: int((s.str.lower() == "exitoso").sum())),
        )
        .reset_index()
        .rename(columns={"_c": "canal_contacto"})
    )
    agg["tasa_exito"] = (agg["exitosos"] / agg["total"].clip(lower=1) * 100).round(1)
    return agg.sort_values("total", ascending=False)


def contacts_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["hora", "total"])
    buckets: dict[str, int] = {}
    for row in df.fillna("").astype(str).to_dict("records"):
        hora = str(row.get("hora_contacto", "") or "").strip()
        if not hora or ":" not in hora:
            continue
        hour = hora.split(":", 1)[0].zfill(2)
        buckets[hour] = buckets.get(hour, 0) + 1
    if not buckets:
        return pd.DataFrame(columns=["hora", "total"])
    out = pd.DataFrame([{"hora": h, "total": buckets[h]} for h in sorted(buckets)])
    return out
