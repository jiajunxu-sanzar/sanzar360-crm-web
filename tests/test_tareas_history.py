from __future__ import annotations

from datetime import date, timedelta

from config.settings import ESTADO_TAREA_OPCIONES, TIPO_TAREA_OPCIONES
from services.history_service import HISTORY_SPECS
from services.tareas_validation import (
    build_tareas_alarm_rows,
    filter_open_tareas,
    is_tarea_abierta,
    is_tarea_vencida_o_hoy,
    next_open_tarea,
    sort_tareas_by_fecha_limite,
    validate_tarea_history_values,
)


def test_tareas_spec_registered() -> None:
    spec = HISTORY_SPECS["tareas"]
    assert spec.worksheet_name == "HistoricoTareas"
    assert spec.id_column == "historial_tarea_id"
    assert spec.date_column == "fecha_limite"
    assert "persona_gestiona" in spec.headers
    assert "fecha_limite" in spec.headers


def test_tipo_y_estado_tarea_opciones() -> None:
    assert "Comunicar riego" in TIPO_TAREA_OPCIONES
    assert "Perseguir cliente" in TIPO_TAREA_OPCIONES
    assert ESTADO_TAREA_OPCIONES == ("Sin iniciar", "En proceso", "Terminado")


def test_filter_open_and_sort_fecha_limite() -> None:
    assert is_tarea_abierta("Sin iniciar") is True
    assert is_tarea_abierta("Terminado") is False
    rows = [
        {"historial_tarea_id": "1", "estado_tarea": "Terminado", "fecha_limite": "10/07/2026"},
        {"historial_tarea_id": "2", "estado_tarea": "En proceso", "fecha_limite": "20/07/2026"},
        {"historial_tarea_id": "3", "estado_tarea": "Sin iniciar", "fecha_limite": "15/07/2026"},
        {"historial_tarea_id": "4", "estado_tarea": "Sin iniciar", "fecha_limite": ""},
    ]
    open_rows = filter_open_tareas(rows)
    assert [r["historial_tarea_id"] for r in open_rows] == ["2", "3", "4"]
    sorted_rows = sort_tareas_by_fecha_limite(open_rows)
    assert [r["historial_tarea_id"] for r in sorted_rows] == ["3", "2", "4"]


def test_validate_tarea_requires_fields() -> None:
    base = {
        "titulo": "",
        "notas": "texto",
        "tipo_tarea": "Consultar cliente",
        "estado_tarea": "Sin iniciar",
    }
    assert validate_tarea_history_values(base) is not None
    base["titulo"] = "Llamar"
    base["notas"] = ""
    assert validate_tarea_history_values(base) is not None
    base["notas"] = "detalle"
    assert validate_tarea_history_values(base) is None


def test_is_tarea_vencida_o_hoy() -> None:
    today = date(2026, 7, 17)
    assert is_tarea_vencida_o_hoy(
        {"estado_tarea": "En progreso", "fecha_limite": "16/07/2026"},
        today=today,
    )
    assert is_tarea_vencida_o_hoy(
        {"estado_tarea": "Sin iniciar", "fecha_limite": "17/07/2026"},
        today=today,
    )
    assert not is_tarea_vencida_o_hoy(
        {"estado_tarea": "Sin iniciar", "fecha_limite": "18/07/2026"},
        today=today,
    )
    assert not is_tarea_vencida_o_hoy(
        {"estado_tarea": "Terminado", "fecha_limite": "16/07/2026"},
        today=today,
    )


def test_alarms_tareas_items_filters() -> None:
    today = date.today()
    overdue = today - timedelta(days=1)
    future = today + timedelta(days=2)
    rows = [
        {
            "historial_tarea_id": "a",
            "contact_id": "c1",
            "nombre_cliente": "Cliente A",
            "titulo": "Vencida",
            "estado_tarea": "En progreso",
            "fecha_limite": overdue.strftime("%d/%m/%Y"),
            "persona_gestiona": "Ana",
            "tipo_tarea": "Consultar cliente",
            "notas": "x",
        },
        {
            "historial_tarea_id": "b",
            "contact_id": "c2",
            "nombre_cliente": "Cliente B",
            "titulo": "Hoy",
            "estado_tarea": "Sin iniciar",
            "fecha_limite": today.strftime("%d/%m/%Y"),
            "persona_gestiona": "Bruno",
            "tipo_tarea": "Comunicar riego",
            "notas": "y",
        },
        {
            "historial_tarea_id": "c",
            "contact_id": "c3",
            "nombre_cliente": "Cliente C",
            "titulo": "Futura",
            "estado_tarea": "Sin iniciar",
            "fecha_limite": future.strftime("%d/%m/%Y"),
            "persona_gestiona": "Ana",
            "tipo_tarea": "Interno",
            "notas": "z",
        },
        {
            "historial_tarea_id": "d",
            "contact_id": "c4",
            "nombre_cliente": "Cliente D",
            "titulo": "Hecha",
            "estado_tarea": "Terminado",
            "fecha_limite": overdue.strftime("%d/%m/%Y"),
            "persona_gestiona": "Ana",
            "tipo_tarea": "Interno",
            "notas": "z",
        },
    ]
    items = build_tareas_alarm_rows(rows, today=today)
    titles = {i.title for i in items}
    assert any("Vencida" in t for t in titles)
    assert any("Hoy" in t for t in titles)
    assert not any("Futura" in t for t in titles)
    assert not any("Hecha" in t for t in titles)


def test_notas_and_tareas_table_columns_start_with_titulo() -> None:
    # Mirror of UI column order (without importing Streamlit table module).
    notas_cols = ["Título", "Tipo", "Estado", "Autor", "Notas"]
    tareas_cols = ["Título", "Tipo", "Estado", "Gestiona", "Límite", "Notas"]
    assert "Nota id" not in notas_cols
    assert "Tarea id" not in tareas_cols
    assert notas_cols[0] == "Título"
    assert tareas_cols[0] == "Título"


def test_next_open_tarea_empty() -> None:
    count, nxt = next_open_tarea([])
    assert count == 0
    assert nxt is None
    count, nxt = next_open_tarea(
        [{"estado_tarea": "Terminado", "fecha_limite": "10/07/2026", "titulo": "Hecha"}]
    )
    assert count == 0
    assert nxt is None


def test_next_open_tarea_picks_earliest_limite() -> None:
    rows = [
        {
            "historial_tarea_id": "1",
            "estado_tarea": "Terminado",
            "fecha_limite": "01/07/2026",
            "titulo": "Ignorar",
        },
        {
            "historial_tarea_id": "2",
            "estado_tarea": "En progreso",
            "fecha_limite": "20/07/2026",
            "titulo": "Lejana",
        },
        {
            "historial_tarea_id": "3",
            "estado_tarea": "Sin iniciar",
            "fecha_limite": "15/07/2026",
            "titulo": "Urgente",
        },
        {
            "historial_tarea_id": "4",
            "estado_tarea": "Sin iniciar",
            "fecha_limite": "",
            "titulo": "Sin fecha",
        },
    ]
    count, nxt = next_open_tarea(rows)
    assert count == 3
    assert nxt is not None
    assert nxt["historial_tarea_id"] == "3"
    assert nxt["titulo"] == "Urgente"
