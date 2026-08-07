"""Parsing de seriales de sensor y sincronización con Inventario (página Contactos)."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from app.cache import history_service, inventory_service
from app.state import bump_inventory_cache
from services.history_service import sensor_serials_from_sensor_serial_number
from services.inventory_service import InventoryAssetOption, normalize_inventory_serial_for_match
from services.sheet_date_format import normalize_sensor_serial_number



def _parse_ddmmyyyy(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None

def _extract_uc501_bundle(serial_value: str) -> tuple[str, str, str]:
    raw = (serial_value or "").strip()
    if not raw:
        return "", "", ""
    first = raw.split(",")[0].strip()
    if not first.lower().startswith("uc501-"):
        return "", "", ""
    first = normalize_sensor_serial_number(first)
    parts = first.split("-")
    if len(parts) == 4:
        return parts[1].strip(), parts[3].strip(), parts[2].strip()  # uc501_sn, sim_sn, probe_sn
    if len(parts) == 2:
        return parts[1].strip(), "", ""
    return "", "", ""

def _extract_ug67_bundle(serial_value: str) -> tuple[str, str]:
    """Return (ug67_sn, sim_sn) from a ug67-* serial string. Children come from inventory.

    Supports both 3-segment (ug67-{sn}-{sim}) and 2-segment (ug67-{sn}) formats.
    Returns ("", "") for sim_sn when no SIM is present.
    """
    raw = (serial_value or "").strip()
    if not raw:
        return "", ""
    first = raw.split(",")[0].strip()
    if not first.lower().startswith("ug67-"):
        return "", ""
    first = normalize_sensor_serial_number(first)
    parts = first.split("-")
    if len(parts) == 3:
        return parts[1].strip(), parts[2].strip()
    if len(parts) == 2:
        return parts[1].strip(), ""
    return "", ""


def _extract_ws6210_bundle(serial_value: str) -> tuple[str, str]:
    """Return (ws6210sc_sn, sim_sn) from a ws6210sc-* pack string."""
    raw = (serial_value or "").strip()
    if not raw:
        return "", ""
    first = raw.split(",")[0].strip()
    if not first.lower().startswith("ws6210sc-"):
        return "", ""
    first = normalize_sensor_serial_number(first)
    parts = first.split("-")
    if len(parts) == 3:
        return parts[1].strip(), parts[2].strip()
    if len(parts) == 2:
        return parts[1].strip(), ""
    return "", ""


def _extract_prefixed_sn(serial_value: str, prefix: str) -> str:
    raw = (serial_value or "").strip()
    if not raw.lower().startswith(f"{prefix}-"):
        return ""
    parts = normalize_sensor_serial_number(raw.split(",")[0].strip()).split("-", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def _extract_solenoide_sn(serial_value: str) -> str:
    return _extract_prefixed_sn(serial_value, "solenoide")


def _extract_sim_sn(serial_value: str) -> str:
    return _extract_prefixed_sn(serial_value, "sim")


def _extract_em500_sn(serial_value: str) -> str:
    return _extract_prefixed_sn(serial_value, "em500")


def _extract_wh51l_sn(serial_value: str) -> str:
    return _extract_prefixed_sn(serial_value, "wh51l")


def _extract_ws69_sn(serial_value: str) -> str:
    return _extract_prefixed_sn(serial_value, "ws69")

def _find_inventory_option_by_serial(
    options: list[InventoryAssetOption],
    serial: str,
) -> InventoryAssetOption | None:
    """Match inventory rows by serial, ignoring wrapping quotes and case."""
    target = normalize_inventory_serial_for_match(serial)
    if not target:
        return None
    for opt in options:
        if normalize_inventory_serial_for_match(opt.serial_number) == target:
            return opt
    return None

def _serial_in_labels(serial: str, labels: list[str]) -> bool:
    target = normalize_inventory_serial_for_match(serial)
    if not target:
        return serial in labels
    return any(
        normalize_inventory_serial_for_match(label) == target
        for label in labels
        if label
    )

def _normalized_serial_set(options: list[InventoryAssetOption]) -> set[str]:
    return {
        normalize_inventory_serial_for_match(o.serial_number)
        for o in options
        if normalize_inventory_serial_for_match(o.serial_number)
    }

def _resolve_inventory_option(
    inv_svc,
    models: tuple[str, ...],
    serial: str,
    available_options: list[InventoryAssetOption],
    inv_df: pd.DataFrame,
) -> InventoryAssetOption | None:
    opt = _find_inventory_option_by_serial(available_options, serial)
    if opt is not None:
        return opt
    all_opts = inv_svc.asset_options_by_models(models, inv_df=inv_df)
    return _find_inventory_option_by_serial(all_opts, serial)

def _infer_sensor_root_type(serial_value: str) -> str:
    """Infer root asset type from existing sensor_serial_number."""
    first = (serial_value or "").strip().split(",")[0].strip().lower()
    if first.startswith("ug67-"):
        return "ug67"
    if first.startswith("ws6210sc-"):
        return "ws6210sc"
    if first.startswith("wh51l-"):
        return "wh51l"
    if first.startswith("ws69-"):
        return "ws69"
    if first.startswith("em500-"):
        return "em500"
    if first.startswith("solenoide-"):
        return "solenoide"
    if first.startswith("sim-"):
        return "sim"
    return "uc501"


def _collect_all_serials_from_sensor_sn(sensor_serial_number: str) -> list[str]:
    """Extract every individual serial number from a canonical sensor_serial_number string."""
    serials: list[str] = []
    for item in [p.strip() for p in normalize_sensor_serial_number(sensor_serial_number).split(",") if p.strip()]:
        lower = item.lower()
        if lower.startswith("uc501-"):
            parts = item.split("-")
            if len(parts) == 4:
                serials.extend([parts[1], parts[2], parts[3]])
            elif len(parts) == 2:
                serials.append(parts[1])
        elif lower.startswith("ug67-") or lower.startswith("ws6210sc-"):
            parts = item.split("-")
            if len(parts) == 3:
                serials.extend([parts[1], parts[2]])
            elif len(parts) == 2:
                serials.append(parts[1])
        elif lower.startswith("solenoide-"):
            parts = item.split("-", 1)
            if len(parts) == 2:
                serials.append(parts[1])
        elif lower.startswith("sim-"):
            parts = item.split("-", 1)
            if len(parts) == 2:
                serials.append(parts[1])
        elif "-" in item:
            serials.append(item.split("-", 1)[1])
    return [s.strip() for s in serials if s.strip()]

def _serials_from_sensor_history_strings(sensor_serial_numbers: list[str]) -> list[str]:
    seen: set[str] = set()
    serials: list[str] = []
    for sensor_serial_number in sensor_serial_numbers:
        for serial in sensor_serials_from_sensor_serial_number(sensor_serial_number):
            key = serial.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            serials.append(serial)
    return serials

def _reconcile_inventory_locations_for_sensor_serials(
    serials: list[str],
    *,
    default_location_type: str = "por_definir",
) -> None:
    if not serials:
        return
    assignments = history_service().open_sensor_assignment_rows_for_serials(serials)
    inventory_service().reconcile_locations_for_serials(
        serials,
        assignments,
        default_location_type=default_location_type,
    )
    bump_inventory_cache()

def _sync_inventory_from_sensor_history(
    values: dict[str, str],
    *,
    close_target_location: str = "",
    previous_sensor_serial_number: str = "",
) -> None:
    serials = _serials_from_sensor_history_strings(
        [
            str(values.get("sensor_serial_number", "") or ""),
            previous_sensor_serial_number,
        ]
    )
    if not serials:
        return
    estado_cierre = str(values.get("estado_cierre_sensor", "")).strip().lower()
    if estado_cierre == "cerrado":
        target = (close_target_location or "por_definir").strip().lower()
        default_location_type = "oficina" if target == "oficina" else "por_definir"
    else:
        default_location_type = "por_definir"
    _reconcile_inventory_locations_for_sensor_serials(serials, default_location_type=default_location_type)

def _sim_eid_from_inv_df(inv_df: pd.DataFrame, inventory_id: str) -> str:
    if inv_df.empty or not (inventory_id or "").strip():
        return ""
    iid = inventory_id.strip()
    m = inv_df[inv_df["inventory_id"].astype(str).str.strip() == iid]
    if m.empty:
        return ""
    return str(m.iloc[0].get("sim_eid_number", "") or "").strip()
