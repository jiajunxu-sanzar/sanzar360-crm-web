"""Tests del clasificador del triángulo textural USDA."""
from __future__ import annotations

import pytest

from services.riego_umbrales import TABLA_TEXTURAS
from services.usda_soil_texture import (
    CRM_KEYS,
    clase_crm_from_percentages,
    classify_soil_texture,
)


def test_classify_known_silt_loam() -> None:
    result = classify_soil_texture(clay=20, silt=60, sand=20)
    assert result["clase_crm"] == "franco-limoso"
    assert result["clase_en"] == "silt loam"
    assert result["clase_es"] == "Franco-Limoso"
    assert result["clay"] == 20.0
    assert result["silt"] == 60.0
    assert result["sand"] == 20.0


def test_classify_normalizes_when_sum_not_100() -> None:
    result = classify_soil_texture(clay=10, silt=30, sand=10, normalize=True)
    assert abs(float(result["clay"]) + float(result["silt"]) + float(result["sand"]) - 100.0) < 1e-6
    assert result["clase_crm"] == "franco-limoso"


def test_classify_rejects_without_normalize_when_sum_not_100() -> None:
    with pytest.raises(ValueError, match="debería ser 100"):
        classify_soil_texture(clay=10, silt=30, sand=10, normalize=False)


def test_classify_rejects_negatives_and_zero_total() -> None:
    with pytest.raises(ValueError, match="negativos"):
        classify_soil_texture(clay=-1, silt=50, sand=51)
    with pytest.raises(ValueError, match="> 0"):
        classify_soil_texture(clay=0, silt=0, sand=0)


def test_all_crm_keys_are_in_tabla_texturas() -> None:
    assert set(CRM_KEYS.values()) == set(TABLA_TEXTURAS.keys())
    for clase_en, clase_crm in CRM_KEYS.items():
        assert clase_crm in TABLA_TEXTURAS
        # Un punto interior aproximado por el centroide ternario del polígono
        # no hace falta aquí: basta que el mapeo cubra toda la tabla.


def test_clase_crm_from_percentages_shortcut() -> None:
    assert clase_crm_from_percentages(20, 60, 20) == "franco-limoso"


@pytest.mark.parametrize(
    "clay,silt,sand,expected_crm",
    [
        (90, 5, 5, "arcilla"),
        (50, 45, 5, "arcillo-limoso"),
        (45, 5, 50, "arcillo-arenoso"),
        (35, 30, 35, "franco-arcilloso"),
        (35, 55, 10, "franco-arcillo-limoso"),
        (30, 10, 60, "franco-arcillo-arenoso"),
        (20, 40, 40, "franco"),
        (5, 90, 5, "limo"),
        (10, 20, 70, "franco-arenoso"),
        (5, 10, 85, "arenoso-franco"),
        (2, 3, 95, "arena"),
    ],
)
def test_classify_representative_points(clay: float, silt: float, sand: float, expected_crm: str) -> None:
    result = classify_soil_texture(clay, silt, sand)
    assert result["clase_crm"] == expected_crm
    assert result["clase_crm"] in TABLA_TEXTURAS
