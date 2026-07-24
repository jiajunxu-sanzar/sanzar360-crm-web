"""Carga de meteo desde CSV Open-Meteo y solape con el sensor."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.riego_umbrales import (
    aviso_solape_meteo_sensor,
    cargar_meteo_open_meteo_csv,
    ejecutar_analisis_completo,
)


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_cargar_meteo_open_meteo_csv_export_con_metadata(tmp_path: Path) -> None:
    csv = _write(
        tmp_path / "meteo_export.csv",
        "\n".join(
            [
                "latitude,longitude,elevation,utc_offset_seconds,timezone,timezone_abbreviation",
                "-1.4411248,38.947784,327.0,0,GMT,GMT",
                "",
                "time,et0_fao_evapotranspiration (mm),precipitation (mm)",
                "2026-07-01T00:00,0.05,0.00",
                "2026-07-01T01:00,0.06,0.00",
                "2026-07-01T02:00,0.07,0.10",
            ]
        )
        + "\n",
    )
    df = cargar_meteo_open_meteo_csv(csv)
    assert list(df.columns) == ["timestamp", "et0", "precipitacion"]
    assert len(df) == 3
    assert float(df.iloc[2]["precipitacion"]) == pytest.approx(0.10)
    assert pd.Timestamp(df.iloc[0]["timestamp"]) == pd.Timestamp("2026-07-01T00:00")


def test_cargar_meteo_csv_limpio(tmp_path: Path) -> None:
    csv = _write(
        tmp_path / "meteo_clean.csv",
        "timestamp,et0,precipitacion\n2026-07-10T12:00,0.4,0\n2026-07-10T13:00,0.5,1.2\n",
    )
    df = cargar_meteo_open_meteo_csv(csv)
    assert len(df) == 2
    assert float(df.iloc[1]["et0"]) == pytest.approx(0.5)


def test_aviso_solape_meteo_antes_que_sensor() -> None:
    meteo = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-07-22T00:00", "2026-07-23T23:00"]),
            "et0": [0.1, 0.2],
            "precipitacion": [0.0, 0.0],
        }
    )
    aviso = aviso_solape_meteo_sensor(
        pd.Timestamp("2026-07-01"),
        pd.Timestamp("2026-07-24T18:00"),
        meteo,
    )
    assert aviso is not None
    assert "23/07/2026" in aviso
    assert "24/07/2026" in aviso


def test_ejecutar_analisis_con_df_meteo_no_llama_api(tmp_path: Path) -> None:
    sensor = _write(
        tmp_path / "sensor.csv",
        "\n".join(
            [
                # sin cabecera; cols 5=timestamp, 6=valor (como TEROS)
                "a,b,c,d,e,2026-07-20 00:00:00,25.0",
                "a,b,c,d,e,2026-07-20 01:00:00,25.1",
                "a,b,c,d,e,2026-07-20 02:00:00,25.2",
                "a,b,c,d,e,2026-07-21 00:00:00,24.0",
                "a,b,c,d,e,2026-07-21 01:00:00,24.1",
                "a,b,c,d,e,2026-07-22 00:00:00,23.5",
            ]
        )
        + "\n",
    )
    meteo = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-07-20", periods=72, freq="h"),
            "et0": [0.1] * 72,
            "precipitacion": [0.0] * 72,
        }
    )
    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("no debe llamar a Open-Meteo")

    informe = ejecutar_analisis_completo(
        csv_path=sensor,
        p_tabla=0.4,
        lat=37.0,
        lon=-1.0,
        textura="franco",
        fecha_inicio="2026-07-20",
        fecha_fin="2026-07-22",
        con_cabecera=False,
        df_meteo=meteo,
        _obtener_meteo_fn=_boom,
    )
    assert called["n"] == 0
    assert informe.df_meteo is not None
    assert not informe.df_meteo.empty
    assert informe.fuente_meteo == "csv"
    assert informe.sensor_fecha_inicio is not None
    assert informe.sensor_fecha_fin is not None
    assert pd.Timestamp(informe.sensor_fecha_inicio).normalize() == pd.Timestamp("2026-07-20")
    assert pd.Timestamp(informe.meteo_fecha_inicio).normalize() == pd.Timestamp("2026-07-20")
    assert pd.Timestamp(informe.meteo_fecha_fin).date() <= pd.Timestamp("2026-07-22").date()


def test_imprimir_informe_incluye_datos_considerados(tmp_path: Path, capsys) -> None:
    from services.riego_umbrales import imprimir_informe_completo

    sensor = _write(
        tmp_path / "sensor_print.csv",
        "\n".join(
            [
                "a,b,c,d,e,2026-07-20 00:00:00,25.0",
                "a,b,c,d,e,2026-07-21 00:00:00,24.0",
                "a,b,c,d,e,2026-07-22 00:00:00,23.5",
            ]
        )
        + "\n",
    )
    meteo = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-07-20", periods=48, freq="h"),
            "et0": [0.1] * 48,
            "precipitacion": [0.0] * 48,
        }
    )
    informe = ejecutar_analisis_completo(
        csv_path=sensor,
        p_tabla=0.4,
        lat=37.0,
        lon=-1.0,
        textura="franco",
        fecha_inicio="2026-07-20",
        fecha_fin="2026-07-22",
        con_cabecera=False,
        df_meteo=meteo,
        _obtener_meteo_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("api")),
    )
    imprimir_informe_completo(informe)
    out = capsys.readouterr().out
    assert "[DATOS CONSIDERADOS]" in out
    assert "Sensor (humedad)" in out
    assert "Meteo (ET0/lluvia)" in out
    assert "CSV Open-Meteo" in out
    assert "20/07/2026" in out


def test_ejecutar_analisis_meteo_sin_solape_error(tmp_path: Path) -> None:
    sensor = _write(
        tmp_path / "sensor2.csv",
        "\n".join(
            [
                "a,b,c,d,e,2026-07-20 00:00:00,25.0",
                "a,b,c,d,e,2026-07-21 00:00:00,24.0",
            ]
        )
        + "\n",
    )
    meteo = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-01", periods=24, freq="h"),
            "et0": [0.1] * 24,
            "precipitacion": [0.0] * 24,
        }
    )
    with pytest.raises(ValueError, match="solape"):
        ejecutar_analisis_completo(
            csv_path=sensor,
            p_tabla=0.4,
            lat=37.0,
            lon=-1.0,
            textura="franco",
            fecha_inicio="2026-07-20",
            fecha_fin="2026-07-21",
            con_cabecera=False,
            df_meteo=meteo,
            _obtener_meteo_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("api")),
        )


def test_ejecutar_analisis_solape_parcial_aviso(tmp_path: Path) -> None:
    sensor = _write(
        tmp_path / "sensor3.csv",
        "\n".join(
            [
                "a,b,c,d,e,2026-07-22 00:00:00,25.0",
                "a,b,c,d,e,2026-07-23 12:00:00,24.0",
                "a,b,c,d,e,2026-07-24 12:00:00,23.0",
            ]
        )
        + "\n",
    )
    # Meteo solo hasta el 23
    meteo = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-07-22", "2026-07-23 23:00", freq="h"),
            "et0": 0.1,
            "precipitacion": 0.0,
        }
    )
    informe = ejecutar_analisis_completo(
        csv_path=sensor,
        p_tabla=0.4,
        lat=37.0,
        lon=-1.0,
        textura="franco",
        fecha_inicio="2026-07-22",
        fecha_fin="2026-07-24",
        con_cabecera=False,
        df_meteo=meteo,
        _obtener_meteo_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("api")),
    )
    assert informe.avisos
    assert any("23/07/2026" in a for a in informe.avisos)
