from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from services.sheets_service import SheetsService

EMPLOYEES_WS = "Vacaciones_Empleados"
ABSENCES_WS = "Vacaciones_Ausencias"
HOLIDAYS_WS = "Vacaciones_Festivos"

EMPLOYEE_HEADERS = [
    "employee_id",
    "nombre",
    "dias_vacaciones_anuales",
    "dias_teletrabajo_anuales",
    "anio",
    "activo",
]

ABSENCE_HEADERS = [
    "leave_id",
    "employee_id",
    "nombre_employee",
    "tipo",
    "fecha_inicio",
    "fecha_fin",
    "medio_dia",
    "estado",
    "comentario",
    "created_at",
    "updated_at",
]

HOLIDAY_HEADERS = [
    "fecha",
    "nombre_festivo",
    "ambito",
    "municipio",
    "anio",
]


@dataclass(frozen=True)
class VacationSummaryRow:
    employee_id: str
    nombre: str
    dias_vacaciones_anuales: float
    dias_vacaciones_cogidos: float
    dias_vacaciones_disponibles: float
    dias_teletrabajo_anuales: float
    dias_teletrabajo_cogidos: float
    dias_teletrabajo_disponibles: float


class VacationsService:
    def __init__(self, sheets: SheetsService) -> None:
        self._sheets = sheets

    def ensure_structure_and_seed_demo(self) -> None:
        employees = self._sheets.read_worksheet_df(EMPLOYEES_WS, EMPLOYEE_HEADERS)
        absences = self._sheets.read_worksheet_df(ABSENCES_WS, ABSENCE_HEADERS)
        holidays = self._sheets.read_worksheet_df(HOLIDAYS_WS, HOLIDAY_HEADERS)
        if employees.empty:
            self._sheets.write_worksheet_df(EMPLOYEES_WS, pd.DataFrame(_demo_employees()), EMPLOYEE_HEADERS)
            employees = self._sheets.read_worksheet_df(EMPLOYEES_WS, EMPLOYEE_HEADERS)
        if absences.empty:
            self._sheets.write_worksheet_df(ABSENCES_WS, pd.DataFrame(_demo_absences()), ABSENCE_HEADERS)
        else:
            synced = self._sync_absence_names(absences, employees)
            if synced is not None:
                self._sheets.write_worksheet_df(ABSENCES_WS, synced, ABSENCE_HEADERS)
        if holidays.empty:
            self._sheets.write_worksheet_df(HOLIDAYS_WS, pd.DataFrame(_default_leganes_holidays()), HOLIDAY_HEADERS)
        else:
            synced_holidays = self._sync_default_holidays(holidays)
            if synced_holidays is not None:
                self._sheets.write_worksheet_df(HOLIDAYS_WS, synced_holidays, HOLIDAY_HEADERS)

    def employees(self) -> pd.DataFrame:
        return self._sheets.read_worksheet_df(EMPLOYEES_WS, EMPLOYEE_HEADERS)

    def absences(self) -> pd.DataFrame:
        return self._sheets.read_worksheet_df(ABSENCES_WS, ABSENCE_HEADERS)

    def holidays(self) -> pd.DataFrame:
        return self._sheets.read_worksheet_df(HOLIDAYS_WS, HOLIDAY_HEADERS)

    def summary_for_year(self, year: int) -> pd.DataFrame:
        employees = self.employees()
        absences = self.absences()
        holidays = self.holidays()
        if employees.empty:
            return pd.DataFrame(columns=[f.name for f in VacationSummaryRow.__dataclass_fields__.values()])

        employees = employees[employees["anio"].astype(str) == str(year)].copy()
        if employees.empty:
            return pd.DataFrame(columns=[f.name for f in VacationSummaryRow.__dataclass_fields__.values()])

        holiday_dates = _holiday_dates_for_year(holidays, year)
        out: list[dict[str, str | float]] = []
        for _, employee in employees.iterrows():
            employee_id = str(employee.get("employee_id", "")).strip()
            nombre = str(employee.get("nombre", "")).strip()
            vac_total = _to_float(employee.get("dias_vacaciones_anuales", "0"))
            tw_total = _to_float(employee.get("dias_teletrabajo_anuales", "0"))

            person_absences = absences[absences["employee_id"].astype(str) == employee_id].copy()
            person_absences = person_absences[person_absences["estado"].astype(str).str.lower() == "aprobado"]
            vac_taken = 0.0
            tw_taken = 0.0
            for _, row in person_absences.iterrows():
                kind = str(row.get("tipo", "")).strip().lower()
                days = _business_days_between(
                    str(row.get("fecha_inicio", "")).strip(),
                    str(row.get("fecha_fin", "")).strip(),
                    holiday_dates,
                    str(row.get("medio_dia", "")).strip().lower() == "true",
                )
                if kind == "vacaciones":
                    vac_taken += days
                elif kind == "teletrabajo":
                    tw_taken += days

            out.append(
                {
                    "employee_id": employee_id,
                    "nombre": nombre,
                    "dias_vacaciones_anuales": vac_total,
                    "dias_vacaciones_cogidos": round(vac_taken, 1),
                    "dias_vacaciones_disponibles": round(vac_total - vac_taken, 1),
                    "dias_teletrabajo_anuales": tw_total,
                    "dias_teletrabajo_cogidos": round(tw_taken, 1),
                    "dias_teletrabajo_disponibles": round(tw_total - tw_taken, 1),
                }
            )
        return pd.DataFrame(out)

    def upsert_absence(self, row: dict[str, str]) -> str:
        leave_id = str(row.get("leave_id", "")).strip()
        absences = self.absences()
        now = date.today().isoformat()
        if not leave_id:
            leave_id = self.next_leave_id(absences)
        payload: dict[str, str] = {
            "leave_id": leave_id,
            "employee_id": str(row.get("employee_id", "")).strip(),
            "nombre_employee": str(row.get("nombre_employee", "")).strip(),
            "tipo": str(row.get("tipo", "")).strip().lower(),
            "fecha_inicio": str(row.get("fecha_inicio", "")).strip(),
            "fecha_fin": str(row.get("fecha_fin", "")).strip(),
            "medio_dia": "TRUE" if str(row.get("medio_dia", "")).strip().lower() in {"true", "1", "si", "sí", "yes"} else "FALSE",
            "estado": str(row.get("estado", "")).strip().lower(),
            "comentario": str(row.get("comentario", "")).strip(),
            "created_at": str(row.get("created_at", "")).strip() or now,
            "updated_at": now,
        }

        row_map = self._sheets.row_numbers_by_id(ABSENCES_WS, "leave_id")
        row_number = row_map.get(leave_id)
        if row_number:
            self._sheets.update_worksheet_row(ABSENCES_WS, ABSENCE_HEADERS, row_number, payload)
        else:
            self._sheets.append_worksheet_row(ABSENCES_WS, ABSENCE_HEADERS, payload)
        return leave_id

    def delete_absence(self, leave_id: str) -> bool:
        target = str(leave_id).strip()
        if not target:
            return False
        absences = self.absences()
        if absences.empty or "leave_id" not in absences.columns:
            return False
        before = len(absences)
        filtered = absences[absences["leave_id"].astype(str) != target].copy()
        if len(filtered) == before:
            return False
        self._sheets.write_worksheet_df(ABSENCES_WS, filtered, ABSENCE_HEADERS)
        return True

    def next_leave_id(self, absences: pd.DataFrame | None = None) -> str:
        frame = absences if absences is not None else self.absences()
        if frame.empty or "leave_id" not in frame.columns:
            return "LV001"
        max_num = 0
        for raw in frame["leave_id"].astype(str).tolist():
            txt = raw.strip().upper()
            if txt.startswith("LV"):
                num = txt[2:]
                if num.isdigit():
                    max_num = max(max_num, int(num))
        return f"LV{max_num + 1:03d}"

    def _sync_absence_names(self, absences: pd.DataFrame, employees: pd.DataFrame) -> pd.DataFrame | None:
        if absences.empty or employees.empty:
            return None
        if "nombre_employee" not in absences.columns:
            absences["nombre_employee"] = ""
        mapping = {
            str(row.get("employee_id", "")).strip(): str(row.get("nombre", "")).strip()
            for _, row in employees.iterrows()
        }
        out = absences.copy()
        changed = False
        for idx, row in out.iterrows():
            employee_id = str(row.get("employee_id", "")).strip()
            name = mapping.get(employee_id, "")
            current_employee_name = str(row.get("nombre_employee", "")).strip()
            if not current_employee_name and name:
                out.at[idx, "nombre_employee"] = name
                changed = True
        return out if changed else None

    def _sync_default_holidays(self, holidays: pd.DataFrame) -> pd.DataFrame | None:
        if holidays.empty:
            return None
        defaults = pd.DataFrame(_default_leganes_holidays())
        defaults_2026 = defaults[defaults["anio"] == "2026"].copy()
        if defaults_2026.empty:
            return None

        out = holidays.copy()
        out["fecha"] = out["fecha"].astype(str).str.strip()
        out["anio"] = out["anio"].astype(str).str.strip()
        out["nombre_festivo"] = out["nombre_festivo"].astype(str).str.strip()

        existing_2026_names = set(
            out.loc[out["anio"] == "2026", "nombre_festivo"].astype(str).str.strip().tolist()
        )
        missing = defaults_2026[
            ~defaults_2026["nombre_festivo"].astype(str).str.strip().isin(existing_2026_names)
        ]
        if missing.empty:
            return None

        merged = pd.concat([out, missing], ignore_index=True)
        return merged[HOLIDAY_HEADERS].fillna("").astype(str)


