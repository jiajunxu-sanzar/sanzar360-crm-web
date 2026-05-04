from __future__ import annotations

from datetime import date, datetime

import pandas as pd


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime((value or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def stagnation_alarms(df: pd.DataFrame, *, max_days: int = 21) -> list[dict[str, str]]:
    if df.empty:
        return []
    today = date.today()
    alarms: list[dict[str, str]] = []
    for row in df.fillna("").astype(str).to_dict("records"):
        changed = _parse_date(row.get("fecha_estado", ""))
        estado = row.get("estado", "")
        if not changed or estado.lower() in {"cliente", "perdido"}:
            continue
        days = (today - changed).days
        if days >= max_days:
            alarm = dict(row)
            alarm["dias_en_estado"] = str(days)
            alarms.append(alarm)
    return sorted(alarms, key=lambda row: int(row.get("dias_en_estado", "0")), reverse=True)
