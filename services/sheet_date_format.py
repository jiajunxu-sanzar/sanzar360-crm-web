from __future__ import annotations

import re
from datetime import datetime, timedelta

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
DD_MM_YYYY_HINT = (
    "Las fechas deben ir en formato DD/MM/AAAA. "
    "Ejemplos válidos: 05/04/2026, 31/12/2025."
)


def is_valid_dd_mm_yyyy(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return True
    if not _DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%d/%m/%Y")
    except ValueError:
        return False
    return True


CONTACT_DATE_COLUMNS = frozenset(
    {
        "fecha_primer_contacto",
        "fecha_ultimo_contacto",
        "proxima_accion_fecha",
        "fecha_veces_sin_respuesta",
        "fecha_estado",
    }
)

CONTACT_DATE_COLUMN_LABELS: dict[str, str] = {
    "fecha_primer_contacto": "Fecha primer contacto",
    "fecha_ultimo_contacto": "Fecha último contacto",
    "proxima_accion_fecha": "Próxima acción (fecha)",
    "fecha_veces_sin_respuesta": "Fecha / veces sin respuesta",
    "fecha_estado": "Fecha cambio de estado",
}


def validate_contact_date_fields(values: dict[str, str]) -> str | None:
    bad_labels = [
        CONTACT_DATE_COLUMN_LABELS.get(column, column)
        for column in CONTACT_DATE_COLUMNS
        if (values.get(column, "") or "").strip()
        and not is_valid_dd_mm_yyyy(values.get(column, ""))
    ]
    if not bad_labels:
        return None
    return f"Revisa el formato de fecha en: {', '.join(bad_labels)}.\n\n{DD_MM_YYYY_HINT}"


def validate_dd_mm_yyyy_fields(labels_and_values: list[tuple[str, str]]) -> str | None:
    bad_labels = [
        label
        for label, value in labels_and_values
        if (value or "").strip() and not is_valid_dd_mm_yyyy(value)
    ]
    if not bad_labels:
        return None
    return f"Revisa el formato de fecha en: {', '.join(bad_labels)}.\n\n{DD_MM_YYYY_HINT}"


_FECHA_PAGOS_ENTRY_RE = re.compile(r"^\d{2}/\d{2}/\d{4}\s*-\s*.+$")
_CUENTA_USUARIO_RE = re.compile(r"^[^,\s]+@[^,\s]+\s*,\s*.+$")
_UC501_ITEM_RE = re.compile(r"^uc501-[^,\s-]+-[^,\s-]+-[^,\s-]+$", re.IGNORECASE)
_UG67_GATEWAY_RE = re.compile(r"^ug67-[^,\s-]+-[^,\s-]+$", re.IGNORECASE)
_UG67_GATEWAY_NO_SIM_RE = re.compile(r"^ug67-[^,\s-]+$", re.IGNORECASE)
_UG67_DEVICE_RE = re.compile(r"^(em500|em300|uc512)-[^,\s-]+$", re.IGNORECASE)
_SOLENOIDE_RE = re.compile(r"^solenoide-[^,\s]+$", re.IGNORECASE)
_SIM_STANDALONE_RE = re.compile(r"^sim-[^,\s]+$", re.IGNORECASE)

SENSOR_SERIAL_NUMBER_FORMAT_HELP = (
    "Formatos permitidos:\n"
    "- UC501: uc501-serial_uc501-serial_teros10-sim. Ejemplo: uc501-UC001-TE001-SIM001\n"
    "- UG67 con SIM: ug67-serial_gateway-sim, em500-serial, ... Ejemplo: ug67-UG001-SIM900, em500-EM50001\n"
    "- UG67 sin SIM: ug67-serial_gateway, em500-serial, ... Ejemplo: ug67-UG001, em500-EM50001\n"
    "- Nodo suelto: em500-EM50001, em300-EM30001 o uc512-UCDEM00341\n"
    "- Electroválvula solenoide: solenoide-SOL001\n"
    "- SIM individual: sim-SERIAL. Ejemplo: sim-SIM001"
)


def parse_fecha_pagos_dates(value: str) -> list[datetime]:
    value = (value or "").strip()
    if not value:
        return []
    dates: list[datetime] = []
    for chunk in [part.strip() for part in value.split(",")]:
        if not chunk:
            continue
        if not _FECHA_PAGOS_ENTRY_RE.match(chunk):
            raise ValueError("Formato inválido en fecha_pagos")
        date_part = chunk.split("-", 1)[0].strip()
        if not is_valid_dd_mm_yyyy(date_part):
            raise ValueError("Fecha inválida en fecha_pagos")
        dates.append(datetime.strptime(date_part, "%d/%m/%Y"))
    return dates


def is_valid_fecha_pagos(value: str) -> bool:
    try:
        parse_fecha_pagos_dates(value)
    except ValueError:
        return False
    return True


def is_valid_cuenta_usuario(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return True
    return bool(_CUENTA_USUARIO_RE.match(value))


def is_valid_sensor_serial_number(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return True
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        return False
    expecting_ug67_devices = False
    ug67_devices_count = 0
    for item in parts:
        if _UC501_ITEM_RE.match(item):
            if expecting_ug67_devices and ug67_devices_count == 0:
                return False
            expecting_ug67_devices = False
            ug67_devices_count = 0
            continue
        if _UG67_GATEWAY_RE.match(item):
            if expecting_ug67_devices and ug67_devices_count == 0:
                return False
            expecting_ug67_devices = True
            ug67_devices_count = 0
            continue
        if _UG67_GATEWAY_NO_SIM_RE.match(item):
            if expecting_ug67_devices and ug67_devices_count == 0:
                return False
            # UG67 without SIM: child devices are optional, not required
            expecting_ug67_devices = False
            ug67_devices_count = 0
            continue
        if _UG67_DEVICE_RE.match(item):
            if not expecting_ug67_devices:
                continue
            ug67_devices_count += 1
            continue
        if _SOLENOIDE_RE.match(item):
            if expecting_ug67_devices and ug67_devices_count == 0:
                return False
            expecting_ug67_devices = False
            ug67_devices_count = 0
            continue
        if _SIM_STANDALONE_RE.match(item):
            if expecting_ug67_devices and ug67_devices_count == 0:
                return False
            expecting_ug67_devices = False
            ug67_devices_count = 0
            continue
        return False
    return not (expecting_ug67_devices and ug67_devices_count == 0)


def sensor_serial_number_summary_lines(value: str) -> list[str]:
    value = (value or "").strip()
    if not value:
        return []
    out: list[str] = []
    current_ug67: str | None = None
    for item in [part.strip() for part in value.split(",") if part.strip()]:
        low = item.lower()
        if low.startswith("uc501-"):
            fields = item.split("-")
            if len(fields) == 4:
                out.append(
                    f"UC501 | UC501 SN: {fields[1]} | Teros10 SN: {fields[2]} | SIM: {fields[3]}"
                )
            else:
                out.append(f"UC501 | {item}")
            current_ug67 = None
        elif low.startswith("ug67-"):
            fields = item.split("-")
            if len(fields) == 3:
                out.append(f"UG67 | Gateway SN: {fields[1]} | SIM: {fields[2]}")
            elif len(fields) == 2:
                out.append(f"UG67 | Gateway SN: {fields[1]} | Sin SIM")
            else:
                out.append(f"UG67 | {item}")
            current_ug67 = item
        elif low.startswith("solenoide-"):
            parts_sol = item.split("-", 1)
            sol_serial = parts_sol[1] if len(parts_sol) == 2 else item
            out.append(f"Solenoide | SN: {sol_serial}")
            current_ug67 = None
        elif low.startswith("sim-"):
            parts_sim = item.split("-", 1)
            sim_serial = parts_sim[1] if len(parts_sim) == 2 else item
            out.append(f"SIM individual | SN: {sim_serial}")
            current_ug67 = None
        elif current_ug67 is not None and "-" in item:
            asset_type, serial = item.split("-", 1)
            out.append(f"  - Nodo {asset_type.upper()}: {serial}")
        else:
            out.append(item)
    return out


def suscripcion_from_fecha_pagos(value: str, now: datetime | None = None) -> str:
    dates = parse_fecha_pagos_dates(value)
    if not dates:
        return "No"
    ref = now or datetime.now()
    return "Sí" if ref <= max(dates) + timedelta(days=365) else "No"
