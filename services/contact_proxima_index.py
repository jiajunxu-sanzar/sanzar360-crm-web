"""Derive per-contact próxima acción from Acciones rows for list filters."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from services.sheet_date_format import normalize_dd_mm_yyyy, parse_sheet_date


def _parse_contact_datetime(fecha: str, hora: str) -> datetime | None:
    parsed = parse_sheet_date(fecha)
    if parsed is None:
        return None
    try:
        base = datetime.combine(parsed, datetime.min.time())
    except ValueError:
        return None
    hora = (hora or "").strip()
    if hora and ":" in hora:
        parts = hora.split(":", 1)
        try:
            return base.replace(hour=int(parts[0]), minute=int(parts[1]))
        except ValueError:
            return base
    return base


def latest_commercial_contact_row(
    acciones_df: pd.DataFrame,
    contact_id: str,
) -> dict[str, str] | None:
    """Most recent Acciones row for a contact (by fecha_contacto + hora_contacto)."""
    cid = str(contact_id or "").strip()
    if not cid or acciones_df.empty or "contact_id" not in acciones_df.columns:
        return None
    best: tuple[datetime, dict[str, str]] | None = None
    for row in acciones_df.fillna("").astype(str).to_dict("records"):
        if str(row.get("contact_id", "") or "").strip() != cid:
            continue
        when = _parse_contact_datetime(
            str(row.get("fecha_contacto", "") or ""),
            str(row.get("hora_contacto", "") or ""),
        ) or datetime.min
        if best is None or when >= best[0]:
            best = (when, row)
    return best[1] if best else None


def sort_commercial_rows_by_contact_date(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Newest contact first."""

    def sort_key(row: dict[str, str]) -> datetime:
        return (
            _parse_contact_datetime(
                str(row.get("fecha_contacto", "") or ""),
                str(row.get("hora_contacto", "") or ""),
            )
            or datetime.min
        )

    return sorted(rows, key=sort_key, reverse=True)


def build_contact_proxima_action_index(acciones_df: pd.DataFrame) -> pd.DataFrame:
    """One row per contact_id: próxima acción from the latest Acciones row only (strict)."""
    cols = [
        "contact_id",
        "persona_proxima_accion",
        "proxima_accion_fecha",
        "proxima_accion_detalle",
        "proxima_accion_canal",
    ]
    if acciones_df.empty or "contact_id" not in acciones_df.columns:
        return pd.DataFrame(columns=cols)

    latest_by_contact: dict[str, tuple[datetime, dict[str, str]]] = {}
    for row in acciones_df.fillna("").astype(str).to_dict("records"):
        cid = str(row.get("contact_id", "") or "").strip()
        if not cid:
            continue
        when = _parse_contact_datetime(
            str(row.get("fecha_contacto", "") or ""),
            str(row.get("hora_contacto", "") or ""),
        ) or datetime.min
        prev = latest_by_contact.get(cid)
        if prev is None or when >= prev[0]:
            latest_by_contact[cid] = (when, row)

    payloads: list[dict[str, str]] = []
    for cid, (_, row) in latest_by_contact.items():
        prox_fecha = normalize_dd_mm_yyyy(str(row.get("proxima_accion_fecha", "") or ""))
        if not prox_fecha:
            continue
        payloads.append(
            {
                "contact_id": cid,
                "persona_proxima_accion": str(row.get("proxima_accion_persona", "") or "").strip(),
                "proxima_accion_fecha": prox_fecha,
                "proxima_accion_detalle": str(row.get("proxima_accion_detalle", "") or "").strip(),
                "proxima_accion_canal": str(row.get("proxima_accion_canal", "") or "").strip(),
            }
        )

    if not payloads:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(payloads)


def enrich_contacts_with_proxima(contacts_df: pd.DataFrame, acciones_df: pd.DataFrame) -> pd.DataFrame:
    """Attach próxima acción columns from Acciones (drops legacy Contactos seguimiento columns)."""
    if contacts_df.empty:
        return contacts_df
    out = contacts_df.copy()
    for legacy in (
        "fecha_ultimo_contacto",
        "persona_ultimo_contacto",
        "proxima_accion_fecha",
        "persona_proxima_accion",
        "proxima_accion_detalle",
        "fecha_veces_sin_respuesta",
        "proxima_accion_canal",
    ):
        if legacy in out.columns:
            out = out.drop(columns=[legacy])
    idx = build_contact_proxima_action_index(acciones_df)
    if idx.empty:
        out["persona_proxima_accion"] = ""
        out["proxima_accion_fecha"] = ""
        out["proxima_accion_detalle"] = ""
        out["proxima_accion_canal"] = ""
        return out
    merged = out.merge(idx, on="contact_id", how="left")
    for col in ("persona_proxima_accion", "proxima_accion_fecha", "proxima_accion_detalle", "proxima_accion_canal"):
        if col in merged.columns:
            merged[col] = merged[col].fillna("").astype(str)
    return merged
