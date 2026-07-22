"""Dropdown options for linking incidencias to open sensor/campaign histories."""
from __future__ import annotations

from dataclasses import dataclass

from services.contact_sensor_overview import format_sensor_pack_associations


@dataclass(frozen=True)
class AssociationOption:
    id: str
    label: str
    sensor_serial_number: str = ""
    nombre_campana: str = ""


def is_open_sensor_history(row: dict[str, str]) -> bool:
    estado = str(row.get("estado_cierre_sensor", "") or "").strip().lower()
    return estado != "cerrado"


def is_open_campana_history(row: dict[str, str]) -> bool:
    estado = str(row.get("estado_cierre_campana", "") or "").strip().lower()
    return estado != "cerrado"


def _date_range_label(start: str, end: str, *, active_label: str) -> str:
    start = str(start or "").strip()
    end = str(end or "").strip()
    if start and end:
        return f"{start} — {end}"
    if start:
        return f"{start} — {active_label}"
    if end:
        return f"hasta {end}"
    return active_label


def _unique_labels(options: list[AssociationOption]) -> list[AssociationOption]:
    if not options:
        return []
    seen: dict[str, int] = {}
    unique: list[AssociationOption] = []
    for opt in options:
        label = opt.label
        count = seen.get(label, 0)
        if count:
            label = f"{label} ({count + 1})"
        seen[opt.label] = count + 1
        unique.append(
            AssociationOption(
                id=opt.id,
                label=label,
                sensor_serial_number=opt.sensor_serial_number,
                nombre_campana=opt.nombre_campana,
            )
        )
    return unique


def _sensor_history_label(row: dict[str, str]) -> str:
    ssn = str(row.get("sensor_serial_number", "") or "").strip()
    formatted = format_sensor_pack_associations(ssn) if ssn else "Sensor sin SN"
    period = _date_range_label(
        str(row.get("fecha_inicio", "") or ""),
        str(row.get("fecha_fin", "") or ""),
        active_label="activo",
    )
    return f"{formatted} · {period}"


def _campana_history_label(row: dict[str, str]) -> str:
    nombre = str(row.get("nombre_campana", "") or "").strip() or "Campaña sin nombre"
    period = _date_range_label(
        str(row.get("fecha_campana_inicio", "") or ""),
        str(row.get("fecha_campana_fin", "") or ""),
        active_label="activa",
    )
    extra_bits: list[str] = []
    cultivo = str(row.get("cultivo", "") or "").strip()
    if cultivo:
        extra_bits.append(cultivo)
    suffix = f" · {' · '.join(extra_bits)}" if extra_bits else ""
    return f"{nombre} · {period}{suffix}"


def build_sensor_history_options(sensor_rows: list[dict[str, str]]) -> list[AssociationOption]:
    options: list[AssociationOption] = []
    for row in sensor_rows:
        if not is_open_sensor_history(row):
            continue
        hist_id = str(row.get("historial_sensor_id", "") or "").strip()
        if not hist_id:
            continue
        ssn = str(row.get("sensor_serial_number", "") or "").strip()
        options.append(
            AssociationOption(
                id=hist_id,
                label=_sensor_history_label(row),
                sensor_serial_number=ssn,
            )
        )
    return _unique_labels(options)


def build_campana_history_options(campana_rows: list[dict[str, str]]) -> list[AssociationOption]:
    options: list[AssociationOption] = []
    for row in campana_rows:
        if not is_open_campana_history(row):
            continue
        hist_id = str(row.get("historial_campana_id", "") or "").strip()
        if not hist_id:
            continue
        nombre = str(row.get("nombre_campana", "") or "").strip()
        options.append(
            AssociationOption(
                id=hist_id,
                label=_campana_history_label(row),
                nombre_campana=nombre,
            )
        )
    return _unique_labels(options)


def option_by_id(options: list[AssociationOption], hist_id: str) -> AssociationOption | None:
    wanted = str(hist_id or "").strip()
    if not wanted:
        return None
    for opt in options:
        if opt.id == wanted:
            return opt
    return None
