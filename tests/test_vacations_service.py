from __future__ import annotations

import pandas as pd

from services.vacations_service import (
    HOLIDAY_HEADERS,
    VacationsService,
    _default_leganes_holidays,
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
