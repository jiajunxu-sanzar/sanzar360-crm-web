"""Tests for incidencia association dropdown options."""
from __future__ import annotations

from services.incidencia_association_options import (
    build_campana_history_options,
    build_sensor_history_options,
    is_open_campana_history,
    is_open_sensor_history,
    option_by_id,
)


def _sensor_row(
    historial_sensor_id: str = "h-sensor-1",
    estado_cierre_sensor: str = "abierto",
    sensor_serial_number: str = "uc501-UC001-T10-SIM001",
    fecha_inicio: str = "01/01/2025",
    fecha_fin: str = "",
) -> dict[str, str]:
    return {
        "historial_sensor_id": historial_sensor_id,
        "estado_cierre_sensor": estado_cierre_sensor,
        "sensor_serial_number": sensor_serial_number,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
    }


def _campana_row(
    historial_campana_id: str = "h-camp-1",
    estado_cierre_campana: str = "abierto",
    nombre_campana: str = "Maíz Norte",
    fecha_campana_inicio: str = "01/03/2025",
    fecha_campana_fin: str = "",
    cultivo: str = "maíz",
    parcela: str = "Parcela A",
) -> dict[str, str]:
    return {
        "historial_campana_id": historial_campana_id,
        "estado_cierre_campana": estado_cierre_campana,
        "nombre_campana": nombre_campana,
        "fecha_campana_inicio": fecha_campana_inicio,
        "fecha_campana_fin": fecha_campana_fin,
        "cultivo": cultivo,
        "parcela": parcela,
    }


def test_is_open_sensor_history() -> None:
    assert is_open_sensor_history(_sensor_row(estado_cierre_sensor="abierto")) is True
    assert is_open_sensor_history(_sensor_row(estado_cierre_sensor="")) is True
    assert is_open_sensor_history(_sensor_row(estado_cierre_sensor="cerrado")) is False


def test_is_open_campana_history() -> None:
    assert is_open_campana_history(_campana_row(estado_cierre_campana="abierto")) is True
    assert is_open_campana_history(_campana_row(estado_cierre_campana="")) is True
    assert is_open_campana_history(_campana_row(estado_cierre_campana="cerrado")) is False


def test_build_sensor_history_options_filters_closed() -> None:
    rows = [
        _sensor_row(historial_sensor_id="open-1", estado_cierre_sensor="abierto"),
        _sensor_row(historial_sensor_id="closed-1", estado_cierre_sensor="cerrado"),
    ]
    options = build_sensor_history_options(rows)
    assert len(options) == 1
    assert options[0].id == "open-1"
    assert "h-sensor-1" not in options[0].label
    assert "open-1" not in options[0].label
    assert options[0].sensor_serial_number == "uc501-UC001-T10-SIM001"


def test_build_campana_history_options_filters_closed() -> None:
    rows = [
        _campana_row(historial_campana_id="open-c", estado_cierre_campana="abierto"),
        _campana_row(historial_campana_id="closed-c", estado_cierre_campana="cerrado"),
    ]
    options = build_campana_history_options(rows)
    assert len(options) == 1
    assert options[0].id == "open-c"
    assert "Maíz Norte" in options[0].label
    assert "open-c" not in options[0].label
    assert options[0].nombre_campana == "Maíz Norte"


def test_sensor_label_includes_period_and_formatted_sn() -> None:
    options = build_sensor_history_options([_sensor_row()])
    assert len(options) == 1
    assert "01/01/2025" in options[0].label
    assert "activo" in options[0].label
    assert "uc501" in options[0].label.lower()


def test_campana_label_includes_cultivo_and_parcela_for_disambiguation() -> None:
    options = build_campana_history_options([_campana_row()])
    assert len(options) == 1
    assert "maíz" in options[0].label
    assert "Parcela A" in options[0].label


def test_duplicate_labels_get_suffix() -> None:
    rows = [
        _sensor_row(historial_sensor_id="a", fecha_inicio="01/01/2025"),
        _sensor_row(historial_sensor_id="b", fecha_inicio="01/01/2025"),
    ]
    options = build_sensor_history_options(rows)
    assert len(options) == 2
    labels = [opt.label for opt in options]
    assert labels[0] != labels[1]
    assert "(2)" in labels[1]


def test_option_by_id() -> None:
    options = build_sensor_history_options([_sensor_row(historial_sensor_id="wanted")])
    assert option_by_id(options, "wanted") is not None
    assert option_by_id(options, "wanted").id == "wanted"
    assert option_by_id(options, "missing") is None
    assert option_by_id(options, "") is None