def _to_float(value: str | float | int) -> float:
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return 0.0


def _to_date(raw: str) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    # Prefer canonical ISO dates (YYYY-MM-DD), then fallback to day-first inputs.
    parsed = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    if pd.isna(parsed):
        parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _holiday_dates_for_year(holidays: pd.DataFrame, year: int) -> set[date]:
    out: set[date] = set()
    if holidays.empty:
        return out
    filtered = holidays[holidays["anio"].astype(str) == str(year)]
    for value in filtered["fecha"].astype(str).tolist():
        parsed = _to_date(value)
        if parsed:
            out.add(parsed)
    return out


def is_business_day(day: date, holidays: set[date]) -> bool:
    """True for Mon–Fri that are not in the Leganés holiday set."""
    return day.weekday() < 5 and day not in holidays


def _business_days_between(start_raw: str, end_raw: str, holidays: set[date], half_day: bool = False) -> float:
    start = _to_date(start_raw)
    end = _to_date(end_raw)
    if not start:
        return 0.0
    if not end:
        end = start
    if end < start:
        start, end = end, start

    count = 0.0
    cursor = start
    while cursor <= end:
        if is_business_day(cursor, holidays):
            count += 1.0
        cursor += timedelta(days=1)
    if half_day and count > 0:
        return 0.5
    return count


