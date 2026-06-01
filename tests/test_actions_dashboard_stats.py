from datetime import date

import pandas as pd

from services.actions_dashboard_stats import (
    contacts_by_hour,
    current_iso_week_bounds,
    success_rate_by_canal,
    summarize_commercial_week,
)


def test_current_iso_week_friday_mid_june() -> None:
    d = date(2024, 6, 7)
    start, end = current_iso_week_bounds(d)
    assert start == date(2024, 6, 3)
    assert end == date(2024, 6, 9)


def test_summarize_commercial_week_filters_by_contact_date() -> None:
    ws, we = current_iso_week_bounds(date(2024, 6, 7))
    rows = [
        {
            "historial_accion_id": "a1",
            "fecha_contacto": ws.strftime("%d/%m/%Y"),
            "hora_contacto": "10:00",
            "persona_contacto": "Ana",
            "resultado_contacto": "exitoso",
            "canal_contacto": "email",
        },
        {
            "historial_accion_id": "a2",
            "fecha_contacto": we.strftime("%d/%m/%Y"),
            "hora_contacto": "",
            "persona_contacto": "Betty",
            "resultado_contacto": "fallido",
            "canal_contacto": "llamada",
        },
        {
            "historial_accion_id": "a3",
            "fecha_contacto": "02/06/2024",
            "hora_contacto": "",
            "persona_contacto": "Carlos",
            "resultado_contacto": "exitoso",
            "canal_contacto": "email",
        },
    ]
    out = summarize_commercial_week(pd.DataFrame(rows), today=date(2024, 6, 7))
    assert out.total_contacts == 2
    assert out.exitosos == 1
    assert out.fallidos == 1
    personas = set(out.by_person["persona_contacto"].tolist())
    assert personas == {"Ana", "Betty"}


def test_success_rate_by_canal() -> None:
    df = pd.DataFrame(
        [
            {"canal_contacto": "email", "resultado_contacto": "exitoso"},
            {"canal_contacto": "email", "resultado_contacto": "fallido"},
            {"canal_contacto": "llamada", "resultado_contacto": "exitoso"},
        ]
    )
    out = success_rate_by_canal(df)
    email_row = out[out["canal_contacto"] == "email"].iloc[0]
    assert email_row["total"] == 2
    assert email_row["tasa_exito"] == 50.0


def test_contacts_by_hour() -> None:
    df = pd.DataFrame(
        [
            {"hora_contacto": "09:30"},
            {"hora_contacto": "09:15"},
            {"hora_contacto": ""},
        ]
    )
    out = contacts_by_hour(df)
    assert out.iloc[0]["hora"] == "09"
    assert int(out.iloc[0]["total"]) == 2
