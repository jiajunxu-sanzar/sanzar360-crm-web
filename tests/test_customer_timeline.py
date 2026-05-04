from datetime import date

from services.customer_timeline import build_customer_timeline, timeline_events_grouped_months


def test_merge_chronological_start() -> None:
    rows_s = [
        {"historial_sensor_id": "1", "fecha_inicio": "01/02/2024", "sensor_serial_number": "X", "fecha_fin": "02/02/2024"}
    ]
    rows_c = [
        {"historial_campana_id": "c1", "nombre_campana": "ABC", "fecha_campana_inicio": "15/03/2024", "cultivo": "maíz"}
    ]
    rows_u = [
        {
            "historial_suscripcion_id": "u1",
            "fecha_pago": "01/06/2024",
            "cantidad_pago": "120",
            "moneda": "EUR",
            "metodo_pago": "transferencia",
            "estado_suscripcion": "activa",
            "suscripcion_fecha_fin": "02/06/2024",
        }
    ]
    rows_i = [
        {
            "historial_incidencia_id": "i1",
            "fecha_apertura": "10/05/2024",
            "fecha_cierre": "12/05/2024",
            "tipo_incidencia": "sensor",
            "prioridad": "alta",
            "estado": "cerrada",
            "detalle": "algo",
            "resolucion": "ok",
        }
    ]
    events = build_customer_timeline(
        sensores_rows=rows_s,
        campanas_rows=rows_c,
        suscripciones_rows=rows_u,
        incidencias_rows=rows_i,
    )
    assert len(events) > 6
    first = sorted(events, key=lambda e: (e.on_date, e.tie_break))[0]
    assert first.on_date == date(2024, 2, 1)


def test_grouped_reverse_month_newest_first() -> None:
    rows_s = [
        {"historial_sensor_id": "1", "fecha_inicio": "01/01/2023", "sensor_serial_number": "a"},
        {"historial_sensor_id": "2", "fecha_inicio": "01/06/2024", "sensor_serial_number": "b"},
    ]
    events = build_customer_timeline(
        sensores_rows=rows_s,
        campanas_rows=[],
        suscripciones_rows=[],
        incidencias_rows=[],
    )
    grouped = timeline_events_grouped_months(events, reverse_chrono=True)
    assert grouped[0][0].startswith("Junio")


def test_month_title_capitalize() -> None:
    rows_s = [{"historial_sensor_id": "1", "fecha_inicio": "05/07/2023", "sensor_serial_number": "X"}]
    events = build_customer_timeline(
        sensores_rows=rows_s,
        campanas_rows=[],
        suscripciones_rows=[],
        incidencias_rows=[],
    )
    grouped = timeline_events_grouped_months(events, reverse_chrono=False)
    assert grouped[0][0] == "Julio 2023"


def test_duplicate_sensor_end_skipped_when_same_as_start() -> None:
    rows_s = [
        {"historial_sensor_id": "1", "fecha_inicio": "01/01/2025", "fecha_fin": "01/01/2025", "sensor_serial_number": "AB"}
    ]
    events = build_customer_timeline(
        sensores_rows=rows_s,
        campanas_rows=[],
        suscripciones_rows=[],
        incidencias_rows=[],
    )
    assert len(events) == 1
