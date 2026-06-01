from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime((value or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def filter_by_persona_proxima_accion(df: pd.DataFrame, persona: str) -> pd.DataFrame:
    """Keep rows whose persona_proxima_accion matches (exact, trimmed). Empty persona = no filter."""
    clean = (persona or "").strip()
    if not clean or df.empty or "persona_proxima_accion" not in df.columns:
        return df
    col = df["persona_proxima_accion"].fillna("").astype(str).str.strip()
    return df[col == clean]


def next_action_bucket_counts(df: pd.DataFrame, *, today: date | None = None) -> dict[str, int]:
    """Count contacts by próxima acción date bucket (past / today / tomorrow)."""
    counts = {"past": 0, "today": 0, "tomorrow": 0}
    if df.empty or "proxima_accion_fecha" not in df.columns:
        return counts
    ref = today or date.today()
    tomorrow_date = ref + timedelta(days=1)
    for row in df.fillna("").astype(str).to_dict("records"):
        due = _parse_date(row.get("proxima_accion_fecha", ""))
        if due is None:
            continue
        if due < ref:
            counts["past"] += 1
        elif due == ref:
            counts["today"] += 1
        elif due == tomorrow_date:
            counts["tomorrow"] += 1
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
    next_actions = pd.to_datetime(
        df["proxima_accion_fecha"].fillna("").astype(str),
        format="%d/%m/%Y",
        errors="coerce",
    )
    ts = pd.Timestamp(ref)
    if bucket == "past":
        return df[next_actions < ts]
    if bucket == "today":
        return df[next_actions == ts]
    if bucket == "tomorrow":
        return df[next_actions == (ts + pd.Timedelta(days=1))]
    return df


def upcoming_actions(df: pd.DataFrame, *, days: int = 14) -> list[dict[str, str]]:
    if df.empty or "proxima_accion_fecha" not in df.columns:
        return []
    today = date.today()
    rows: list[dict[str, str]] = []
    for row in df.fillna("").astype(str).to_dict("records"):
        due = _parse_date(row.get("proxima_accion_fecha", ""))
        if due and 0 <= (due - today).days <= days:
            rows.append(row)
    return sorted(rows, key=lambda row: _parse_date(row.get("proxima_accion_fecha", "")) or date.max)


def overdue_actions(df: pd.DataFrame) -> list[dict[str, str]]:
    if df.empty or "proxima_accion_fecha" not in df.columns:
        return []
    today = date.today()
    rows: list[dict[str, str]] = []
    for row in df.fillna("").astype(str).to_dict("records"):
        due = _parse_date(row.get("proxima_accion_fecha", ""))
        if due and due < today:
            rows.append(row)
    return sorted(rows, key=lambda row: _parse_date(row.get("proxima_accion_fecha", "")) or date.max)