def _coerce_to_date(value: object) -> date | None:
    """Normalize Timestamp/datetime/str to a pure datetime.date (not a Timestamp)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if type(value) is date:
        return value
    # pd.Timestamp / datetime.datetime are subclasses of date; always unwrap.
    if hasattr(value, "date") and callable(getattr(value, "date", None)):
        try:
            coerced = value.date()  # type: ignore[union-attr]
            if type(coerced) is date:
                return coerced
        except Exception:
            pass
    return _to_date(str(value or ""))


def expand_absence_day_types(
    absences: list[dict[str, object]] | pd.DataFrame,
    year: int,
    holiday_dates: set[date],
) -> dict[date, str]:
    """Map calendar days to ausencia/teletrabajo, skipping weekends and holidays.

    Vacaciones wins over teletrabajo when both mark the same day.
    Keys are always pure datetime.date so calendar HTML lookups work.
    """
    out: dict[date, str] = {}
    if isinstance(absences, pd.DataFrame):
        if absences.empty:
            return out
        rows = absences.to_dict("records")
    else:
        rows = list(absences)
        if not rows:
            return out

    for row in rows:
        start = _coerce_to_date(row.get("fecha_inicio"))
        end = _coerce_to_date(row.get("fecha_fin"))
        if not start:
            continue
        if not end:
            end = start
        if end < start:
            start, end = end, start
        kind = str(row.get("tipo", "") or "").strip().lower()
        cursor = start
        while cursor <= end:
            if cursor.year == year and is_business_day(cursor, holiday_dates):
                existing = out.get(cursor, "")
                if kind == "teletrabajo":
                    if existing == "":
                        out[cursor] = "teletrabajo"
                else:
                    out[cursor] = "ausencia"
            cursor += timedelta(days=1)
    return out


def _demo_employees() -> list[dict[str, str]]:
    return [
        {
            "employee_id": "EMP001",
            "nombre": "Marco Ruano",
            "dias_vacaciones_anuales": "23",
            "dias_teletrabajo_anuales": "48",
            "anio": "2026",
            "activo": "TRUE",
        },
        {
            "employee_id": "EMP002",
            "nombre": "Carla Moreno",
            "dias_vacaciones_anuales": "23",
            "dias_teletrabajo_anuales": "48",
            "anio": "2026",
            "activo": "TRUE",
        },
        {
            "employee_id": "EMP003",
            "nombre": "David Ortiz",
            "dias_vacaciones_anuales": "23",
            "dias_teletrabajo_anuales": "48",
            "anio": "2026",
            "activo": "TRUE",
        },
    ]


def _demo_absences() -> list[dict[str, str]]:
    today = date.today().isoformat()
    return [
        {
            "leave_id": "LV001",
            "employee_id": "EMP001",
            "nombre_employee": "Marco Ruano",
            "tipo": "vacaciones",
            "fecha_inicio": "2026-05-25",
            "fecha_fin": "2026-05-29",
            "medio_dia": "FALSE",
            "estado": "aprobado",
            "comentario": "Viaje familiar",
            "created_at": today,
            "updated_at": today,
        },
        {
            "leave_id": "LV002",
            "employee_id": "EMP002",
            "nombre_employee": "Carla Moreno",
            "tipo": "teletrabajo",
            "fecha_inicio": "2026-06-10",
            "fecha_fin": "2026-06-10",
            "medio_dia": "FALSE",
            "estado": "aprobado",
            "comentario": "Trabajo remoto",
            "created_at": today,
            "updated_at": today,
        },
        {
            "leave_id": "LV003",
            "employee_id": "EMP003",
            "nombre_employee": "David Ortiz",
            "tipo": "vacaciones",
            "fecha_inicio": "2026-08-03",
            "fecha_fin": "2026-08-14",
            "medio_dia": "FALSE",
            "estado": "aprobado",
            "comentario": "Vacaciones verano",
            "created_at": today,
            "updated_at": today,
        },
    ]


def _default_leganes_holidays() -> list[dict[str, str]]:
    # Festivos de referencia para 2026 solicitados por negocio.
    return [
        {"fecha": "2026-01-01", "nombre_festivo": "Ano Nuevo", "ambito": "nacional", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-01-06", "nombre_festivo": "Reyes", "ambito": "nacional", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-04-02", "nombre_festivo": "Jueves Santo", "ambito": "nacional", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-04-03", "nombre_festivo": "Viernes Santo", "ambito": "nacional", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-05-01", "nombre_festivo": "Dia del Trabajo", "ambito": "nacional", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-05-02", "nombre_festivo": "Comunidad de Madrid", "ambito": "comunidad", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-08-14", "nombre_festivo": "Virgen de Butarque", "ambito": "local", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-08-15", "nombre_festivo": "Asuncion", "ambito": "nacional", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-10-12", "nombre_festivo": "Fiesta Nacional", "ambito": "nacional", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-11-02", "nombre_festivo": "Dia siguiente a Todos los Santos", "ambito": "nacional", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-12-07", "nombre_festivo": "Dia siguiente a la Constitucion", "ambito": "nacional", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-12-08", "nombre_festivo": "Inmaculada", "ambito": "nacional", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-12-24", "nombre_festivo": "Convenio Ingenieros (Nochebuena)", "ambito": "convenio", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-12-25", "nombre_festivo": "Navidad", "ambito": "nacional", "municipio": "Leganes", "anio": "2026"},
        {"fecha": "2026-12-31", "nombre_festivo": "Convenio Ingenieros (Nochevieja)", "ambito": "convenio", "municipio": "Leganes", "anio": "2026"},
    ]
