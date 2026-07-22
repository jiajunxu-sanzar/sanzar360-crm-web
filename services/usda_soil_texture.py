"""Clasificador del triángulo textural USDA-NRCS.

Dado el % de arcilla (clay), % de limo (silt) y % de arena (sand), determina
en qué clase textural USDA cae. Las claves de salida (`clase_crm`) coinciden
con ``TABLA_TEXTURAS`` del CRM (guiones, p.ej. ``franco-arenoso``).
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

from services.tecnico_campana_prefill import textura_visible_name

Point = Tuple[float, float]

# Vertices de los 12 polígonos: cada vértice es (clay%, sand%, silt%) que suma 100.
TEXTURE_POLYGONS_TERNARY: Dict[str, List[Tuple[float, float, float]]] = {
    "clay": [
        (100.0, 0.0, 0.0),
        (55.0, 45.0, 0.0),
        (40.0, 45.0, 15.0),
        (40.0, 20.0, 40.0),
        (60.0, 0.0, 40.0),
    ],
    "silty clay": [
        (60.0, 0.0, 40.0),
        (40.0, 20.0, 40.0),
        (40.0, 0.0, 60.0),
    ],
    "sandy clay": [
        (55.0, 45.0, 0.0),
        (35.0, 65.0, 0.0),
        (35.0, 45.0, 20.0),
    ],
    "clay loam": [
        (40.0, 20.0, 40.0),
        (40.0, 45.0, 15.0),
        (27.0, 45.0, 28.0),
        (27.0, 20.0, 53.0),
    ],
    "silty clay loam": [
        (40.0, 0.0, 60.0),
        (40.0, 20.0, 40.0),
        (27.0, 20.0, 53.0),
        (27.0, 0.0, 73.0),
    ],
    "sandy clay loam": [
        (35.0, 45.0, 20.0),
        (35.0, 65.0, 0.0),
        (20.0, 80.0, 0.0),
        (20.0, 52.0, 28.0),
        (27.0, 45.0, 28.0),
    ],
    "loam": [
        (27.0, 23.0, 50.0),
        (27.0, 45.0, 28.0),
        (20.0, 52.0, 28.0),
        (7.0, 52.0, 41.0),
        (7.0, 43.0, 50.0),
    ],
    "silt loam": [
        (27.0, 0.0, 73.0),
        (27.0, 23.0, 50.0),
        (0.0, 50.0, 50.0),
        (0.0, 20.0, 80.0),
        (12.0, 8.0, 80.0),
        (12.0, 0.0, 88.0),
    ],
    "silt": [
        (12.0, 0.0, 88.0),
        (12.0, 8.0, 80.0),
        (0.0, 20.0, 80.0),
        (0.0, 0.0, 100.0),
    ],
    "sandy loam": [
        (20.0, 52.0, 28.0),
        (20.0, 80.0, 0.0),
        (15.0, 85.0, 0.0),
        (0.0, 70.0, 30.0),
        (0.0, 50.0, 50.0),
        (7.0, 43.0, 50.0),
        (7.0, 52.0, 41.0),
    ],
    "loamy sand": [
        (15.0, 85.0, 0.0),
        (10.0, 90.0, 0.0),
        (0.0, 85.0, 15.0),
        (0.0, 70.0, 30.0),
    ],
    "sand": [
        (10.0, 90.0, 0.0),
        (0.0, 100.0, 0.0),
        (0.0, 85.0, 15.0),
    ],
}

# Claves CRM (coinciden con TABLA_TEXTURAS).
CRM_KEYS: Dict[str, str] = {
    "clay": "arcilla",
    "silty clay": "arcillo-limoso",
    "sandy clay": "arcillo-arenoso",
    "clay loam": "franco-arcilloso",
    "silty clay loam": "franco-arcillo-limoso",
    "sandy clay loam": "franco-arcillo-arenoso",
    "loam": "franco",
    "silt loam": "franco-limoso",
    "silt": "limo",
    "sandy loam": "franco-arenoso",
    "loamy sand": "arenoso-franco",
    "sand": "arena",
}

SQRT3_2 = math.sqrt(3.0) / 2.0


def ternary_to_xy(clay: float, sand: float, silt: float) -> Point:
    """Conversión barycéntrica: arriba=arcilla, abajo-izq=arena, abajo-der=limo."""
    total = clay + sand + silt
    if total <= 0:
        raise ValueError("clay + sand + silt debe ser > 0")
    c, s, l = clay / total, sand / total, silt / total
    x = c * 0.5 + s * 0.0 + l * 1.0
    y = c * SQRT3_2 + s * 0.0 + l * 0.0
    return (x, y)


def _point_on_segment(p: Point, a: Point, b: Point, tol: float) -> bool:
    (px, py), (ax, ay), (bx, by) = p, a, b
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    seg_len_sq = abx * abx + aby * aby
    if seg_len_sq < tol * tol:
        return math.hypot(apx, apy) <= tol
    cross = abx * apy - aby * apx
    dist = abs(cross) / math.sqrt(seg_len_sq)
    if dist > tol:
        return False
    dot = (apx * abx + apy * aby) / seg_len_sq
    return -tol <= dot <= 1 + tol


def point_in_polygon(point: Point, polygon: List[Point], tol: float = 1e-7) -> bool:
    x, y = point
    n = len(polygon)
    inside = False
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        if _point_on_segment(point, a, b, tol):
            return True
        ax, ay = a
        bx, by = b
        if (ay > y) != (by > y):
            x_intersect = ax + (y - ay) * (bx - ax) / (by - ay)
            if x < x_intersect:
                inside = not inside
    return inside


def classify_soil_texture(
    clay: float,
    silt: float,
    sand: float,
    *,
    normalize: bool = True,
) -> dict[str, object]:
    """Clasifica una muestra según el triángulo textural USDA.

    Returns
    -------
    dict con:
        clase_en, clase_crm, clase_es, clay, silt, sand, candidatos
    """
    if clay < 0 or silt < 0 or sand < 0:
        raise ValueError("Los porcentajes no pueden ser negativos")

    total = clay + silt + sand
    if total <= 0:
        raise ValueError("clay + silt + sand debe ser > 0")

    if abs(total - 100.0) > 1e-9:
        if not normalize:
            raise ValueError(f"clay+silt+sand = {total}, debería ser 100")
        clay, silt, sand = (v * 100.0 / total for v in (clay, silt, sand))

    xy = ternary_to_xy(clay, sand, silt)

    candidatos: List[str] = []
    for name, poly_ternary in TEXTURE_POLYGONS_TERNARY.items():
        poly_xy = [ternary_to_xy(c, s, l) for c, s, l in poly_ternary]
        if point_in_polygon(xy, poly_xy):
            candidatos.append(name)

    if not candidatos:
        raise ValueError(
            f"No se encontró clase textural para clay={clay:.2f}, "
            f"silt={silt:.2f}, sand={sand:.2f} (¿punto fuera del triángulo?)"
        )

    clase_en = candidatos[0]
    clase_crm = CRM_KEYS[clase_en]
    return {
        "clase_en": clase_en,
        "clase_crm": clase_crm,
        "clase_es": textura_visible_name(clase_crm),
        "clay": round(clay, 3),
        "silt": round(silt, 3),
        "sand": round(sand, 3),
        "candidatos": candidatos,
    }


def clase_crm_from_percentages(clay: float, silt: float, sand: float) -> str:
    """Atajo: solo la clave CRM de la textura clasificada."""
    return str(classify_soil_texture(clay, silt, sand)["clase_crm"])
