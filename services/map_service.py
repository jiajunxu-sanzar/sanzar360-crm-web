from __future__ import annotations

import folium
import pandas as pd

from services.geo_service import geocode_address, parse_coordinates


def resolve_row_coordinates(row: dict[str, str]) -> tuple[float, float] | None:
    # Prioridad solicitada: coordenadas -> municipio -> provincia.
    coords = parse_coordinates(row.get("coordenadas", ""))
    if coords:
        return coords

    municipio = (row.get("municipio", "") or "").strip()
    if municipio:
        try:
            geo = geocode_address(f"{municipio}, España")
            if geo:
                return geo
        except Exception:
            pass

    provincia = (row.get("provincia", "") or "").strip()
    if provincia:
        try:
            geo = geocode_address(f"{provincia}, España")
            if geo:
                return geo
        except Exception:
            pass

    return None


def build_contacts_map(
    df: pd.DataFrame,
    *,
    focus_coords: tuple[float, float] | None = None,
    focus_zoom: int = 13,
) -> folium.Map:
    center = list(focus_coords) if focus_coords else [40.4168, -3.7038]
    zoom = focus_zoom if focus_coords else 6
    fmap = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap")
    if df.empty:
        return fmap
    points: list[tuple[float, float]] = []
    for row in df.fillna("").astype(str).to_dict("records"):
        coords = resolve_row_coordinates(row)
        if not coords:
            continue
        lat, lon = coords
        points.append((lat, lon))
        is_lost = str(row.get("estado", "")).strip().lower() == "perdido"
        marker_color = "#dc2626" if is_lost else "#2f855a"
        popup = (
            f"<b>{row.get('nombre', '')}</b><br>"
            f"{row.get('municipio', '')} {row.get('provincia', '')}<br>"
            f"Estado: {row.get('estado', '')}<br>"
            f"contact_id: {row.get('contact_id', '')}"
        )
        marker_token = f"cid::{row.get('contact_id', '')}::{row.get('nombre', '')}"
        folium.CircleMarker(
            location=[lat, lon],
            radius=7,
            color=marker_color,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.75,
            popup=folium.Popup(popup, max_width=320),
            tooltip=marker_token,
        ).add_to(fmap)
    if points and not focus_coords:
        fmap.fit_bounds(points)
    return fmap
