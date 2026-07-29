"""Validación y visualización del histórico de riegos asociado a campañas."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

import matplotlib.pyplot as plt

from services.locale_numbers import parse_locale_float
from services.sheet_date_format import is_valid_dd_mm_yyyy, normalize_dd_mm_yyyy

_HH_MM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_es_nota(raw: object) -> bool:
    """Normaliza el flag es_nota desde Sheets (true/false/sí/1/…)."""
    text = str(raw or "").strip().lower()
    if not text:
        return False
    return text in {"true", "1", "sí", "si", "yes", "y", "verdadero", "x"}


def serialize_es_nota(flag: bool) -> str:
    return "true" if flag else "false"


def is_valid_hh_mm(value: str) -> bool:
    return bool(_HH_MM_RE.match(str(value or "").strip()))


def parse_riego_start(dia_riego: str, hora_inicio_riego: str) -> datetime | None:
    dia = normalize_dd_mm_yyyy(str(dia_riego or "").strip()) or str(dia_riego or "").strip()
    hora = str(hora_inicio_riego or "").strip()
    if not dia or not is_valid_dd_mm_yyyy(dia) or not is_valid_hh_mm(hora):
        return None
    try:
        return datetime.strptime(f"{dia} {hora}", "%d/%m/%Y %H:%M")
    except ValueError:
        return None


def validate_riego_campana_values(values: dict[str, str]) -> str | None:
    """Valida una fila de riego/nota. Devuelve mensaje de error o None."""
    es_nota = parse_es_nota(values.get("es_nota", ""))
    dia = normalize_dd_mm_yyyy(str(values.get("dia_riego", "") or "").strip()) or str(
        values.get("dia_riego", "") or ""
    ).strip()
    hora = str(values.get("hora_inicio_riego", "") or "").strip()

    if not dia:
        return "Indica el día de riego (DD/MM/YYYY)."
    if not is_valid_dd_mm_yyyy(dia):
        return "El día de riego debe tener formato DD/MM/YYYY."
    if not hora or not is_valid_hh_mm(hora):
        return "Indica la hora de inicio (HH:MM)."

    if es_nota:
        if not str(values.get("nota", "") or "").strip():
            return "Si es una nota, el campo nota es obligatorio."
        return None

    horas = parse_locale_float(values.get("horas_riego", ""))
    litros = parse_locale_float(values.get("litros", ""))
    if horas is None or horas < 0:
        return "Horas de riego debe ser un número ≥ 0."
    if litros is None or litros < 0:
        return "Litros debe ser un número ≥ 0."
    return None


def normalize_riego_row_values(values: dict[str, str]) -> dict[str, str]:
    """Normaliza campos antes de persistir."""
    out = {k: str(v or "") for k, v in values.items()}
    es_nota = parse_es_nota(out.get("es_nota", ""))
    out["es_nota"] = serialize_es_nota(es_nota)
    dia = normalize_dd_mm_yyyy(out.get("dia_riego", "")) or out.get("dia_riego", "")
    out["dia_riego"] = dia
    out["hora_inicio_riego"] = str(out.get("hora_inicio_riego", "") or "").strip()
    if es_nota:
        # En notas, litros/horas pueden quedar vacíos.
        if not str(out.get("horas_riego", "") or "").strip():
            out["horas_riego"] = ""
        if not str(out.get("litros", "") or "").strip():
            out["litros"] = ""
    else:
        horas = parse_locale_float(out.get("horas_riego", ""))
        litros = parse_locale_float(out.get("litros", ""))
        out["horas_riego"] = "" if horas is None else str(horas)
        out["litros"] = "" if litros is None else str(litros)
        out["nota"] = str(out.get("nota", "") or "").strip()
    return out


def build_riego_timeline_figure(rows: list[dict[str, str]]) -> Any | None:
    """Gráfico timeline: barras de duración para riegos; marcadores para notas."""
    import matplotlib.dates as mdates

    events: list[dict[str, Any]] = []
    for row in rows:
        start = parse_riego_start(
            str(row.get("dia_riego", "") or ""),
            str(row.get("hora_inicio_riego", "") or ""),
        )
        if start is None:
            continue
        es_nota = parse_es_nota(row.get("es_nota", ""))
        horas = parse_locale_float(row.get("horas_riego", "")) or 0.0
        litros = parse_locale_float(row.get("litros", "")) or 0.0
        nota = str(row.get("nota", "") or "").strip()
        if es_nota:
            # Marcador corto en el instante de la nota.
            end = start + timedelta(hours=0.25)
            label = (nota[:28] + "…") if len(nota) > 28 else (nota or "Nota")
        else:
            duration_h = horas if horas > 0 else 0.25
            end = start + timedelta(hours=duration_h)
            label = f"{litros:g} L · {horas:g} h" if litros or horas else "Riego"
        events.append(
            {
                "start": start,
                "end": end,
                "es_nota": es_nota,
                "label": label,
            }
        )
    if not events:
        return None

    events = sorted(events, key=lambda e: e["start"])
    fig, ax = plt.subplots(figsize=(7.2, max(2.2, 0.42 * len(events) + 1.2)))
    yticks: list[int] = []
    ylabels: list[str] = []
    for i, ev in enumerate(events):
        y = len(events) - 1 - i
        yticks.append(y)
        color = "#b45309" if ev["es_nota"] else "#2563eb"
        left = mdates.date2num(ev["start"])
        right = mdates.date2num(ev["end"])
        width = max(right - left, 1.0 / 96.0)  # mínimo ~15 min en eje fecha
        ax.barh(y, width, left=left, height=0.55, color=color, alpha=0.85)
        ylabels.append(ev["label"])

    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels, fontsize=8)
    ax.set_xlabel("Fecha / hora")
    ax.set_title("Riegos y notas de la campaña")
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig
