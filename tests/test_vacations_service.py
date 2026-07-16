from __future__ import annotations

from datetime import date

import pandas as pd

from services.vacations_service import (
    HOLIDAY_HEADERS,
    VacationsService,
    _business_days_between,
    _default_leganes_holidays,
    expand_absence_day_types,
)


def _vacations_service() -> VacationsService:
    return VacationsService(sheets=object())  # type: ignore[arg-type]


def _butarque_row(fecha: str = "2026-08-14") -> dict[str, str]:
    return {
        "fecha": fecha,
        "nombre_festivo": "Virgen de Butarque",
        "ambito": "local",
        "municipio": "Leganes",
        "anio": "2026",
    }


def test_default_butarque_date_is_august_14() -> None:
    holidays = _default_leganes_holidays()
    butarque = next(row for row in holidays if row["nombre_festivo"] == "Virgen de Butarque")
    assert butarque["fecha"] == "2026-08-14"


def test_sync_preserves_edited_butarque_date() -> None:
    svc = _vacations_service()
    rows = []
    for row in _default_leganes_holidays():
        if row["nombre_festivo"] == "Virgen de Butarque":
            rows.append(_butarque_row("2026-08-14"))
        else:
            rows.append(row)
    existing = pd.DataFrame(rows, columns=HOLIDAY_HEADERS)
    result = svc._sync_default_holidays(existing)
    assert result is None


def test_sync_does_not_revert_butarque_to_old_default() -> None:
    svc = _vacations_service()
    existing = pd.DataFrame([_butarque_row("2026-08-14")], columns=HOLIDAY_HEADERS)
    result = svc._sync_default_holidays(existing)
    assert result is not None
    butarque = result[result["nombre_festivo"] == "Virgen de Butarque"]
    assert len(butarque) == 1
    assert str(butarque.iloc[0]["fecha"]) == "2026-08-14"
    assert not (butarque["fecha"].astype(str) == "2026-08-05").any()


def test_sync_adds_missing_default_holidays() -> None:
    svc = _vacations_service()
    existing = pd.DataFrame([_butarque_row("2026-08-14")], columns=HOLIDAY_HEADERS)
    result = svc._sync_default_holidays(existing)
    assert result is not None
    names = set(result["nombre_festivo"].astype(str).tolist())
    assert "Virgen de Butarque" in names
    assert "Navidad" in names
    butarque = result[result["nombre_festivo"] == "Virgen de Butarque"]
    assert len(butarque) == 1
    assert str(butarque.iloc[0]["fecha"]) == "2026-08-14"


def test_sync_returns_none_when_all_defaults_present() -> None:
    svc = _vacations_service()
    existing = pd.DataFrame(_default_leganes_holidays(), columns=HOLIDAY_HEADERS)
    result = svc._sync_default_holidays(existing)
    assert result is None


def test_sync_returns_none_for_empty_holidays() -> None:
    svc = _vacations_service()
    result = svc._sync_default_holidays(pd.DataFrame(columns=HOLIDAY_HEADERS))
    assert result is None


def test_business_days_mon_to_fri_without_holidays() -> None:
    # 2026-08-24 Mon .. 2026-08-28 Fri
    assert _business_days_between("2026-08-24", "2026-08-28", set()) == 5.0


def test_business_days_excludes_weekend() -> None:
    # 2026-08-21 Fri .. 2026-08-28 Fri includes Sat 22 and Sun 23
    assert _business_days_between("2026-08-21", "2026-08-28", set()) == 6.0


def test_business_days_excludes_holiday() -> None:
    holidays = {date(2026, 8, 14)}  # Friday Virgen de Butarque
    # Mon 10 .. Fri 14 → 4 laborables (excludes Friday holiday)
    assert _business_days_between("2026-08-10", "2026-08-14", holidays) == 4.0


def test_business_days_half_day() -> None:
    assert _business_days_between("2026-08-24", "2026-08-24", set(), half_day=True) == 0.5


def test_expand_skips_weekend() -> None:
    absences = [
        {
            "fecha_inicio": "2026-08-21",
            "fecha_fin": "2026-08-28",
            "tipo": "vacaciones",
        }
    ]
    day_types = expand_absence_day_types(absences, 2026, set())
    assert date(2026, 8, 21) in day_types  # Fri
    assert date(2026, 8, 22) not in day_types  # Sat
    assert date(2026, 8, 23) not in day_types  # Sun
    assert date(2026, 8, 24) in day_types  # Mon
    assert day_types[date(2026, 8, 24)] == "ausencia"


def test_expand_skips_holiday() -> None:
    holiday = date(2026, 8, 14)
    absences = [
        {
            "fecha_inicio": "2026-08-10",
            "fecha_fin": "2026-08-14",
            "tipo": "vacaciones",
        }
    ]
    day_types = expand_absence_day_types(absences, 2026, {holiday})
    assert holiday not in day_types
    assert date(2026, 8, 13) in day_types
    assert day_types[date(2026, 8, 13)] == "ausencia"


def test_expand_teletrabajo_on_business_days_only() -> None:
    absences = [
        {
            "fecha_inicio": "2026-08-21",
            "fecha_fin": "2026-08-24",
            "tipo": "teletrabajo",
        }
    ]
    day_types = expand_absence_day_types(absences, 2026, set())
    assert day_types[date(2026, 8, 21)] == "teletrabajo"
    assert date(2026, 8, 22) not in day_types
    assert date(2026, 8, 23) not in day_types
    assert day_types[date(2026, 8, 24)] == "teletrabajo"


def test_expand_vacaciones_wins_over_teletrabajo() -> None:
    absences = [
        {"fecha_inicio": "2026-08-24", "fecha_fin": "2026-08-24", "tipo": "teletrabajo"},
        {"fecha_inicio": "2026-08-24", "fecha_fin": "2026-08-24", "tipo": "vacaciones"},
    ]
    day_types = expand_absence_day_types(absences, 2026, set())
    assert day_types[date(2026, 8, 24)] == "ausencia"


def test_expand_timestamp_dataframe_lookup_by_date() -> None:
    """calendar_df uses pd.Timestamp; HTML looks up with datetime.date — keys must match."""
    df = pd.DataFrame(
        [
            {
                "fecha_inicio": pd.Timestamp("2026-08-24"),
                "fecha_fin": pd.Timestamp("2026-08-28"),
                "tipo": "vacaciones",
            }
        ]
    )
    day_types = expand_absence_day_types(df, 2026, set())
    assert day_types.get(date(2026, 8, 24)) == "ausencia"
    assert day_types.get(date(2026, 8, 28)) == "ausencia"
    assert all(type(k) is date for k in day_types)

