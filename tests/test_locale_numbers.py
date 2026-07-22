from __future__ import annotations

import pytest

from services.locale_numbers import parse_locale_float, parse_p_tabla
from services.tecnico_campana_prefill import build_tecnico_prefill


def test_parse_locale_float_dot_and_comma() -> None:
    assert parse_locale_float("0.45") == pytest.approx(0.45)
    assert parse_locale_float("0,45") == pytest.approx(0.45)
    assert parse_locale_float("-3,4414") == pytest.approx(-3.4414)
    assert parse_locale_float(0) == 0.0
    assert parse_locale_float("") is None


def test_parse_p_tabla_heals_sheets_locale_mangle() -> None:
    assert parse_p_tabla("0,3") == pytest.approx(0.3)
    assert parse_p_tabla("0.45") == pytest.approx(0.45)
    assert parse_p_tabla(3) == pytest.approx(0.3)
    assert parse_p_tabla(45) == pytest.approx(0.45)
    assert parse_p_tabla(3.0) == pytest.approx(0.3)
    assert parse_p_tabla(1.5) is None


def test_prefill_heals_mangled_p_tabla_from_cultivo() -> None:
    campana = {
        "cultivo": "cebolla - seca",
        "latitud": "39,0497",
        "longitud": "-3.4414",
        "textura_suelo": "franco",
        "fecha_campana_inicio": "05/05/2026",
        "fecha_campana_fin": "22/09/2026",
    }
    cultivos = [{"nombre": "cebolla - seca", "p_tabla": 3}]  # 0.3 mangled by Sheets
    result = build_tecnico_prefill(campana, {}, cultivos)
    assert "p_tabla" not in " ".join(result.missing)
    assert result.values["p_tabla"] == pytest.approx(0.3)
    assert result.values["lat"] == pytest.approx(39.0497)
    assert result.values["lon"] == pytest.approx(-3.4414)
