from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from services.history_service import HISTORY_SPECS
from services.riego_umbrales import validar_cultivo
from services.tecnico_campana_prefill import (
    build_tecnico_prefill,
    contacts_with_open_campaigns,
    csv_date_range,
    open_campaigns_for_contact,
    textura_key_from_value,
)


def test_textura_key_from_value_accepts_key_and_visible() -> None:
    assert textura_key_from_value("franco") == "franco"
    assert textura_key_from_value("Franco") == "franco"
    assert textura_key_from_value("Franco-Arenoso") == "franco-arenoso"
    assert textura_key_from_value("desconocido") is None


def test_campanas_spec_uses_textura_suelo() -> None:
    headers = HISTORY_SPECS["campanas"].headers
    assert "textura_suelo" in headers
    assert "tipo_suelo" not in headers
    assert "latitud" in headers
    assert "longitud" in headers
    assert "coordenadas_parcela" in headers
    for removed in (
        "p_tabla",
        "k_1",
        "k_3",
        "k_5",
        "parcela",
        "porcentaje_fase_1",
        "porcentaje_fase_2",
        "porcentaje_fase_3",
        "porcentaje_fase_4",
    ):
        assert removed not in headers


def test_contacts_with_open_campaigns_filters() -> None:
    contacts = pd.DataFrame(
        [
            {"contact_id": "c1", "nombre": "Ana"},
            {"contact_id": "c2", "nombre": "Bruno"},
            {"contact_id": "c3", "nombre": "Carla"},
        ]
    )
    campanas = [
        {"contact_id": "c1", "estado_cierre_campana": "abierto", "historial_campana_id": "h1"},
        {"contact_id": "c2", "estado_cierre_campana": "cerrado", "historial_campana_id": "h2"},
        {"contact_id": "c3", "estado_cierre_campana": "", "historial_campana_id": "h3"},
    ]
    opts = contacts_with_open_campaigns(contacts, campanas)
    assert [o.contact_id for o in opts] == ["c1", "c3"]


def test_open_campaigns_for_contact() -> None:
    rows = [
        {
            "contact_id": "c1",
            "historial_campana_id": "a",
            "estado_cierre_campana": "abierto",
            "fecha_campana_inicio": "01/01/2024",
        },
        {
            "contact_id": "c1",
            "historial_campana_id": "b",
            "estado_cierre_campana": "cerrado",
            "fecha_campana_inicio": "01/06/2024",
        },
        {
            "contact_id": "c2",
            "historial_campana_id": "c",
            "estado_cierre_campana": "abierto",
            "fecha_campana_inicio": "01/03/2024",
        },
    ]
    open_rows = open_campaigns_for_contact(rows, "c1")
    assert len(open_rows) == 1
    assert open_rows[0]["historial_campana_id"] == "a"


def test_build_tecnico_prefill_complete() -> None:
    campana = {
        "cultivo": "viña - uva",
        "latitud": "40.1",
        "longitud": "-3.7",
        "textura_suelo": "franco",
        "fecha_campana_inicio": "01/03/2024",
        "fecha_campana_fin": "15/09/2024",
    }
    cultivos = [
        {
            "nombre": "viña - uva",
            "L1": 30.0,
            "L2": 90.0,
            "L3": 130.0,
            "L4": 210.0,
            "kc_ini": 0.3,
            "kc_med": 0.7,
            "kc_fin": 0.45,
            "p_tabla": 0.4,
        }
    ]
    result = build_tecnico_prefill(campana, {}, cultivos)
    assert result.missing == ()
    assert result.values["cultivo_nombre"] == "viña - uva"
    assert result.values["p_tabla"] == 0.4
    assert result.values["lat"] == pytest.approx(40.1)
    assert result.values["lon"] == pytest.approx(-3.7)
    assert result.values["textura"] == "franco"
    assert result.values["fecha_siembra"] == date(2024, 3, 1)
    assert result.values["fecha_cosecha"] == date(2024, 9, 15)


def test_build_tecnico_prefill_partial_missing_and_fallbacks() -> None:
    campana = {
        "cultivo": "no existe",
        "latitud": "",
        "longitud": "",
        "coordenadas_parcela": "",
        "textura_suelo": "",
        "fecha_campana_inicio": "",
        "fecha_campana_fin": "",
    }
    contact = {"coordenadas": "41.0, -2.5"}
    cultivos = [{"nombre": "viña - uva", "p_tabla": 0.35}]
    result = build_tecnico_prefill(campana, contact, cultivos)
    assert "lat" in result.values
    assert result.values["lat"] == pytest.approx(41.0)
    assert any("Cultivo" in m for m in result.missing)
    assert any("p_tabla" in m for m in result.missing)
    assert any("Textura" in m for m in result.missing)
    assert any("siembra" in m for m in result.missing)
    assert any("cosecha" in m for m in result.missing)


def test_build_tecnico_prefill_p_tabla_from_cultivo() -> None:
    campana = {
        "cultivo": "viña - uva",
        "textura_suelo": "arena",
        "latitud": "1",
        "longitud": "2",
    }
    cultivos = [{"nombre": "viña - uva", "p_tabla": 0.55}]
    result = build_tecnico_prefill(campana, {}, cultivos)
    assert result.values["p_tabla"] == 0.55


