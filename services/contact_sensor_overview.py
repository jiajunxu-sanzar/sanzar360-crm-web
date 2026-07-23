"""Read-only per-contact overview: open sensors, incidents, last contact, próxima acción."""
from __future__ import annotations

import pandas as pd

from services.contact_proxima_index import (
    enrich_contacts_with_proxima,
    latest_commercial_contact_row,
)
from services.history_service import count_sensor_packs, parse_sensor_assets
from services.sheet_date_format import normalize_dd_mm_yyyy

OVERVIEW_COLUMNS = [
    "contact_id",
    "nombre",
    "num_sensores",
    "sensor_sns",
    "ultimo_contacto",
    "ultimo_contacto_canal",
    "ultimo_contacto_detalle",
    "proxima_accion_fecha",
    "proxima_accion_detalle",
    "persona_proxima_accion",
    "incidencias_abiertas",
    "incidencias_detalle",
    "semaforo",
]

_CLOSED_INCIDENT_ESTADOS = frozenset({"cerrada", "cerrado", "resuelta", "resuelto"})
_SENSOR_SEMAFORO_ACTIVE = frozenset({"verde", "amarillo"})


def _is_sensor_history_open(row: dict[str, str]) -> bool:
    estado = str(row.get("estado_cierre_sensor", "") or "").strip().lower()
    return estado != "cerrado"


def is_incidencia_abierta(row: dict[str, str]) -> bool:
    if str(row.get("fecha_cierre", "") or "").strip():
        return False
    estado = str(row.get("estado", "") or "").strip().lower()
    return estado not in _CLOSED_INCIDENT_ESTADOS


def _is_incidencia_abierta(row: dict[str, str]) -> bool:
    return is_incidencia_abierta(row)


def format_sensor_pack_associations(sensor_serial_number: str) -> str:
    """Format one sensor history SSN with uc501/ug67 pack associations."""
    raw = str(sensor_serial_number or "").strip()
    assets = parse_sensor_assets(raw)
    if not assets:
        return raw

    grouped: dict[str, list[str]] = {}
    group_order: list[str] = []
    for asset, assoc in assets:
        token = f"{asset.asset_type}-{asset.serial}"
        group_key = (assoc or token).strip()
        if group_key not in grouped:
            grouped[group_key] = []
            group_order.append(group_key)
        existing_lower = {t.lower() for t in grouped[group_key]}
        if token.lower() not in existing_lower:
            grouped[group_key].append(token)

    pack_lines: list[str] = []
    for group_key in group_order:
        tokens = grouped[group_key]
        if len(tokens) == 1:
            pack_lines.append(tokens[0])
            continue
        root = ""
        for prefix in ("uc501-", "ug67-"):
            root = next((t for t in tokens if t.lower().startswith(prefix)), "")
            if root:
                break
        if not root:
            root = tokens[0]
        children = [t for t in tokens if t != root]
        if children:
            pack_lines.append(f"{root} → {' · '.join(children)}")
        else:
            pack_lines.append(root)
    return "; ".join(pack_lines)


def format_ultimo_contacto_detail(latest: dict[str, str] | None) -> str:
    if not latest:
        return ""
    lines: list[str] = []
    fecha = normalize_dd_mm_yyyy(str(latest.get("fecha_contacto", "") or ""))
    hora = str(latest.get("hora_contacto", "") or "").strip()
    canal = str(latest.get("canal_contacto", "") or "").strip()
    when_parts = [p for p in [fecha, hora] if p]
    when = " ".join(when_parts)
    if canal:
        when = f"{when} · {canal}" if when else canal
    if when:
        lines.append(when)
    persona = str(latest.get("persona_contacto", "") or "").strip()
    resultado = str(latest.get("resultado_contacto", "") or "").strip()
    if persona or resultado:
        lines.append(" · ".join(p for p in [persona, resultado] if p))
    notas = str(latest.get("notas_contacto", "") or "").strip()
    if notas:
        lines.append(notas)
    return "\n".join(lines)


def format_incidencias_detail(open_rows: list[dict[str, str]]) -> str:
    if not open_rows:
        return ""
    blocks: list[str] = []
    for row in open_rows:
        tipo = str(row.get("tipo_incidencia", "") or "").strip()
        estado = str(row.get("estado", "") or "").strip()
        prioridad = str(row.get("prioridad", "") or "").strip()
        detalle = str(row.get("detalle", "") or "").strip()
        resolucion = str(row.get("resolucion", "") or "").strip()
        head = " · ".join(p for p in [tipo, estado, prioridad] if p)
        parts = [head] if head else []
        if detalle:
            parts.append(detalle)
        if resolucion:
            parts.append(f"Resolución: {resolucion}")
        if parts:
            blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def _aggregate_open_sensors(sensor_rows: list[dict]) -> dict[str, tuple[int, str]]:
    rows_by_contact: dict[str, list[dict]] = {}
    for row in sensor_rows:
        if not _is_sensor_history_open(row):
            continue
        cid = str(row.get("contact_id", "") or "").strip()
        if not cid:
            continue
        rows_by_contact.setdefault(cid, []).append(row)

    out: dict[str, tuple[int, str]] = {}
    for cid, rows in rows_by_contact.items():
        packs: list[str] = []
        total = 0
        seen_ssn: set[str] = set()
        for row in rows:
            ssn = str(row.get("sensor_serial_number", "") or "").strip()
            if not ssn:
                continue
            key = ssn.lower()
            if key in seen_ssn:
                continue
            seen_ssn.add(key)
            total += count_sensor_packs(ssn)
            pack = format_sensor_pack_associations(ssn)
            if pack:
                packs.append(pack)
        out[cid] = (total, "\n".join(packs))
    return out


