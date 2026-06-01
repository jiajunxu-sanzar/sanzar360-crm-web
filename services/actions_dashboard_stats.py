"""Agregaciones para el dashboard «Acciones» (seguimiento comercial)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

from app.navigation import ROLES_WITH_ACCIONES_PAGE
from config.settings import CANAL_CONTACTO_OPCIONES
from services.contact_proxima_index import _parse_contact_datetime

CANAL_KEYS: tuple[str, ...] = CANAL_CONTACTO_OPCIONES


@dataclass(frozen=True)
class CanalBreakdown:
    total: int = 0
    exitosos: int = 0
    fallidos: int = 0


@dataclass(frozen=True)
class PersonCanalWeekStats:
    persona_contacto: str
    total: int
    exitosos: int
    fallidos: int
    by_canal: dict[str, CanalBreakdown] = field(default_factory=dict)


@dataclass(frozen=True)
class PersonWeekSnapshot:
    week_start: date
    week_end: date
    total_acciones: int
    contactos_unicos: int
    exitosos: int
    fallidos: int
    by_canal: dict[str, CanalBreakdown] = field(default_factory=dict)


@dataclass(frozen=True)
class PersonPerformanceAverages:
    weeks_with_activity: int
    avg_acciones_per_week: float
    avg_contactos_unicos_per_week: float
    avg_success_rate_pct: float
    total_acciones: int
    total_exitosos: int
    total_fallidos: int


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


def _normalize_persona(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "(sin persona)"


def _normalize_canal(value: object) -> str:
    return str(value or "").strip().lower()


def _is_exitoso(resultado: str) -> bool:
    return str(resultado or "").strip().lower() == "exitoso"


def _is_fallido(resultado: str) -> bool:
    return str(resultado or "").strip().lower() == "fallido"


def _empty_canal_breakdown() -> dict[str, CanalBreakdown]:
    return {canal: CanalBreakdown() for canal in CANAL_KEYS}


def _accumulate_canal(breakdown: dict[str, CanalBreakdown], canal: str, resultado: str) -> dict[str, CanalBreakdown]:
    key = canal if canal in breakdown else ""
    if key not in breakdown:
        return breakdown
    current = breakdown[key]
    exitosos = current.exitosos + (1 if _is_exitoso(resultado) else 0)
    fallidos = current.fallidos + (1 if _is_fallido(resultado) else 0)
    updated = CanalBreakdown(total=current.total + 1, exitosos=exitosos, fallidos=fallidos)
    return {**breakdown, key: updated}


def current_iso_week_bounds(today: date | None = None) -> tuple[date, date]:
    d = today or date.today()
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def iso_week_bounds_for_offset(offset: int, today: date | None = None) -> tuple[date, date]:
    ws, _ = current_iso_week_bounds(today)
    shifted = ws + timedelta(weeks=offset)
    return shifted, shifted + timedelta(days=6)


def filter_rows_in_week(
    df: pd.DataFrame,
    week_start: date,
    week_end: date,
) -> list[dict[str, str]]:
    if df.empty or "fecha_contacto" not in df.columns:
        return []
    work = df.fillna("").astype(str)
    in_week: list[dict[str, str]] = []
    for row in work.to_dict("records"):
        when = _parse_row_datetime(row)
        if when is None:
            continue
        d = when.date()
        if week_start <= d <= week_end:
            in_week.append(row)
    return in_week


def _summarize_rows(rows: list[dict[str, str]], week_start: date, week_end: date) -> CommercialWeekSummary:
    empty_person = pd.DataFrame(columns=["persona_contacto", "total", "exitosos", "fallidos"])
    if not rows:
        return CommercialWeekSummary(
            week_start=week_start,
            week_end=week_end,
            total_contacts=0,
            exitosos=0,
            fallidos=0,
            by_person=empty_person,
        )
    sub = pd.DataFrame(rows)
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
        week_start=week_start,
        week_end=week_end,
        total_contacts=len(sub),
        exitosos=exitosos,
        fallidos=fallidos,
        by_person=agg,
    )


def summarize_commercial_week(
    df: pd.DataFrame,
    *,
    today: date | None = None,
    week_offset: int = 0,
) -> CommercialWeekSummary:
    ws, we = iso_week_bounds_for_offset(week_offset, today)
    rows = filter_rows_in_week(df, ws, we)
    return _summarize_rows(rows, ws, we)


def summarize_person_canal_week(
    df: pd.DataFrame,
    week_start: date,
    week_end: date,
) -> list[PersonCanalWeekStats]:
    rows = filter_rows_in_week(df, week_start, week_end)
    if not rows:
        return []

    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        persona = _normalize_persona(row.get("persona_contacto"))
        resultado = str(row.get("resultado_contacto", "") or "")
        canal = _normalize_canal(row.get("canal_contacto"))
        bucket = grouped.setdefault(
            persona,
            {
                "total": 0,
                "exitosos": 0,
                "fallidos": 0,
                "by_canal": _empty_canal_breakdown(),
            },
        )
        bucket["total"] = int(bucket["total"]) + 1
        if _is_exitoso(resultado):
            bucket["exitosos"] = int(bucket["exitosos"]) + 1
        if _is_fallido(resultado):
            bucket["fallidos"] = int(bucket["fallidos"]) + 1
        bucket["by_canal"] = _accumulate_canal(bucket["by_canal"], canal, resultado)  # type: ignore[arg-type]

    stats = [
        PersonCanalWeekStats(
            persona_contacto=persona,
            total=int(values["total"]),
            exitosos=int(values["exitosos"]),
            fallidos=int(values["fallidos"]),
            by_canal=values["by_canal"],  # type: ignore[arg-type]
        )
        for persona, values in grouped.items()
    ]
    return sorted(stats, key=lambda item: item.total, reverse=True)


def commercial_team_roster(users: list[object]) -> list[str]:
    """Nombres de usuarios con rol admin, agro_team o sales (pestaña Acciones)."""
    names: list[str] = []
    for user in users:
        role = str(getattr(user, "role", "") or "").strip().lower()
        nombre = str(getattr(user, "nombre", "") or "").strip()
        if role in ROLES_WITH_ACCIONES_PAGE and nombre:
            names.append(nombre)
    return sorted(set(names), key=str.casefold)


def merge_person_canal_week_with_roster(
    stats: list[PersonCanalWeekStats],
    roster: list[str],
) -> list[PersonCanalWeekStats]:
    """Incluye todo el equipo comercial aunque no tenga acciones en la semana."""
    by_name = {item.persona_contacto: item for item in stats}
    roster_set = set(roster)
    merged: list[PersonCanalWeekStats] = []
    for name in roster:
        if name in by_name:
            merged.append(by_name[name])
        else:
            merged.append(
                PersonCanalWeekStats(
                    persona_contacto=name,
                    total=0,
                    exitosos=0,
                    fallidos=0,
                    by_canal=_empty_canal_breakdown(),
                )
            )
    extras = [item for item in stats if item.persona_contacto not in roster_set]
    merged.extend(sorted(extras, key=lambda item: item.total, reverse=True))
    return merged


def _snapshot_from_rows(rows: list[dict[str, str]], week_start: date, week_end: date) -> PersonWeekSnapshot:
    if not rows:
        return PersonWeekSnapshot(
            week_start=week_start,
            week_end=week_end,
            total_acciones=0,
            contactos_unicos=0,
            exitosos=0,
            fallidos=0,
            by_canal=_empty_canal_breakdown(),
        )
    exitosos = sum(1 for row in rows if _is_exitoso(str(row.get("resultado_contacto", ""))))
    fallidos = sum(1 for row in rows if _is_fallido(str(row.get("resultado_contacto", ""))))
    contact_ids = {
        str(row.get("contact_id", "") or "").strip()
        for row in rows
        if str(row.get("contact_id", "") or "").strip()
    }
    by_canal = _empty_canal_breakdown()
    for row in rows:
        by_canal = _accumulate_canal(
            by_canal,
            _normalize_canal(row.get("canal_contacto")),
            str(row.get("resultado_contacto", "") or ""),
        )
    return PersonWeekSnapshot(
        week_start=week_start,
        week_end=week_end,
        total_acciones=len(rows),
        contactos_unicos=len(contact_ids),
        exitosos=exitosos,
        fallidos=fallidos,
        by_canal=by_canal,
    )


def person_performance_last_months(
    df: pd.DataFrame,
    persona: str,
    *,
    months: int = 3,
    today: date | None = None,
) -> list[PersonWeekSnapshot]:
    target = _normalize_persona(persona)
    if target == "(sin persona)":
        persona_filter = lambda row: not str(row.get("persona_contacto", "") or "").strip()
    else:
        persona_filter = lambda row: _normalize_persona(row.get("persona_contacto")) == target

    d = today or date.today()
    current_ws, _ = current_iso_week_bounds(d)
    weeks_back = max(1, int(months * 52 / 12))
    snapshots: list[PersonWeekSnapshot] = []

    for offset in range(0, -weeks_back, -1):
        ws, we = iso_week_bounds_for_offset(offset, d)
        rows = filter_rows_in_week(df, ws, we)
        person_rows = [row for row in rows if persona_filter(row)]
        snapshots.append(_snapshot_from_rows(person_rows, ws, we))

    return snapshots


def person_performance_averages(snapshots: list[PersonWeekSnapshot]) -> PersonPerformanceAverages:
    active = [snap for snap in snapshots if snap.total_acciones > 0]
    if not active:
        return PersonPerformanceAverages(
            weeks_with_activity=0,
            avg_acciones_per_week=0.0,
            avg_contactos_unicos_per_week=0.0,
            avg_success_rate_pct=0.0,
            total_acciones=0,
            total_exitosos=0,
            total_fallidos=0,
        )
    total_acciones = sum(snap.total_acciones for snap in active)
    total_exitosos = sum(snap.exitosos for snap in active)
    total_fallidos = sum(snap.fallidos for snap in active)
    avg_acciones = total_acciones / len(active)
    avg_contactos = sum(snap.contactos_unicos for snap in active) / len(active)
    avg_rate = (total_exitosos / total_acciones * 100) if total_acciones else 0.0
    return PersonPerformanceAverages(
        weeks_with_activity=len(active),
        avg_acciones_per_week=round(avg_acciones, 1),
        avg_contactos_unicos_per_week=round(avg_contactos, 1),
        avg_success_rate_pct=round(avg_rate, 1),
        total_acciones=total_acciones,
        total_exitosos=total_exitosos,
        total_fallidos=total_fallidos,
    )


def success_rate_by_canal(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "canal_contacto" not in df.columns:
        return pd.DataFrame(columns=["canal_contacto", "total", "exitosos", "fallidos", "tasa_exito"])
    sub = df.fillna("").astype(str)
    sub["_c"] = sub["canal_contacto"].str.strip().str.lower()
    sub = sub[sub["_c"] != ""]
    if sub.empty:
        return pd.DataFrame(columns=["canal_contacto", "total", "exitosos", "fallidos", "tasa_exito"])
    agg = (
        sub.groupby("_c", dropna=False)
        .agg(
            total=("resultado_contacto", "count"),
            exitosos=("resultado_contacto", lambda s: int((s.str.lower() == "exitoso").sum())),
            fallidos=("resultado_contacto", lambda s: int((s.str.lower() == "fallido").sum())),
        )
        .reset_index()
        .rename(columns={"_c": "canal_contacto"})
    )
    agg["tasa_exito"] = (agg["exitosos"] / agg["total"].clip(lower=1) * 100).round(1)
    return agg.sort_values("total", ascending=False)
