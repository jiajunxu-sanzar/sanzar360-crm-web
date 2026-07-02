import pandas as pd

from ui.components.contact_overview_table import (
    build_overview_table_html,
    build_overview_row_html,
    filter_overview_by_contact_ids,
    filter_overview_with_sensors_only,
    format_incidencias_cell,
    format_sensors_cell,
    overview_row_inline_style,
    semaforo_row_modifier,
    sort_overview_by_proxima_accion,
)
from ui.palette import STATUS_NEUTRAL, STATUS_SUCCESS, STATUS_WARNING


def _overview_row(
    contact_id: str,
    nombre: str = "Test",
    proxima_accion_fecha: str = "",
    semaforo: str = "sin_sensores",
) -> dict[str, object]:
    return {
        "contact_id": contact_id,
        "nombre": nombre,
        "num_sensores": 0,
        "sensor_sns": "",
        "ultimo_contacto": "",
        "ultimo_contacto_canal": "",
        "proxima_accion_fecha": proxima_accion_fecha,
        "proxima_accion_detalle": "",
        "persona_proxima_accion": "",
        "incidencias_abiertas": 0,
        "semaforo": semaforo,
    }


def test_sort_overview_proxima_asc_empty_last() -> None:
    rows = [
        _overview_row("c3", proxima_accion_fecha=""),
        _overview_row("c1", proxima_accion_fecha="10/06/2025"),
        _overview_row("c2", proxima_accion_fecha="01/06/2025"),
    ]
    df = pd.DataFrame(rows)
    sorted_df = sort_overview_by_proxima_accion(df)
    ids = sorted_df["contact_id"].tolist()
    assert ids == ["c2", "c1", "c3"]


def test_semaforo_row_modifier() -> None:
    assert semaforo_row_modifier("verde") == "sanzar-overview-row--verde"
    assert semaforo_row_modifier("amarillo") == "sanzar-overview-row--amarillo"
    assert semaforo_row_modifier("sin_sensores") == "sanzar-overview-row--neutral"
    assert semaforo_row_modifier("") == "sanzar-overview-row--neutral"


def test_overview_row_inline_style_uses_palette() -> None:
    assert f"background:{STATUS_SUCCESS.bg}" in overview_row_inline_style("verde")
    assert f"background:{STATUS_WARNING.bg}" in overview_row_inline_style("amarillo")
    assert f"background:{STATUS_NEUTRAL.bg}" in overview_row_inline_style("sin_sensores")


def test_format_sensors_cell() -> None:
    assert format_sensors_cell(3, "uc501-UC001 → teros10-TE001 · sim-SIM001") == (
        "uc501-UC001 → teros10-TE001 · sim-SIM001"
    )
    assert format_sensors_cell(0, "") == "—"


def test_format_incidencias_cell() -> None:
    assert format_incidencias_cell(2) == "2 abiertas"
    assert format_incidencias_cell(0) == "—"


def test_filter_overview_by_contact_ids() -> None:
    df = pd.DataFrame(
        [
            _overview_row("c1", nombre="Uno"),
            _overview_row("c2", nombre="Dos"),
            _overview_row("c3", nombre="Tres"),
        ]
    )
    scoped = filter_overview_by_contact_ids(df, ["c2", "c1"])
    assert set(scoped["contact_id"].tolist()) == {"c1", "c2"}


def test_build_overview_row_html_escapes() -> None:
    row = _overview_row("c1", nombre="<script>")
    html = build_overview_row_html(row)
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_filter_overview_with_sensors_only() -> None:
    df = pd.DataFrame(
        [
            _overview_row("c1", semaforo="verde"),
            _overview_row("c2", semaforo="amarillo"),
            _overview_row("c3", semaforo="sin_sensores"),
        ]
    )
    scoped = filter_overview_with_sensors_only(df)
    assert set(scoped["contact_id"].tolist()) == {"c1", "c2"}


def test_build_overview_table_html_expanded() -> None:
    row = _overview_row(
        "c1",
        nombre="Cliente largo",
        proxima_accion_fecha="01/06/2025",
        semaforo="verde",
    )
    row["num_sensores"] = 3
    row["sensor_sns"] = "sim-8988228066632864352, sim-8988228066632864356"
    df = pd.DataFrame([row])
    table_html = build_overview_table_html(df, expanded=True)
    assert "sanzar-overview-table--expanded" in table_html
    assert "sim-8988228066632864352" in table_html
    assert "Contacto</span>" in table_html
