from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from config.contact_estado import (
    is_terminal_contact_estado,
    normalize_contact_estado,
    stagnation_threshold_days,
)


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime((value or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def stagnation_alarms(df: pd.DataFrame) -> list[dict[str, str]]:
    if df.empty:
        return []
    today = date.today()
    alarms: list[dict[str, str]] = []
    for row in df.fillna("").astype(str).to_dict("records"):
        changed = _parse_date(row.get("fecha_estado", ""))
        estado_norm = normalize_contact_estado(row.get("estado", ""))
        if not changed or not estado_norm or is_terminal_contact_estado(estado_norm):
            continue
        threshold = stagnation_threshold_days(estado_norm)
        if threshold is None:
            continue
        days = (today - changed).days
        if days >= threshold:
            alarm = dict(row)
            alarm["dias_en_estado"] = str(days)
            alarm["umbral_estado"] = str(threshold)
            alarm["estado_normalizado"] = estado_norm
            alarms.append(alarm)
    return sorted(alarms, key=lambda row: int(row.get("dias_en_estado", "0")), reverse=True)
