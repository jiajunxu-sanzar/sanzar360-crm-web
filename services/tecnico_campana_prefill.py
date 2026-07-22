from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from services.geo_service import parse_coordinates
from services.incidencia_association_options import is_open_campana_history
from services.locale_numbers import parse_locale_float, parse_p_tabla
from services.riego_umbrales import TABLA_TEXTURAS, cargar_serie
from services.sheet_date_format import parse_sheet_date


def textura_visible_name(clave: str) -> str:
    return "-".join(parte.capitalize() for parte in str(clave).split("-"))


def textura_key_from_value(value: object) -> str | None:
    """Acepta clave interna o nombre visible; None si no es textura FAO válida."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in TABLA_TEXTURAS:
        return raw
    lowered = raw.casefold()
    for key in TABLA_TEXTURAS:
        if key.casefold() == lowered or textura_visible_name(key).casefold() == lowered:
            return key
    return None


@dataclass(frozen=True)
class ContactCampaignOption:
    contact_id: str
    nombre: str


@dataclass(frozen=True)
class PrefillResult:
    values: dict[str, Any] = field(default_factory=dict)
    missing: tuple[str, ...] = ()


def contacts_with_open_campaigns(
    contacts_df: pd.DataFrame,
    campanas_rows: list[dict[str, str]],
) -> list[ContactCampaignOption]:
    open_ids = {
        str(row.get("contact_id", "") or "").strip()
        for row in campanas_rows
        if is_open_campana_history(row) and str(row.get("contact_id", "") or "").strip()
    }
    if not open_ids or contacts_df is None or contacts_df.empty:
        return []
    out: list[ContactCampaignOption] = []
    for _, row in contacts_df.iterrows():
        cid = str(row.get("contact_id", "") or "").strip()
        if cid not in open_ids:
            continue
        nombre = str(row.get("nombre", "") or "").strip() or cid
        out.append(ContactCampaignOption(contact_id=cid, nombre=nombre))
    out.sort(key=lambda c: c.nombre.casefold())
    return out


def open_campaigns_for_contact(
    campanas_rows: list[dict[str, str]],
    contact_id: str,
) -> list[dict[str, str]]:
    target = str(contact_id or "").strip()
    if not target:
        return []
    rows = [
        row
        for row in campanas_rows
        if is_open_campana_history(row) and str(row.get("contact_id", "") or "").strip() == target
    ]
    rows.sort(
        key=lambda r: str(r.get("fecha_campana_inicio", "") or ""),
        reverse=True,
    )
    return rows


def _match_cultivo_kc(
    cultivo_name: str,
    cultivos_kc: list[dict[str, Any]],
) -> dict[str, Any] | None:
    target = str(cultivo_name or "").strip().casefold()
    if not target:
        return None
    for crop in cultivos_kc:
        if str(crop.get("nombre", "") or "").strip().casefold() == target:
            return crop
    return None


def _parse_coord_number(raw: object) -> float | None:
    """Parse lat/lon; accepts comma decimals (Sheets es_ES) and numeric 0."""
    return parse_locale_float(raw)


def build_tecnico_prefill(
    campana: dict[str, str] | None,
    contact: dict[str, str] | None,
    cultivos_kc: list[dict[str, Any]],
) -> PrefillResult:
    values: dict[str, Any] = {}
    missing: list[str] = []
    campana = campana or {}
    contact = contact or {}

    cultivo_name = str(campana.get("cultivo", "") or "").strip()
    matched = _match_cultivo_kc(cultivo_name, cultivos_kc) if cultivo_name else None
    if matched:
        values["cultivo_nombre"] = str(matched["nombre"])
    else:
        missing.append("Cultivo Kc (no encontrado en CultivosKc o vacío en campaña)")

    p_crop = parse_p_tabla(matched.get("p_tabla")) if matched is not None else None
    if p_crop is not None:
        values["p_tabla"] = p_crop
    else:
        missing.append("p_tabla (CultivosKc)")

    lat = _parse_coord_number(campana.get("latitud"))
    lon = _parse_coord_number(campana.get("longitud"))
    coords: tuple[float, float] | None = (lat, lon) if lat is not None and lon is not None else None
    if coords is None:
        coords = parse_coordinates(str(campana.get("coordenadas_parcela", "") or ""))
    if coords is None:
        coords = parse_coordinates(str(contact.get("coordenadas", "") or ""))
    if coords is not None:
        values["lat"] = float(coords[0])
        values["lon"] = float(coords[1])
    else:
        missing.append("Latitud / longitud (coordenadas)")

    textura_raw = str(campana.get("textura_suelo", "") or campana.get("tipo_suelo", "") or "").strip()
    textura_key = textura_key_from_value(textura_raw)
    if textura_key:
        values["textura"] = textura_key
    else:
        missing.append("Textura del suelo")

    fecha_siembra = parse_sheet_date(str(campana.get("fecha_campana_inicio", "") or ""))
    fecha_cosecha = parse_sheet_date(str(campana.get("fecha_campana_fin", "") or ""))
    if fecha_siembra is not None:
        values["fecha_siembra"] = fecha_siembra
    else:
        missing.append("Fecha de siembra (fecha_campana_inicio)")
    if fecha_cosecha is not None:
        values["fecha_cosecha"] = fecha_cosecha
    else:
        missing.append("Fecha de cosecha (fecha_campana_fin)")

    return PrefillResult(values=values, missing=tuple(missing))


def csv_date_range(
    csv_path: str,
    *,
    con_cabecera: bool = False,
    col_timestamp: int = 5,
    col_valor: int = 6,
) -> tuple[date | None, date | None]:
    df = cargar_serie(csv_path, col_timestamp=col_timestamp, col_valor=col_valor, con_cabecera=con_cabecera)
    if df.empty or "timestamp" not in df.columns:
        return None, None
    ts = pd.to_datetime(df["timestamp"], errors="coerce").dropna()
    if ts.empty:
        return None, None
    return ts.min().date(), ts.max().date()


def csv_upload_date_range(upload, *, con_cabecera: bool = False) -> tuple[date | None, date | None]:
    tmp = tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False)
    try:
        tmp.write(upload.getbuffer())
        tmp.flush()
        tmp.close()
        return csv_date_range(tmp.name, con_cabecera=con_cabecera)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
