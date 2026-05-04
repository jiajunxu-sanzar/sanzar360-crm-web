from datetime import date

import pandas as pd

from services.actions_dashboard_stats import (
    SIN_PERSONA_LABEL,
    current_iso_week_bounds,
    personas_with_counted_actions,
    summarize_actions_current_week,
    weekly_breakdown_for_person,
)


def test_current_iso_week_friday_mid_june() -> None:
    d = date(2024, 6, 7)  # viernes
    start, end = current_iso_week_bounds(d)
    assert start == date(2024, 6, 3)
    assert end == date(2024, 6, 9)


def test_summarize_keeps_only_counted_types_in_window_and_drops_zeros() -> None:
    ws, we = current_iso_week_bounds(date(2024, 6, 7))
    rows = [
        {
            "fecha_accion": f"{ws.strftime('%d/%m/%Y')} 10:00",
            "tipo_accion": "batch email",
            "persona": "Ana",
            "contact_id": "",
            "nombre_contacto": "",
            "detalle": "",
        },
        {
            "fecha_accion": f"{we.strftime('%d/%m/%Y')} 12:00",
            "tipo_accion": "seguimiento comercial",
            "persona": "Ana",
            "contact_id": "",
            "nombre_contacto": "",
            "detalle": "",
        },
        {
            "fecha_accion": f"{ws.strftime('%d/%m/%Y')} 09:00",
            "tipo_accion": "seguimiento comercial",
            "persona": "Betty",
            "contact_id": "",
            "nombre_contacto": "",
            "detalle": "",
        },
        {
            # fuera de ventana (semana anterior)
            "fecha_accion": "02/06/2024 09:00",
            "tipo_accion": "batch email",
            "persona": "Carlos",
            "contact_id": "",
            "nombre_contacto": "",
            "detalle": "",
        },
        {
            # tipo irrelevante
            "fecha_accion": f"{ws.strftime('%d/%m/%Y')} 09:00",
            "tipo_accion": "modificacion contacto",
            "persona": "Dave",
            "contact_id": "",
            "nombre_contacto": "",
            "detalle": "",
        },
    ]
    df = pd.DataFrame(rows)
    out = summarize_actions_current_week(df, today=date(2024, 6, 7))
    assert out.week_start == ws
    assert out.week_end == we
    personas = set(out.by_person["persona"].tolist())
    assert personas == {"Ana", "Betty"}
    assert out.by_person.loc[out.by_person["persona"] == "Ana", "total"].iloc[0] == 2
    assert out.by_person.loc[out.by_person["persona"] == "Betty", "total"].iloc[0] == 1
    assert not bool((out.by_person["persona"] == "Carlos").any())
    assert not bool((out.by_person["persona"] == "Dave").any())


def test_personas_include_sin_persona() -> None:
    df = pd.DataFrame(
        [
            {
                "fecha_accion": "05/06/2024 10:00",
                "tipo_accion": "batch email",
                "persona": "   ",
                "contact_id": "",
                "nombre_contacto": "",
                "detalle": "",
            }
        ]
    )
    personas = personas_with_counted_actions(df)
    assert SIN_PERSONA_LABEL in personas


def test_weekly_breakdown_desc_by_week_same_person_two_weeks() -> None:
    rows = [
        {
            "fecha_accion": "03/06/2024 10:00",
            "tipo_accion": "batch email",
            "persona": "Ana",
            "contact_id": "",
            "nombre_contacto": "",
            "detalle": "",
        },
        {
            "fecha_accion": "10/06/2024 11:00",
            "tipo_accion": "seguimiento comercial",
            "persona": "Ana",
            "contact_id": "",
            "nombre_contacto": "",
            "detalle": "",
        },
    ]
    bd = weekly_breakdown_for_person(pd.DataFrame(rows), persona_display="Ana")
    assert len(bd) == 2
    assert list(bd["semana_desde"]) == [date(2024, 6, 10), date(2024, 6, 3)]
    assert bd.iloc[0]["total"] == 1


def test_empty_person_placeholder() -> None:
    ws, _we = current_iso_week_bounds(date(2024, 6, 7))
    df = pd.DataFrame(
        [
            {
                "fecha_accion": f"{ws.strftime('%d/%m/%Y')} 10:00",
                "tipo_accion": "Batch Email",
                "persona": "  ",
                "contact_id": "",
                "nombre_contacto": "",
                "detalle": "",
            }
        ]
    )
    out = summarize_actions_current_week(df, today=date(2024, 6, 7))
    assert out.by_person.iloc[0]["persona"] == SIN_PERSONA_LABEL
    assert int(out.by_person.iloc[0]["total"]) == 1