def test_build_tecnico_prefill_coords_accept_comma_decimal() -> None:
    campana = {
        "cultivo": "cebolla - seca",
        "latitud": "-3,4414",
        "longitud": "39,0497",
        "textura_suelo": "franco",
        "fecha_campana_inicio": "05/05/2026",
        "fecha_campana_fin": "22/09/2026",
    }
    cultivos = [
        {
            "nombre": "cebolla - seca",
            "L1": 10.0,
            "L2": 20.0,
            "L3": 30.0,
            "L4": 40.0,
            "kc_ini": 0.3,
            "kc_med": 0.7,
            "kc_fin": 0.45,
            "p_tabla": 0.45,
        }
    ]
    result = build_tecnico_prefill(campana, {}, cultivos)
    assert result.missing == ()
    assert result.values["cultivo_nombre"] == "cebolla - seca"
    assert result.values["p_tabla"] == 0.45
    assert result.values["lat"] == pytest.approx(-3.4414)
    assert result.values["lon"] == pytest.approx(39.0497)


def test_cultivos_from_df_includes_named_crop_with_p_tabla() -> None:
    from pages.tecnico import _cultivos_from_df

    df = pd.DataFrame(
        [
            {
                "cultivo_kc_id": "id1",
                "nombre": "cebolla - seca",
                "L1": "20",
                "L2": "40",
                "L3": "60",
                "L4": "90",
                "kc_ini": "0.4",
                "kc_med": "0.9",
                "kc_fin": "0.7",
                "p_tabla": "0.45",
            },
            {
                "cultivo_kc_id": "id2",
                "nombre": "",
                "L1": "1",
                "L2": "2",
                "L3": "3",
                "L4": "4",
                "kc_ini": "0.1",
                "kc_med": "0.2",
                "kc_fin": "0.3",
                "p_tabla": "0.3",
            },
        ]
    )
    crops = _cultivos_from_df(df)
    assert len(crops) == 1
    assert crops[0]["nombre"] == "cebolla - seca"
    assert crops[0]["p_tabla"] == 0.45

    campana = {
        "cultivo": "cebolla - seca",
        "latitud": "40.1",
        "longitud": "-3.7",
        "textura_suelo": "franco",
        "fecha_campana_inicio": "01/03/2024",
        "fecha_campana_fin": "15/09/2024",
    }
    result = build_tecnico_prefill(campana, {}, crops)
    assert result.missing == ()
    assert result.values["cultivo_nombre"] == "cebolla - seca"
    assert result.values["p_tabla"] == 0.45


def test_build_tecnico_prefill_coords_from_legacy_coordenadas_parcela() -> None:
    campana = {
        "cultivo": "viña - uva",
        "textura_suelo": "arena",
        "coordenadas_parcela": "39.5, -0.4",
    }
    cultivos = [{"nombre": "viña - uva", "p_tabla": 0.4}]
    result = build_tecnico_prefill(campana, {}, cultivos)
    assert result.values["lat"] == pytest.approx(39.5)
    assert result.values["lon"] == pytest.approx(-0.4)


def test_validar_cultivo_rejects_bad_p_tabla() -> None:
    with pytest.raises(ValueError, match="p_tabla"):
        validar_cultivo(
            {
                "nombre": "x",
                "L1": 1,
                "L2": 2,
                "L3": 3,
                "L4": 4,
                "kc_ini": 0.1,
                "kc_med": 0.2,
                "kc_fin": 0.3,
                "p_tabla": "1.5",
            }
        )


def test_csv_date_range_from_temp_file(tmp_path) -> None:
    # cargar_serie uses columns 5 (timestamp) and 6 (value) by default
    path = tmp_path / "sensor.csv"
    lines = []
    for i, ts in enumerate(["2024-01-10 00:00:00", "2024-01-12 12:00:00", "2024-01-11 06:00:00"]):
        cols = [""] * 7
        cols[5] = ts
        cols[6] = str(20 + i)
        lines.append(",".join(cols))
    path.write_text("\n".join(lines), encoding="utf-8")
    start, end = csv_date_range(str(path), con_cabecera=False)
    assert start == date(2024, 1, 10)
    assert end == date(2024, 1, 12)


def test_history_normalize_maps_tipo_suelo_legacy() -> None:
    from services.history_service import HistoryService

    class _Sheets:
        pass

    svc = HistoryService(_Sheets())  # type: ignore[arg-type]
    df = pd.DataFrame(
        [
            {
                "historial_campana_id": "h1",
                "contact_id": "c1",
                "tipo_suelo": "franco",
                "textura_suelo": "",
                "coordenadas_parcela": "40.0, -3.0",
                "latitud": "",
                "longitud": "",
            }
        ]
    )
    spec = HISTORY_SPECS["campanas"]
    for h in spec.headers:
        if h not in df.columns:
            df[h] = ""
    df["tipo_suelo"] = "franco"
    df["textura_suelo"] = ""
    df["coordenadas_parcela"] = "40.0, -3.0"
    df["latitud"] = ""
    df["longitud"] = ""
    out = svc._normalize_dataframe(df, spec)
    assert out.iloc[0]["textura_suelo"] == "franco"
    assert out.iloc[0]["latitud"] == "40.0"
    assert out.iloc[0]["longitud"] == "-3.0"
    assert "tipo_suelo" not in out.columns