def _open_incidencias_by_contact(incidencia_rows: list[dict]) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for row in incidencia_rows:
        if not _is_incidencia_abierta(row):
            continue
        cid = str(row.get("contact_id", "") or "").strip()
        if not cid:
            continue
        out.setdefault(cid, []).append(row)
    return out


def _semaforo(num_sensores: int, incidencias_abiertas: int) -> str:
    if num_sensores == 0:
        return "sin_sensores"
    if incidencias_abiertas > 0:
        return "amarillo"
    return "verde"


def build_contact_sensor_overview(
    contacts_df: pd.DataFrame,
    sensor_rows: list[dict],
    incidencia_rows: list[dict],
    acciones_df: pd.DataFrame,
) -> pd.DataFrame:
    """One row per contact with sensor/incident status and commercial follow-up."""
    if contacts_df.empty:
        return pd.DataFrame(columns=OVERVIEW_COLUMNS)

    enriched = enrich_contacts_with_proxima(contacts_df, acciones_df)
    sensor_by_contact = _aggregate_open_sensors(sensor_rows)
    incidencias_by_contact = _open_incidencias_by_contact(incidencia_rows)

    rows: list[dict[str, object]] = []
    for _, contact in enriched.iterrows():
        cid = str(contact.get("contact_id", "") or "").strip()
        num_sensores, sensor_display = sensor_by_contact.get(cid, (0, ""))
        open_incidencias = incidencias_by_contact.get(cid, [])
        incidencias_abiertas = len(open_incidencias)
        incidencias_detalle = format_incidencias_detail(open_incidencias)

        latest = latest_commercial_contact_row(acciones_df, cid)
        ultimo_contacto = ""
        ultimo_contacto_canal = ""
        ultimo_contacto_detalle = ""
        if latest:
            ultimo_contacto = normalize_dd_mm_yyyy(
                str(latest.get("fecha_contacto", "") or "")
            )
            ultimo_contacto_canal = str(latest.get("canal_contacto", "") or "").strip()
            ultimo_contacto_detalle = format_ultimo_contacto_detail(latest)

        rows.append(
            {
                "contact_id": cid,
                "nombre": str(contact.get("nombre", "") or "").strip(),
                "num_sensores": num_sensores,
                "sensor_sns": sensor_display,
                "ultimo_contacto": ultimo_contacto,
                "ultimo_contacto_canal": ultimo_contacto_canal,
                "ultimo_contacto_detalle": ultimo_contacto_detalle,
                "proxima_accion_fecha": str(contact.get("proxima_accion_fecha", "") or "").strip(),
                "proxima_accion_detalle": str(contact.get("proxima_accion_detalle", "") or "").strip(),
                "persona_proxima_accion": str(contact.get("persona_proxima_accion", "") or "").strip(),
                "incidencias_abiertas": incidencias_abiertas,
                "incidencias_detalle": incidencias_detalle,
                "semaforo": _semaforo(num_sensores, incidencias_abiertas),
            }
        )

    return pd.DataFrame(rows, columns=OVERVIEW_COLUMNS)


def semaforo_by_contact_id(overview: pd.DataFrame) -> dict[str, str]:
    """Map contact_id -> semaforo (missing ids omitted)."""
    if overview.empty or "contact_id" not in overview.columns or "semaforo" not in overview.columns:
        return {}
    out: dict[str, str] = {}
    for row in overview.fillna("").astype(str).to_dict("records"):
        cid = str(row.get("contact_id", "") or "").strip()
        if not cid:
            continue
        out[cid] = str(row.get("semaforo", "") or "").strip() or "sin_sensores"
    return out


def filter_by_sensor_overview(
    df: pd.DataFrame,
    overview: pd.DataFrame,
    *,
    only_with_sensors: bool,
) -> pd.DataFrame:
    """If only_with_sensors, keep rows whose semaforo is verde or amarillo."""
    if not only_with_sensors:
        return df
    if df.empty or "contact_id" not in df.columns:
        return df
    if overview.empty:
        return df.iloc[0:0].copy()
    active_ids = {
        cid
        for cid, sem in semaforo_by_contact_id(overview).items()
        if sem in _SENSOR_SEMAFORO_ACTIVE
    }
    if not active_ids:
        return df.iloc[0:0].copy()
    col = df["contact_id"].fillna("").astype(str).str.strip()
    return df[col.isin(active_ids)]


def semaforo_display_prefix(semaforo: str, *, is_lost: bool) -> str:
    """Return row prefix for semaforo; perdido uses 🔴 in contacts.py instead."""
    if is_lost:
        return ""
    sem = (semaforo or "").strip().lower()
    if sem == "verde":
        return "🟢 "
    if sem == "amarillo":
        return "🟡 "
    return ""
