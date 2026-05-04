"""Agregaciones para el dashboard «Acciones» (log de pestaña Acciones / Google Sheet)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

COUNTED_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "batch email",
        "seguimiento comercial",
    }
)

SIN_PERSONA_LABEL: str = "(sin persona)"


@dataclass(frozen=True)
class ActionsWeekSummary:
    """Ventana temporal y agregados por persona (solo conteos > 0 en total)."""

    week_start: date
    week_end: date
    by_person: pd.DataFrame  # persona, batch_email, seguimiento_comercial, total


def _normalize_action_type(raw: object) -> str:
    return ("" if raw is None else str(raw)).strip().lower()


def _parse_row_datetime(raw: object) -> datetime | None:
    s = ("" if raw is None else str(raw)).strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def monday_of_date(d: date) -> date:
    """Lunes de la semana calendario (ISO lunes-first) que contiene ``d``."""
    return d - timedelta(days=d.weekday())


def current_iso_week_bounds(today: date | None = None) -> tuple[date, date]:
    """Semana ISO **en curso** que contiene `today` (lunes–domingo)."""
    d = today or date.today()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def summarize_actions_current_week(df: pd.DataFrame, *, today: date | None = None) -> ActionsWeekSummary:
    """Filtra tipos relevantes en la semana actual (lunes–domingo) y agrega por ``persona``.

    Omit personas con total 0 (no aparecen en ``by_person``).
    Filas sin ``persona`` se agrupan en ``"(sin persona)"`` si tienen fecha válida."""
    ws, we = current_iso_week_bounds(today)

    if df.empty or not all(c in df.columns for c in ("fecha_accion", "tipo_accion", "persona")):
        return ActionsWeekSummary(week_start=ws, week_end=we, by_person=_empty_by_person())

    work = df.copy()
    parsed_list = [_parse_row_datetime(x) for x in work["fecha_accion"].tolist()]
    work["_ts"] = pd.to_datetime(parsed_list)
    types = work["tipo_accion"].apply(_normalize_action_type)
    day_series = work["_ts"].dt.date
    in_window = work["_ts"].notna() & (day_series >= ws) & (day_series <= we)
    counted = types.isin(COUNTED_ACTION_TYPES)
    sub = work.loc[in_window & counted].copy()
    if sub.empty:
        return ActionsWeekSummary(week_start=ws, week_end=we, by_person=_empty_by_person())

    sub["_persona"] = sub["persona"].fillna("").astype(str).str.strip()
    sub.loc[sub["_persona"] == "", "_persona"] = SIN_PERSONA_LABEL

    sub["_be"] = (sub["tipo_accion"].apply(_normalize_action_type) == "batch email").astype(int)
    sub["_sc"] = (
        sub["tipo_accion"].apply(_normalize_action_type) == "seguimiento comercial"
    ).astype(int)

    agg = (
        sub.groupby("_persona", dropna=False)
        .agg(batch_email=("_be", "sum"), seguimiento_comercial=("_sc", "sum"))
        .reset_index()
        .rename(columns={"_persona": "persona"})
    )
    agg["total"] = agg["batch_email"] + agg["seguimiento_comercial"]
    agg = agg.loc[agg["total"] > 0].sort_values("total", ascending=False).reset_index(drop=True)
    return ActionsWeekSummary(week_start=ws, week_end=we, by_person=agg)


def _empty_by_person() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["persona", "batch_email", "seguimiento_comercial", "total"],
    )


def _normalized_persona_series(raw: pd.Series) -> pd.Series:
    s = raw.fillna("").astype(str).str.strip()
    return s.mask(s.eq(""), SIN_PERSONA_LABEL)


def personas_with_counted_actions(df: pd.DataFrame) -> list[str]:
    """Personas únicas que tienen alguna fila contabilizable (orden alfabético)."""
    if df.empty or not all(c in df.columns for c in ("fecha_accion", "tipo_accion", "persona")):
        return []

    parsed = [_parse_row_datetime(x) for x in df["fecha_accion"].tolist()]
    ts = pd.to_datetime(parsed)
    types = df["tipo_accion"].apply(_normalize_action_type)
    ok = ts.notna() & types.isin(COUNTED_ACTION_TYPES)
    if not bool(ok.any()):
        return []

    personas = sorted(_normalized_persona_series(df.loc[ok, "persona"]).astype(str).unique().tolist())
    return personas


def weekly_breakdown_for_person(df: pd.DataFrame, *, persona_display: str) -> pd.DataFrame:
    """Filas agrupadas por semana ISO (lunes–domingo) solo para esa persona."""
    empty = pd.DataFrame(
        columns=[
            "semana_desde",
            "semana_hasta",
            "batch_email",
            "seguimiento_comercial",
            "total",
        ]
    )
    if df.empty or not persona_display.strip():
        return empty

    if not all(c in df.columns for c in ("fecha_accion", "tipo_accion", "persona")):
        return empty

    work = df.copy()
    parsed_list = [_parse_row_datetime(x) for x in work["fecha_accion"].tolist()]
    work["_ts"] = pd.to_datetime(parsed_list)
    types = work["tipo_accion"].apply(_normalize_action_type)
    counted = types.isin(COUNTED_ACTION_TYPES)
    work = work.loc[counted & work["_ts"].notna()].copy()
    if work.empty:
        return empty

    disp = persona_display.strip()
    work["_p"] = _normalized_persona_series(work["persona"])
    sel = work.loc[work["_p"].astype(str) == disp].copy()
    if sel.empty:
        return empty

    sel["_d"] = sel["_ts"].dt.normalize().dt.date
    sel["_monday"] = sel["_d"].apply(monday_of_date)
    sel["_be"] = (sel["tipo_accion"].apply(_normalize_action_type) == "batch email").astype(int)
    sel["_sc"] = (sel["tipo_accion"].apply(_normalize_action_type) == "seguimiento comercial").astype(
        int
    )

    out = (
        sel.groupby("_monday", dropna=False)
        .agg(batch_email=("_be", "sum"), seguimiento_comercial=("_sc", "sum"))
        .reset_index()
        .rename(columns={"_monday": "semana_desde"})
    )
    out["semana_hasta"] = out["semana_desde"].apply(lambda m: m + timedelta(days=6))
    out["total"] = out["batch_email"] + out["seguimiento_comercial"]
    out = (
        out.sort_values("semana_desde", ascending=False)
        .reset_index(drop=True)[
            ["semana_desde", "semana_hasta", "batch_email", "seguimiento_comercial", "total"]
        ]
    )
    return out


__all__ = [
    "ActionsWeekSummary",
    "COUNTED_ACTION_TYPES",
    "SIN_PERSONA_LABEL",
    "current_iso_week_bounds",
    "monday_of_date",
    "personas_with_counted_actions",
    "weekly_breakdown_for_person",
    "summarize_actions_current_week",
]
