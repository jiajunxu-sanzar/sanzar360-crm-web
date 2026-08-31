"""Control de asistencia: registros diarios, horas exigidas y saldo mensual.

La base de datos es el propio Google Sheet del CRM:

- ``Asistencia_Registros``: una fila por persona y dia trabajado.
- ``Usuarios CRM``: quien es quien (``nombre_fichaje``), su jornada habitual
  (``jornada``) y las excepciones por mes (``jornada_excepciones``).
- ``Vacaciones_Ausencias`` y ``Vacaciones_Festivos``: se leen para descontar
  vacaciones y ausencias aprobadas de las horas exigidas y para dar por
  cumplidos los dias de teletrabajo aprobados.

Reglas de computo (las mismas que muestra el boton "i" de la pagina):

- Un dia con dos o mas fichajes cuenta de la primera a la ultima marca.
- Un dia con un solo fichaje se toma como jornada completa (origen
  ``estimado``): no se sabe cuando salio, pero el dia se trabajo.
- A las jornadas de 8 h o mas se les descuentan 30 minutos de comida por cada
  dia con registro.
- Los dias de vacaciones y ausencias aprobadas no cuentan como dias exigidos.
- Los dias de teletrabajo aprobado cuentan como jornada completa sin necesidad
  de fichaje; si ademas hay registro, manda el registro.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO

import pandas as pd

from services.sheets_service import SheetsService
from services.vacations_service import (
    ABSENCE_HEADERS,
    ABSENCES_WS,
    HOLIDAY_HEADERS,
    HOLIDAYS_WS,
    expand_absence_day_types,
)

RECORDS_WS = "Asistencia_Registros"

RECORD_HEADERS = [
    "registro_id",
    "employee_id",
    "nombre",
    "fecha",
    "anio_mes",
    "entrada",
    "salida",
    "horas",
    "origen",
    "nota",
    "created_at",
    "updated_at",
]

ORIGEN_FICHAJE = "fichaje"
ORIGEN_ESTIMADO = "estimado"
ORIGEN_MANUAL = "manual"

# Minutos de comida que se descuentan por dia con registro a las jornadas
# largas, y jornada a partir de la cual se aplica.
MEAL_BREAK_HOURS = 0.5
MEAL_BREAK_MIN_JORNADA = 8.0

DEFAULT_ENTRY_TIME = "09:00"

REPORT_SHEET = "Registros de asistencia"
REPORT_NAME_COLUMN = 12  # 1-based, tal y como viene el informe de la maquina.
REPORT_BLOCK_HEIGHT = 4

MESES_ES = [
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]


def month_label(anio: int, mes: int) -> str:
    return f"{MESES_ES[mes]} {anio}"


# ---------------------------------------------------------------- personas


@dataclass(frozen=True)
class AttendancePerson:
    """Persona del CRM con lo que hace falta para contar sus horas."""

    employee_id: str
    nombre: str
    nombre_fichaje: str = ""
    jornada: str = ""
    jornada_excepciones: str = ""

    def jornada_for(self, anio: int, mes: int) -> float | None:
        return resolve_jornada(self.jornada, self.jornada_excepciones, anio, mes)


def people_from_users(users: list[object]) -> list[AttendancePerson]:
    """Convierte los ``AppUser`` de ``Usuarios CRM`` en personas de asistencia."""
    out: list[AttendancePerson] = []
    for user in users:
        employee_id = str(getattr(user, "employee_id", "") or "").strip()
        nombre = str(getattr(user, "nombre", "") or "").strip()
        if not employee_id or not nombre:
            continue
        out.append(
            AttendancePerson(
                employee_id=employee_id,
                nombre=nombre,
                nombre_fichaje=str(getattr(user, "nombre_fichaje", "") or "").strip(),
                jornada=str(getattr(user, "jornada", "") or "").strip(),
                jornada_excepciones=str(getattr(user, "jornada_excepciones", "") or "").strip(),
            )
        )
    return out


def _normalize_name(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def people_by_report_name(people: list[AttendancePerson]) -> dict[str, AttendancePerson]:
    """Indice ``nombre en la maquina de fichar -> persona``.

    Se aceptan varios alias separados por ``;`` o ``,`` en ``nombre_fichaje``,
    y como ultimo recurso el propio nombre del CRM.
    """
    out: dict[str, AttendancePerson] = {}
    for person in people:
        for raw in re.split(r"[;,]", person.nombre_fichaje or ""):
            alias = _normalize_name(raw)
            if alias:
                out.setdefault(alias, person)
    for person in people:
        out.setdefault(_normalize_name(person.nombre), person)
    return out


def resolve_jornada(
    jornada_raw: str | float | int,
    excepciones_raw: str,
    anio: int,
    mes: int,
) -> float | None:
    """Horas diarias de una persona en un mes concreto.

    ``excepciones_raw`` admite ``"2026-07:8, 2026-08:8"`` (tambien con ``;`` o
    saltos de linea como separador). Si no hay excepcion para ese mes se usa la
    jornada habitual; si no hay jornada habitual, ``None``.
    """
    clave = f"{int(anio)}-{int(mes):02d}"
    for chunk in re.split(r"[;,\n]", str(excepciones_raw or "")):
        if ":" not in chunk:
            continue
        mes_txt, horas_txt = chunk.split(":", 1)
        if mes_txt.strip() != clave:
            continue
        horas = _to_float_or_none(horas_txt)
        if horas is not None:
            return horas
    return _to_float_or_none(jornada_raw)


def _to_float_or_none(value: str | float | int | None) -> float | None:
    text = str(value if value is not None else "").strip().replace(",", ".")
    text = text.rstrip("hH ").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


# ------------------------------------------------------------------- horas


def parse_marks(raw: object) -> list[str]:
    """Marcas HH:MM que aparecen en la celda de fichajes de un dia."""
    if raw is None:
        return []
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none"}:
        return []
    return re.findall(r"\d{1,2}:\d{2}", text)


def time_to_minutes(value: str) -> int:
    hours, minutes = str(value).split(":")
    return int(hours) * 60 + int(minutes)


def minutes_to_time(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def hours_between(entrada: str, salida: str) -> float:
    diff = time_to_minutes(salida) - time_to_minutes(entrada)
    if diff < 0:
        diff += 24 * 60
    return round(diff / 60.0, 2)


def meal_break_for(jornada: float) -> float:
    """Comida que se descuenta por dia registrado (solo jornadas largas)."""
    return MEAL_BREAK_HOURS if float(jornada) >= MEAL_BREAK_MIN_JORNADA else 0.0


def gross_full_day_hours(jornada: float) -> float:
    """Horas brutas de un dia que se da por jornada completa.

    Se guardan en bruto (con la comida incluida) para que al descontarla en el
    total el dia quede exactamente en la jornada de la persona.
    """
    return round(float(jornada) + meal_break_for(jornada), 2)


def full_day_times(jornada: float, entrada: str = DEFAULT_ENTRY_TIME) -> tuple[str, str, float]:
    """(entrada, salida, horas brutas) de un dia de jornada completa."""
    gross = gross_full_day_hours(jornada)
    salida = minutes_to_time(time_to_minutes(entrada) + int(round(gross * 60)))
    return entrada, salida, gross


def net_hours(records: list[dict[str, object]], jornada: float) -> float:
    """Horas efectivas de un conjunto de registros, ya descontada la comida."""
    total = sum(_to_float_or_none(row.get("horas")) or 0.0 for row in records)
    total -= meal_break_for(jornada) * len(records)
    return round(total, 2)


# ----------------------------------------------------------- calendario


def business_days(anio: int, mes: int, holiday_dates: set[date]) -> list[date]:
    """Dias de lunes a viernes del mes que no son festivo."""
    total = calendar.monthrange(anio, mes)[1]
    out: list[date] = []
    for day in range(1, total + 1):
        current = date(anio, mes, day)
        if current.weekday() < 5 and current not in holiday_dates:
            out.append(current)
    return out


def holiday_dates_for_year(holidays: pd.DataFrame, anio: int) -> set[date]:
    out: set[date] = set()
    if holidays is None or holidays.empty or "fecha" not in holidays.columns:
        return out
    frame = holidays
    if "anio" in holidays.columns:
        frame = holidays[holidays["anio"].astype(str).str.strip() == str(anio)]
    for raw in frame["fecha"].astype(str).tolist():
        parsed = pd.to_datetime(raw, errors="coerce")
        if not pd.isna(parsed):
            out.add(parsed.date())
    return out


def approved_absences(absences: pd.DataFrame) -> pd.DataFrame:
    """Solo las ausencias aprobadas: las pendientes no descuentan nada."""
    if absences is None or absences.empty or "estado" not in absences.columns:
        return pd.DataFrame(columns=ABSENCE_HEADERS)
    return absences[absences["estado"].astype(str).str.strip().str.lower() == "aprobado"].copy()


def absence_days_by_employee(
    absences: pd.DataFrame,
    anio: int,
    holiday_dates: set[date],
) -> dict[str, dict[date, str]]:
    """``employee_id -> {dia: "ausencia" | "teletrabajo"}`` del año indicado."""
    out: dict[str, dict[date, str]] = {}
    approved = approved_absences(absences)
    if approved.empty:
        return out
    for employee_id, rows in approved.groupby(approved["employee_id"].astype(str).str.strip()):
        if not employee_id:
            continue
        out[employee_id] = expand_absence_day_types(rows, anio, holiday_dates)
    return out


def absence_days_for_people(
    absences: pd.DataFrame,
    people: list[AttendancePerson],
    anio: int,
    holiday_dates: set[date],
) -> dict[str, dict[date, str]]:
    """Ausencias aprobadas de cada persona, cruzando por id y, si no, por nombre.

    ``Vacaciones_Empleados`` y ``Usuarios CRM`` son hojas distintas y sus
    ``employee_id`` no tienen por que coincidir. Cruzar solo por id hacia que
    las vacaciones de alguien no descontasen nada y su saldo saliera en
    negativo sin motivo, asi que el nombre sirve de red de seguridad.
    """
    out: dict[str, dict[date, str]] = {}
    approved = approved_absences(absences)
    if approved.empty or not people:
        return out

    por_id = {p.employee_id: p for p in people}
    por_nombre = {_normalize_name(p.nombre): p for p in people}

    filas_por_persona: dict[str, list[dict[str, object]]] = {}
    for row in approved.to_dict("records"):
        person = por_id.get(str(row.get("employee_id", "")).strip())
        if person is None:
            person = por_nombre.get(_normalize_name(str(row.get("nombre_employee", ""))))
        if person is None:
            continue
        filas_por_persona.setdefault(person.employee_id, []).append(row)

    for employee_id, filas in filas_por_persona.items():
        out[employee_id] = expand_absence_day_types(filas, anio, holiday_dates)
    return out


def unmatched_absence_names(
    absences: pd.DataFrame, people: list[AttendancePerson]
) -> list[str]:
    """Nombres de Vacaciones que no cuadran con ningun usuario del CRM."""
    approved = approved_absences(absences)
    if approved.empty:
        return []
    ids = {p.employee_id for p in people}
    nombres = {_normalize_name(p.nombre) for p in people}
    sueltos: set[str] = set()
    for row in approved.to_dict("records"):
        if str(row.get("employee_id", "")).strip() in ids:
            continue
        nombre = str(row.get("nombre_employee", "")).strip()
        if _normalize_name(nombre) in nombres:
            continue
        sueltos.add(nombre or str(row.get("employee_id", "")).strip())
    return sorted(n for n in sueltos if n)


# ------------------------------------------------------------- registros


def record_id(employee_id: str, fecha: date) -> str:
    return f"{str(employee_id).strip()}_{fecha.isoformat()}"


def build_record(
    person: AttendancePerson,
    fecha: date,
    entrada: str,
    salida: str,
    horas: float,
    origen: str,
    nota: str = "",
    created_at: str = "",
) -> dict[str, str]:
    today = date.today().isoformat()
    return {
        "registro_id": record_id(person.employee_id, fecha),
        "employee_id": person.employee_id,
        "nombre": person.nombre,
        "fecha": fecha.isoformat(),
        "anio_mes": f"{fecha.year}-{fecha.month:02d}",
        "entrada": entrada,
        "salida": salida,
        "horas": f"{round(float(horas), 2)}",
        "origen": origen,
        "nota": str(nota or "").strip(),
        "created_at": str(created_at or "").strip() or today,
        "updated_at": today,
    }


def manual_record(
    person: AttendancePerson,
    fecha: date,
    jornada: float,
    *,
    entrada: str | None = None,
    salida: str | None = None,
    nota: str = "",
    created_at: str = "",
) -> dict[str, str]:
    """Registro dado de alta a mano: con horario concreto o jornada completa."""
    if entrada and salida:
        horas = hours_between(entrada, salida)
        return build_record(
            person, fecha, entrada, salida, horas, ORIGEN_MANUAL, nota, created_at
        )
    entrada_final, salida_final, horas = full_day_times(jornada, entrada or DEFAULT_ENTRY_TIME)
    return build_record(
        person, fecha, entrada_final, salida_final, horas, ORIGEN_MANUAL, nota, created_at
    )


def records_to_frame(records: list[dict[str, str]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=RECORD_HEADERS)
    frame = pd.DataFrame(records)
    for header in RECORD_HEADERS:
        if header not in frame.columns:
            frame[header] = ""
    return frame[RECORD_HEADERS].fillna("").astype(str)


def merge_records(existing: pd.DataFrame, incoming: list[dict[str, str]]) -> pd.DataFrame:
    """Mezcla registros nuevos sobre los existentes, respetando el id del dia.

    Un dia que ya existe se sobreescribe con el registro nuevo, conservando su
    ``created_at``. Los dias que no vienen en ``incoming`` se quedan como
    estaban: reprocesar un mes no borra los dias dados de alta a mano.
    """
    base = existing.copy() if existing is not None and not existing.empty else pd.DataFrame(columns=RECORD_HEADERS)
    for header in RECORD_HEADERS:
        if header not in base.columns:
            base[header] = ""
    base = base[RECORD_HEADERS].fillna("").astype(str)

    created_by_id = {
        str(row["registro_id"]).strip(): str(row.get("created_at", "")).strip()
        for _, row in base.iterrows()
    }
    incoming_by_id: dict[str, dict[str, str]] = {}
    for row in incoming:
        rid = str(row.get("registro_id", "")).strip()
        if not rid:
            continue
        merged = dict(row)
        previous = created_by_id.get(rid, "")
        if previous:
            merged["created_at"] = previous
        incoming_by_id[rid] = merged

    kept = base[~base["registro_id"].astype(str).str.strip().isin(incoming_by_id.keys())]
    out = pd.concat([kept, records_to_frame(list(incoming_by_id.values()))], ignore_index=True)
    return sort_records(out)


def sort_records(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out["_orden"] = pd.to_datetime(out["fecha"], errors="coerce")
    out = out.sort_values(["_orden", "nombre"], kind="stable").drop(columns=["_orden"])
    return out.reset_index(drop=True)


def records_for_month(records: pd.DataFrame, anio: int, mes: int) -> pd.DataFrame:
    if records is None or records.empty:
        return pd.DataFrame(columns=RECORD_HEADERS)
    return records[records["anio_mes"].astype(str).str.strip() == f"{anio}-{mes:02d}"].copy()


# Estado de un dia en el calendario de alta manual. Los dos primeros no se
# pueden seleccionar: ya hay un dato que diria lo contrario de lo que ibas a
# meter.
DAY_RECORDED = "registrado"
DAY_ABSENCE = "ausencia"
DAY_REMOTE = "teletrabajo"
DAY_NON_WORKING = "no_laborable"
DAY_FREE = "libre"

BLOCKED_DAY_STATES = frozenset({DAY_RECORDED, DAY_ABSENCE})


def day_picker_state(
    day: date,
    recorded: set[date],
    holiday_dates: set[date],
    absence_days: dict[date, str],
) -> str:
    """Por que un dia se puede o no dar de alta a mano.

    Manda el registro existente sobre todo lo demas: si el dia ya tiene datos,
    ese es el motivo por el que no se toca. Despues las vacaciones y ausencias
    aprobadas, que contradicen cualquier horario que se quisiera meter.
    """
    if day in recorded:
        return DAY_RECORDED
    if absence_days.get(day) == "ausencia":
        return DAY_ABSENCE
    if absence_days.get(day) == "teletrabajo":
        return DAY_REMOTE
    if day.weekday() >= 5 or day in holiday_dates:
        return DAY_NON_WORKING
    return DAY_FREE


def is_day_selectable(state: str) -> bool:
    return state not in BLOCKED_DAY_STATES


def recorded_dates(records: pd.DataFrame, employee_id: str) -> set[date]:
    """Dias que ya tienen registro para una persona (los que no se pueden re-dar de alta)."""
    if records is None or records.empty:
        return set()
    person = records[records["employee_id"].astype(str).str.strip() == str(employee_id).strip()]
    out: set[date] = set()
    for raw in person["fecha"].astype(str).tolist():
        parsed = pd.to_datetime(raw, errors="coerce")
        if not pd.isna(parsed):
            out.add(parsed.date())
    return out


# --------------------------------------------------------------- resumen


@dataclass(frozen=True)
class MonthSummary:
    employee_id: str
    nombre: str
    anio: int
    mes_num: int
    mes: str
    jornada: float
    dias_laborables: int
    dias_ausencia: int
    dias_exigidos: int
    dias_registrados: int
    dias_teletrabajo_auto: int
    mes_en_curso: bool
    sin_datos: bool
    horas_exigidas: float
    horas_registradas: float
    horas_teletrabajo: float
    horas_computadas: float
    saldo: float


def month_summary(
    person: AttendancePerson,
    anio: int,
    mes: int,
    records: pd.DataFrame,
    holiday_dates: set[date],
    absence_days: dict[date, str],
    today: date | None = None,
) -> MonthSummary | None:
    """Resumen de un mes para una persona, o ``None`` si no tiene jornada.

    Del mes en curso solo se exigen los dias que ya han pasado: pedir el mes
    entero el dia 5 sacaria un saldo negativo enorme que no significa nada.
    """
    jornada = person.jornada_for(anio, mes)
    if jornada is None:
        return None

    referencia = today or date.today()
    mes_en_curso = (anio, mes) == (referencia.year, referencia.month)
    laborables = business_days(anio, mes, holiday_dates)
    if mes_en_curso:
        laborables = [d for d in laborables if d <= referencia]
    dias_ausencia = [d for d in laborables if absence_days.get(d) == "ausencia"]
    dias_exigidos = [d for d in laborables if absence_days.get(d) != "ausencia"]

    del_mes = records_for_month(records, anio, mes)
    del_mes = del_mes[del_mes["employee_id"].astype(str).str.strip() == person.employee_id]
    filas = del_mes.to_dict("records")
    dias_con_registro = recorded_dates(del_mes, person.employee_id)

    teletrabajo_auto = [
        d
        for d in dias_exigidos
        if absence_days.get(d) == "teletrabajo" and d not in dias_con_registro
    ]

    horas_registradas = net_hours(filas, jornada)
    horas_teletrabajo = round(jornada * len(teletrabajo_auto), 2)
    horas_exigidas = round(jornada * len(dias_exigidos), 2)
    horas_computadas = round(horas_registradas + horas_teletrabajo, 2)

    return MonthSummary(
        employee_id=person.employee_id,
        nombre=person.nombre,
        anio=anio,
        mes_num=mes,
        mes=month_label(anio, mes),
        jornada=float(jornada),
        dias_laborables=len(laborables),
        dias_ausencia=len(dias_ausencia),
        dias_exigidos=len(dias_exigidos),
        dias_registrados=len(filas),
        dias_teletrabajo_auto=len(teletrabajo_auto),
        mes_en_curso=mes_en_curso,
        sin_datos=not filas and not teletrabajo_auto,
        horas_exigidas=horas_exigidas,
        horas_registradas=horas_registradas,
        horas_teletrabajo=horas_teletrabajo,
        horas_computadas=horas_computadas,
        saldo=round(horas_computadas - horas_exigidas, 2),
    )


def months_of_year(anio: int, today: date | None = None) -> list[int]:
    """Meses a computar de un año: hasta el mes en curso si es el año actual."""
    reference = today or date.today()
    if anio > reference.year:
        return []
    if anio == reference.year:
        return list(range(1, reference.month + 1))
    return list(range(1, 13))


def year_summary(
    people: list[AttendancePerson],
    anio: int,
    records: pd.DataFrame,
    holidays: pd.DataFrame,
    absences: pd.DataFrame,
    today: date | None = None,
) -> pd.DataFrame:
    """Tabla persona x mes con horas exigidas, hechas, saldo y acumulado."""
    referencia = today or date.today()
    holiday_set = holiday_dates_for_year(holidays, anio)
    absence_by_employee = absence_days_for_people(absences, people, anio, holiday_set)
    meses = months_of_year(anio, referencia)

    filas: list[dict[str, object]] = []
    for person in people:
        acumulado = 0.0
        for mes in meses:
            resumen = month_summary(
                person,
                anio,
                mes,
                records,
                holiday_set,
                absence_by_employee.get(person.employee_id, {}),
                today=referencia,
            )
            if resumen is None:
                continue
            # Un mes sin ningun registro no suma al acumulado: casi siempre
            # significa que falta subir el informe, no que no se trabajara.
            # En cuanto se procese, el mes entra solo.
            if not resumen.sin_datos:
                acumulado = round(acumulado + resumen.saldo, 2)
            fila = resumen.__dict__.copy()
            fila["saldo_acumulado"] = acumulado
            filas.append(fila)
    if not filas:
        return pd.DataFrame(
            columns=[*MonthSummary.__dataclass_fields__.keys(), "saldo_acumulado"]
        )
    return pd.DataFrame(filas)


# ------------------------------------------------- lectura de informes


@dataclass
class ParsedReport:
    """Contenido util de un informe de la maquina de fichar."""

    anio: int
    mes: int
    marcas_por_nombre: dict[str, dict[int, str]] = field(default_factory=dict)

    @property
    def mes_label(self) -> str:
        return month_label(self.anio, self.mes)


def _sheet_grid(data: bytes, filename: str) -> list[list[object]]:
    """Informe (.xls o .xlsx) como rejilla de celdas, sin cabeceras."""
    buffer = BytesIO(data)
    lower = str(filename).lower()
    engine = "xlrd" if lower.endswith(".xls") else "openpyxl"
    try:
        sheets = pd.read_excel(buffer, sheet_name=None, header=None, engine=engine)
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise ValueError(
            f"Falta la libreria para leer '{filename}': {exc}. Instala xlrd para .xls."
        ) from exc
    if REPORT_SHEET not in sheets:
        raise ValueError(f"'{filename}' no tiene la hoja '{REPORT_SHEET}'.")
    frame = sheets[REPORT_SHEET]
    return frame.values.tolist()


def _cell(grid: list[list[object]], row: int, col: int) -> object:
    """Celda 0-indexada, o ``None`` fuera de rango."""
    if row < 0 or row >= len(grid):
        return None
    fila = grid[row]
    if col < 0 or col >= len(fila):
        return None
    value = fila[col]
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def detect_month_year(grid: list[list[object]]) -> tuple[int, int]:
    """Mes y año del informe, a partir del rango que sigue a la celda 'Fecha'."""
    for row in range(min(len(grid), 10)):
        for col in range(min(len(grid[row]) if grid[row] else 0, 10)):
            value = _cell(grid, row, col)
            if value is None or "fecha" not in str(value).lower():
                continue
            for col2 in range(len(grid[row])):
                candidate = _cell(grid, row, col2)
                if candidate is None:
                    continue
                match = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(candidate))
                if match:
                    return int(match.group(2)), int(match.group(3))
    raise ValueError("No se pudo detectar el mes del informe (no aparece la celda 'Fecha').")


def parse_attendance_report(data: bytes, filename: str) -> ParsedReport:
    """Lee un informe y devuelve las marcas por nombre y dia, sin interpretarlas."""
    grid = _sheet_grid(data, filename)
    mes, anio = detect_month_year(grid)
    total_dias = calendar.monthrange(anio, mes)[1]

    marcas: dict[str, dict[int, str]] = {}
    row = 0
    while row < len(grid):
        cabecera = _cell(grid, row, 0)
        if cabecera is None or str(cabecera).strip() != "ID.":
            row += 1
            continue
        nombre = _cell(grid, row, REPORT_NAME_COLUMN - 1)
        nombre = str(nombre).strip() if nombre is not None else ""
        if not nombre:
            row += REPORT_BLOCK_HEIGHT
            continue

        fila_dias = row + 1
        fila_horas = row + 3
        del_nombre = marcas.setdefault(nombre, {})
        for col in range(min(total_dias, 31)):
            dia_val = _cell(grid, fila_dias, col)
            if dia_val is None:
                continue
            try:
                dia = int(float(str(dia_val).strip()))
            except (TypeError, ValueError):
                continue
            if not 1 <= dia <= total_dias:
                continue
            horas_txt = _cell(grid, fila_horas, col)
            del_nombre[dia] = "" if horas_txt is None else str(horas_txt)
        row += REPORT_BLOCK_HEIGHT

    return ParsedReport(anio=anio, mes=mes, marcas_por_nombre=marcas)


def records_from_report(
    report: ParsedReport,
    people: list[AttendancePerson],
    holiday_dates: set[date],
) -> tuple[list[dict[str, str]], list[str], list[str]]:
    """Convierte un informe en registros diarios.

    Devuelve ``(registros, nombres sin usuario, nombres sin jornada)``. Nunca se
    inventa una jornada: quien no la tenga en ``Usuarios CRM`` se queda fuera y
    se avisa por pantalla.
    """
    indice = people_by_report_name(people)
    registros: list[dict[str, str]] = []
    sin_usuario: list[str] = []
    sin_jornada: list[str] = []
    total_dias = calendar.monthrange(report.anio, report.mes)[1]

    for nombre, dias in report.marcas_por_nombre.items():
        person = indice.get(_normalize_name(nombre))
        if person is None:
            sin_usuario.append(nombre)
            continue
        jornada = person.jornada_for(report.anio, report.mes)
        if jornada is None:
            sin_jornada.append(nombre)
            continue

        for dia in range(1, total_dias + 1):
            fecha = date(report.anio, report.mes, dia)
            if fecha.weekday() >= 5 or fecha in holiday_dates:
                continue
            marcas = parse_marks(dias.get(dia))
            if len(marcas) >= 2:
                entrada, salida = marcas[0], marcas[-1]
                registros.append(
                    build_record(
                        person,
                        fecha,
                        entrada,
                        salida,
                        hours_between(entrada, salida),
                        ORIGEN_FICHAJE,
                    )
                )
            elif len(marcas) == 1:
                entrada, salida, horas = full_day_times(jornada)
                registros.append(
                    build_record(
                        person,
                        fecha,
                        entrada,
                        salida,
                        horas,
                        ORIGEN_ESTIMADO,
                        nota="Un solo fichaje",
                    )
                )
            # Sin marcas: dia sin fichaje. No se registra nada; el dia sigue
            # contando como exigido y aparecera como horas que faltan.

    return registros, sorted(set(sin_usuario)), sorted(set(sin_jornada))


# --------------------------------------------------------------- servicio


class AttendanceService:
    """Acceso al Google Sheet para el control de asistencia."""

    def __init__(self, sheets: SheetsService) -> None:
        self._sheets = sheets

    def records(self) -> pd.DataFrame:
        return self._sheets.read_worksheet_df(RECORDS_WS, RECORD_HEADERS)

    def absences(self) -> pd.DataFrame:
        return self._sheets.read_worksheet_df(ABSENCES_WS, ABSENCE_HEADERS)

    def holidays(self) -> pd.DataFrame:
        return self._sheets.read_worksheet_df(HOLIDAYS_WS, HOLIDAY_HEADERS)

    def save_record(self, record: dict[str, str]) -> str:
        """Alta o edicion de un dia suelto (una sola escritura en la hoja)."""
        registro_id = str(record.get("registro_id", "")).strip()
        if not registro_id:
            raise ValueError("El registro no tiene registro_id.")
        row_map = self._sheets.row_numbers_by_id(RECORDS_WS, "registro_id")
        row_number = row_map.get(registro_id)
        if row_number:
            self._sheets.update_worksheet_row(RECORDS_WS, RECORD_HEADERS, row_number, record)
        else:
            self._sheets.append_worksheet_row(RECORDS_WS, RECORD_HEADERS, record)
        return registro_id

    def save_records(self, records: list[dict[str, str]]) -> int:
        """Alta o edicion en bloque: mezcla con lo que hay y reescribe la hoja."""
        if not records:
            return 0
        if len(records) == 1:
            self.save_record(records[0])
            return 1
        merged = merge_records(self.records(), records)
        self._sheets.write_worksheet_df(RECORDS_WS, merged, RECORD_HEADERS)
        return len(records)

    def delete_record(self, registro_id: str) -> bool:
        target = str(registro_id).strip()
        if not target:
            return False
        current = self.records()
        if current.empty or "registro_id" not in current.columns:
            return False
        filtered = current[current["registro_id"].astype(str).str.strip() != target].copy()
        if len(filtered) == len(current):
            return False
        self._sheets.write_worksheet_df(RECORDS_WS, filtered, RECORD_HEADERS)
        return True
