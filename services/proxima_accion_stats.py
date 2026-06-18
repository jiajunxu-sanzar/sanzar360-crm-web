from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from config.contact_estado import normalize_contact_estado
from services.sheet_date_format import parse_sheet_date


def filter_by_persona_proxima_accion(df: pd.DataFrame, persona: str) -> pd.DataFrame:
    """Keep rows whose persona_proxima_accion matches (exact, trimmed). Empty persona = no filter."""
    clean = (persona or "").strip()
    if not clean or df.empty or "persona_proxima_accion" not in df.columns:
        return df
    col = df["persona_proxima_accion"].fillna("").astype(str).str.strip()
    return df[col == clean]


def filter_by_contact_estado(df: pd.DataFrame, estado: str) -> pd.DataFrame:
    """Keep rows whose commercial estado matches (normalized). Empty estado = no filter."""
    target = normalize_contact_estado(str(estado or "").strip())
    if not target or df.empty or "estado" not in df.columns:
        return df
    normalized = df["estado"].fillna("").astype(str).map(normalize_contact_estado)
    return df[normalized == target]


def filter_by_responsable_cliente(df: pd.DataFrame, responsable: str) -> pd.DataFrame:
    """Keep rows whose responsable_cliente matches (exact, trimmed). Empty = no filter."""
    clean = (responsable or "").strip()
    if not clean or df.empty or "responsable_cliente" not in df.columns:
        return df
    col = df["responsable_cliente"].fillna("").astype(str).str.strip()
    return df[col == clean]


def next_action_bucket_counts(df: pd.DataFrame, *, today: date | None = None) -> dict[str, int]:
    """Count contacts by próxima acción date bucket (past / today / tomorrow / future)."""
    counts = {"past": 0, "today": 0, "tomorrow": 0, "future": 0}
    if df.empty or "proxima_accion_fecha" not in df.columns:
        return counts
    ref = today or date.today()
    tomorrow_date = ref + timedelta(days=1)
    future_from = ref + timedelta(days=2)
    for row in df.fillna("").astype(str).to_dict("records"):
        due = parse_sheet_date(str(row.get("proxima_accion_fecha", "") or ""))
        if due is None:
            continue
        if due < ref:
            counts["past"] += 1
        elif due == ref:
            counts["today"] += 1
        elif due == tomorrow_date:
            counts["tomorrow"] += 1
        elif due >= future_from:
            counts["future"] += 1
    return counts


def apply_dash_bucket_date_filter(
    df: pd.DataFrame,
    dash_bucket: str,
    *,
    today: date | None = None,
) -> pd.DataFrame:
    """Filter contacts by próxima acción date bucket used in the contacts dashboard."""
    bucket = (dash_bucket or "").strip().lower()
    if not bucket or df.empty or "proxima_accion_fecha" not in df.columns:
        return df
    ref = today or date.today()
    tomorrow_date = ref + timedelta(days=1)
    future_from = ref + timedelta(days=2)
    parsed = df["proxima_accion_fecha"].fillna("").astype(str).map(parse_sheet_date)
    if bucket == "past":
        return df[parsed.map(lambda d: d is not None and d < ref)]
    if bucket == "today":
        return df[parsed == ref]
    if bucket == "tomorrow":
        return df[parsed == tomorrow_date]
    if bucket == "future":
        return df[parsed.map(lambda d: d is not None and d >= future_from)]
    return df


def upcoming_actions(df: pd.DataFrame, *, days: int = 14) -> list[dict[str, str]]:
    if df.empty or "proxima_accion_fecha" not in df.columns:
        return []
    today = date.today()
    rows: list[dict[str, str]] = []
    for row in df.fillna("").astype(str).to_dict("records"):
        due = parse_sheet_date(str(row.get("proxima_accion_fecha", "") or ""))
        if due and 0 <= (due - today).days <= days:
            rows.append(row)
    return sorted(
        rows,
        key=lambda row: parse_sheet_date(str(row.get("proxima_accion_fecha", "") or "")) or date.max,
    )


def overdue_actions(df: pd.DataFrame) -> list[dict[str, str]]:
    if df.empty or "proxima_accion_fecha" not in df.columns:
        return []
    today = date.today()
    rows: list[dict[str, str]] = []
    for row in df.fillna("").astype(str).to_dict("records"):
        due = parse_sheet_date(str(row.get("proxima_accion_fecha", "") or ""))
        if due and due < today:
            rows.append(row)
    return sorted(
        rows,
        key=lambda row: parse_sheet_date(str(row.get("proxima_accion_fecha", "") or "")) or date.max,
    )
