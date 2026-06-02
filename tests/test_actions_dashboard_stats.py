from datetime import date

import pandas as pd

from services.actions_dashboard_stats import (
    commercial_team_roster,
    current_iso_week_bounds,
    iso_week_bounds_for_offset,
    merge_person_canal_week_with_roster,
    person_performance_averages,
    person_performance_last_months,
    success_rate_by_canal,
    summarize_commercial_week,
    summarize_person_canal_week,
)


def test_current_iso_week_friday_mid_june() -> None:
    d = date(2024, 6, 7)
    start, end = current_iso_week_bounds(d)
    assert start == date(2024, 6, 3)
    assert end == date(2024, 6, 9)


def test_iso_week_bounds_for_offset_previous_week() -> None:
    d = date(2024, 6, 7)
    start, end = iso_week_bounds_for_offset(-1, d)
    assert start == date(2024, 5, 27)
    assert end == date(2024, 6, 2)


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


def test_summarize_commercial_week_with_offset() -> None:
    ws, we = current_iso_week_bounds(date(2024, 6, 7))
    prev_ws, prev_we = iso_week_bounds_for_offset(-1, date(2024, 6, 7))
    rows = [
        {
            "fecha_contacto": prev_ws.strftime("%d/%m/%Y"),
            "persona_contacto": "Ana",
            "resultado_contacto": "exitoso",
            "canal_contacto": "email",
        },
        {
            "fecha_contacto": ws.strftime("%d/%m/%Y"),
            "persona_contacto": "Betty",
            "resultado_contacto": "fallido",
            "canal_contacto": "llamada",
        },
    ]
    out = summarize_commercial_week(pd.DataFrame(rows), today=date(2024, 6, 7), week_offset=-1)
    assert out.week_start == prev_ws
    assert out.week_end == prev_we
    assert out.total_contacts == 1
    assert out.by_person.iloc[0]["persona_contacto"] == "Ana"


def test_summarize_person_canal_week() -> None:
    ws, we = current_iso_week_bounds(date(2024, 6, 7))
    rows = pd.DataFrame(
        [
            {
                "fecha_contacto": ws.strftime("%d/%m/%Y"),
                "persona_contacto": "Ana",
                "resultado_contacto": "exitoso",
                "canal_contacto": "email",
            },
            {
                "fecha_contacto": ws.strftime("%d/%m/%Y"),
                "persona_contacto": "Ana",
                "resultado_contacto": "fallido",
                "canal_contacto": "llamada",
            },
            {
                "fecha_contacto": ws.strftime("%d/%m/%Y"),
                "persona_contacto": "Ana",
                "resultado_contacto": "exitoso",
                "canal_contacto": "en_persona",
            },
        ]
    )
    people = summarize_person_canal_week(rows, ws, we)
    assert len(people) == 1
    ana = people[0]
    assert ana.total == 3
    assert ana.exitosos == 2
    assert ana.fallidos == 1
    assert ana.by_canal["email"].total == 1
    assert ana.by_canal["llamada"].fallidos == 1
    assert ana.by_canal["en_persona"].exitosos == 1
    assert ana.by_canal["whatsapp"].total == 0


def test_person_performance_last_months_counts_unique_contacts() -> None:
    ws, _ = current_iso_week_bounds(date(2024, 6, 7))
    rows = pd.DataFrame(
        [
            {
                "fecha_contacto": ws.strftime("%d/%m/%Y"),
                "persona_contacto": "Ana",
                "contact_id": "c1",
                "resultado_contacto": "exitoso",
                "canal_contacto": "email",
            },
            {
                "fecha_contacto": ws.strftime("%d/%m/%Y"),
                "persona_contacto": "Ana",
                "contact_id": "c1",
                "resultado_contacto": "fallido",
                "canal_contacto": "llamada",
            },
            {
                "fecha_contacto": ws.strftime("%d/%m/%Y"),
                "persona_contacto": "Ana",
                "contact_id": "c2",
                "resultado_contacto": "exitoso",
                "canal_contacto": "email",
            },
        ]
    )
    snapshots = person_performance_last_months(rows, "Ana", months=3, today=date(2024, 6, 7))
    current = snapshots[0]
    assert current.total_acciones == 3
    assert current.contactos_unicos == 2
    assert current.exitosos == 2
    assert current.fallidos == 1


def test_person_performance_averages() -> None:
    ws, we = current_iso_week_bounds(date(2024, 6, 7))
    from services.actions_dashboard_stats import PersonWeekSnapshot

    snapshots = [
        PersonWeekSnapshot(
            week_start=ws,
            week_end=we,
            total_acciones=4,
            contactos_unicos=2,
            exitosos=3,
            fallidos=1,
            by_canal={},
        ),
        PersonWeekSnapshot(
            week_start=ws,
            week_end=we,
            total_acciones=0,
            contactos_unicos=0,
            exitosos=0,
            fallidos=0,
            by_canal={},
        ),
    ]
    avg = person_performance_averages(snapshots)
    assert avg.weeks_with_activity == 1
    assert avg.avg_acciones_per_week == 4.0
    assert avg.avg_contactos_unicos_per_week == 2.0
    assert avg.avg_success_rate_pct == 75.0


def test_commercial_team_roster_filters_roles() -> None:
    from dataclasses import dataclass

    @dataclass
    class _User:
        nombre: str
        role: str

    users = [
        _User("Ana Admin", "admin"),
        _User("Bob Agro", "agro_team"),
        _User("Carla Sales", "sales"),
        _User("Dan Emp", "employee"),
    ]
    roster = commercial_team_roster(users)  # type: ignore[arg-type]
    assert roster == ["Ana Admin", "Bob Agro", "Carla Sales"]


def test_merge_person_canal_week_with_roster_adds_zeros() -> None:
    from services.actions_dashboard_stats import CanalBreakdown, PersonCanalWeekStats, merge_person_canal_week_with_roster

    stats = [
        PersonCanalWeekStats(
            persona_contacto="Ana Admin",
            total=2,
            exitosos=1,
            fallidos=1,
            by_canal={"email": CanalBreakdown(total=2, exitosos=1, fallidos=1)},
        )
    ]
    merged = merge_person_canal_week_with_roster(stats, ["Ana Admin", "Bob Agro"])
    assert len(merged) == 2
    assert merged[0].persona_contacto == "Ana Admin"
    assert merged[0].total == 2
    assert merged[1].persona_contacto == "Bob Agro"
    assert merged[1].total == 0


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
    assert email_row["fallidos"] == 1
    assert email_row["tasa_exito"] == 50.0


def test_success_rate_by_canal_whatsapp() -> None:
    df = pd.DataFrame(
        [
            {"canal_contacto": "whatsapp", "resultado_contacto": "exitoso"},
            {"canal_contacto": "whatsapp", "resultado_contacto": "fallido"},
        ]
    )
    out = success_rate_by_canal(df)
    wa_row = out[out["canal_contacto"] == "whatsapp"].iloc[0]
    assert wa_row["total"] == 2
    assert wa_row["exitosos"] == 1
    assert wa_row["tasa_exito"] == 50.0
