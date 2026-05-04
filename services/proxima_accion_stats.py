from __future__ import annotations

from datetime import date, datetime

import pandas as pd


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime((value or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


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
