from __future__ import annotations

import folium
import pandas as pd

from services.geo_service import geocode_address, parse_coordinates


def _resolve_row_coordinates(row: dict[str, str]) -> tuple[float, float] | None:
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


def build_contacts_map(df: pd.DataFrame) -> folium.Map:
    center = [40.4168, -3.7038]
    fmap = folium.Map(location=center, zoom_start=6, tiles="OpenStreetMap")
    if df.empty:
        return fmap
    points: list[tuple[float, float]] = []
    for row in df.fillna("").astype(str).to_dict("records"):
        coords = _resolve_row_coordinates(row)
        if not coords:
            continue
        lat, lon = coords
        points.append((lat, lon))
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
            color="#2f855a",
            fill=True,
            fill_opacity=0.75,
            popup=folium.Popup(popup, max_width=320),
            tooltip=marker_token,
        ).add_to(fmap)
    if points:
        fmap.fit_bounds(points)
    return fmap
