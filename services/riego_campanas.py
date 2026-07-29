"""Validación y visualización del histórico de riegos asociado a campañas."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import plotly.express as px

from services.locale_numbers import parse_locale_float
from services.sheet_date_format import is_valid_dd_mm_yyyy, normalize_dd_mm_yyyy

_HH_MM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_TRUE_VALUES = frozenset({"true", "1", "sí", "si", "yes", "y", "verdadero", "x"})


def _parse_bool_flag(raw: object) -> bool:
    text = str(raw or "").strip().lower()
    if not text:
        return False
    return text in _TRUE_VALUES


def parse_es_nota(raw: object) -> bool:
    """Normaliza el flag es_nota desde Sheets (true/false/sí/1/…)."""
    return _parse_bool_flag(raw)


def serialize_es_nota(flag: bool) -> str:
    return "true" if flag else "false"


def parse_nota_util(raw: object) -> bool:
    """Normaliza nota_util. Vacío se trata como útil (True) para notas nuevas/legacy."""
    text = str(raw or "").strip().lower()
    if not text:
        return True
    if text in {"false", "0", "no", "n", "falso"}:
        return False
    return text in _TRUE_VALUES


def serialize_nota_util(flag: bool) -> str:
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

    if es_nota:
        if not str(values.get("nota", "") or "").strip():
            return "Si es una nota, el campo nota es obligatorio."
        return None

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
    if es_nota:
        out["nota"] = str(out.get("nota", "") or "").strip()
        out["nota_util"] = serialize_nota_util(parse_nota_util(out.get("nota_util", "true")))
        out["dia_riego"] = ""
        out["hora_inicio_riego"] = ""
        out["horas_riego"] = ""
        out["litros"] = ""
    else:
        dia = normalize_dd_mm_yyyy(out.get("dia_riego", "")) or out.get("dia_riego", "")
        out["dia_riego"] = dia
        out["hora_inicio_riego"] = str(out.get("hora_inicio_riego", "") or "").strip()
        horas = parse_locale_float(out.get("horas_riego", ""))
        litros = parse_locale_float(out.get("litros", ""))
        out["horas_riego"] = "" if horas is None else str(horas)
        out["litros"] = "" if litros is None else str(litros)
        out["nota"] = str(out.get("nota", "") or "").strip()
        out["nota_util"] = "false"
    return out


def split_riego_and_nota_rows(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    riegos: list[dict[str, str]] = []
    notas: list[dict[str, str]] = []
    for row in rows:
        if parse_es_nota(row.get("es_nota", "")):
            notas.append(row)
        else:
            riegos.append(row)
    return riegos, notas


def build_riego_timeline_figure(rows: list[dict[str, str]]) -> Any | None:
    """Timeline Plotly solo con riegos (notas excluidas). Hover: inicio, duración, litros."""
    events: list[dict[str, Any]] = []
    for row in rows:
        if parse_es_nota(row.get("es_nota", "")):
            continue
        start = parse_riego_start(
            str(row.get("dia_riego", "") or ""),
            str(row.get("hora_inicio_riego", "") or ""),
        )
        if start is None:
            continue
        horas = parse_locale_float(row.get("horas_riego", "")) or 0.0
        litros = parse_locale_float(row.get("litros", "")) or 0.0
        duration_h = horas if horas > 0 else 0.25
        end = start + timedelta(hours=duration_h)
        inicio_txt = start.strftime("%d/%m/%Y %H:%M")
        label = f"{inicio_txt} · {litros:g} L"
        events.append(
            {
                "Task": label,
                "Start": start,
                "Finish": end,
                "Inicio": inicio_txt,
                "Duracion_h": horas,
                "Litros": litros,
            }
        )
    if not events:
        return None

    events = sorted(events, key=lambda e: e["Start"])
    df = pd.DataFrame(events)
    fig = px.timeline(
        df,
        x_start="Start",
        x_end="Finish",
        y="Task",
        custom_data=["Inicio", "Duracion_h", "Litros"],
    )
    fig.update_traces(
        marker_color="#2563eb",
        hovertemplate=(
            "Inicio: %{customdata[0]}<br>"
            "Duración: %{customdata[1]:g} h<br>"
            "Litros: %{customdata[2]:g} L"
            "<extra></extra>"
        ),
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        title="Riegos de la campaña",
        xaxis_title="Fecha / hora",
        yaxis_title="",
        height=max(220, 48 * len(events) + 100),
        margin=dict(l=20, r=20, t=48, b=40),
        xaxis=dict(tickformat="%d/%m %H:%M"),
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig
