from __future__ import annotations

import calendar
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from app.cache import sheets_service
from services.vacations_service import VacationsService

_VAC_OVERLAY_KEY = "vacaciones.manage_absences_open"


@st.cache_resource
def vacations_service() -> VacationsService:
    return VacationsService(sheets_service())


@st.cache_data(ttl=120, show_spinner=False)
def load_vacations_bundle(_version: int = 0) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    vs = vacations_service()
    vs.ensure_structure_and_seed_demo()
    year = int(pd.Timestamp.today().year)
    employees = vs.employees()
    absences = vs.absences()
    holidays = vs.holidays()
    summary = vs.summary_for_year(year)
    return employees, absences, holidays, summary


def render(_: pd.DataFrame) -> None:
    st.title("Vacaciones")
    st.caption("Control de ausencias, teletrabajo y festivos (Leganes por defecto).")

    reload_key = st.session_state.get("vacations_cache_version", 0)
    employees, absences, holidays, summary = load_vacations_bundle(reload_key)
    if employees.empty:
        st.warning("No hay empleados cargados en la hoja de vacaciones.")
        return

    selected_name = ""
    if not summary.empty:
        title_col, action_col = st.columns([4, 1])
        with title_col:
            st.subheader("Resumen anual")
        with action_col:
            if st.button("Gestionar ausencias", width="stretch"):
                st.session_state[_VAC_OVERLAY_KEY] = True
        summary_view = summary.rename(
            columns={
                "nombre": "Nombre",
                "dias_vacaciones_anuales": "Dias vacaciones",
                "dias_vacaciones_cogidos": "Cogidos",
                "dias_vacaciones_disponibles": "Disponibles",
                "dias_teletrabajo_anuales": "Dias teletrabajo",
                "dias_teletrabajo_cogidos": "Teletrabajo cogidos",
                "dias_teletrabajo_disponibles": "Teletrabajo disponibles",
            }
        )
        event = st.dataframe(
            summary_view,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="vac_summary_table",
        )
        selected_rows = event.selection.rows if event else []
        if selected_rows:
            selected_idx = int(selected_rows[0])
            if 0 <= selected_idx < len(summary_view):
                selected_name = str(summary_view.iloc[selected_idx]["Nombre"])
                st.caption(f"Empleado seleccionado: {selected_name}")
        else:
            st.caption("Haz click en una fila del resumen para ver su calendario.")

    if st.session_state.get(_VAC_OVERLAY_KEY, False):
        _manage_absences_dialog(employees, absences)

    st.subheader("Calendario de ausencias (12 meses)")
    year = int(pd.Timestamp.today().year)
    calendar_df = _build_calendar_df(absences, employees)
    holiday_dates = _holiday_dates_for_year(holidays, year)
    if selected_name:
        calendar_df = calendar_df[calendar_df["nombre_employee"] == selected_name]
    _render_year_calendar(calendar_df, year, holiday_dates)

    st.subheader("Festivos Leganes")
    current_year = str(pd.Timestamp.today().year)
    holidays_view = holidays[holidays["anio"].astype(str) == current_year].copy()
    holidays_view = holidays_view.sort_values(by="fecha", ascending=True)
    st.dataframe(
        holidays_view.rename(
            columns={
                "fecha": "Fecha",
                "nombre_festivo": "Festivo",
                "ambito": "Ambito",
                "municipio": "Municipio",
            }
        ),
        hide_index=True,
        width="stretch",
    )


@st.dialog("Anadir / editar / eliminar ausencias")
def _manage_absences_dialog(employees: pd.DataFrame, absences: pd.DataFrame) -> None:
    vs = vacations_service()
    employee_options = employees["employee_id"].astype(str).tolist()
    if not employee_options:
        st.error("No hay empleados disponibles.")
        return
    employee_name_by_id = {
        str(row.get("employee_id", "")): str(row.get("nombre", ""))
        for _, row in employees.iterrows()
    }
    action = st.selectbox("Accion", ["anadir", "editar o eliminar"])
    employee_id = st.selectbox(
        "employee_id",
        employee_options,
        format_func=lambda eid: f"{eid} - {employee_name_by_id.get(eid, eid)}",
    )
    nombre_employee = employee_name_by_id.get(employee_id, "")

    if action == "anadir":
        new_leave_id = vs.next_leave_id(absences)
        with st.form("vac_absence_add_form"):
            st.text_input("leave_id", value=new_leave_id, disabled=True)
            st.text_input("nombre_employee", value=nombre_employee, disabled=True)
            c1, c2 = st.columns(2)
            tipo = c1.selectbox("tipo", ["vacaciones", "ausencia", "teletrabajo"], key="vac_add_tipo")
            estado = c2.selectbox("estado", ["aprobado", "pendiente", "rechazado"], index=0, key="vac_add_estado")
            c3, c4 = st.columns(2)
            fecha_inicio = c3.date_input("fecha_inicio", key="vac_add_inicio")
            fecha_fin = c4.date_input("fecha_fin", key="vac_add_fin")
            medio_dia = st.checkbox("medio_dia", key="vac_add_medio")
            comentario = st.text_area("comentario", value="", key="vac_add_comentario")
            b1, b2 = st.columns(2)
            cancelar = b1.form_submit_button("Cancelar", key="vac_cancel_add_btn")
            confirmar = b2.form_submit_button("Confirmar", type="primary", key="vac_confirm_add_btn")

        if cancelar:
            st.session_state[_VAC_OVERLAY_KEY] = False
            st.rerun()
        if confirmar:
            payload = {
                "leave_id": new_leave_id,
                "employee_id": employee_id,
                "nombre_employee": nombre_employee,
                "tipo": tipo,
                "fecha_inicio": fecha_inicio.isoformat(),
                "fecha_fin": fecha_fin.isoformat(),
                "medio_dia": "TRUE" if medio_dia else "FALSE",
                "estado": estado,
                "comentario": comentario.strip(),
            }
            saved_id = vs.upsert_absence(payload)
            st.success(f"Guardado en Vacaciones_Ausencias ({saved_id}).")
            st.session_state["vacations_cache_version"] = st.session_state.get("vacations_cache_version", 0) + 1
            st.session_state[_VAC_OVERLAY_KEY] = False
            st.rerun()
        return

    employee_absences = absences[absences["employee_id"].astype(str) == employee_id].copy()
    if employee_absences.empty:
        st.info("Este empleado no tiene leave_id registrados.")
        if st.button("Cerrar"):
            st.session_state[_VAC_OVERLAY_KEY] = False
            st.rerun()
        return

    leave_options = employee_absences["leave_id"].astype(str).tolist()
    selected_leave_id = st.selectbox("leave_id", leave_options)
    selected_row = employee_absences[employee_absences["leave_id"].astype(str) == selected_leave_id].iloc[0]

    default_start = pd.to_datetime(selected_row.get("fecha_inicio", ""), errors="coerce")
    default_end = pd.to_datetime(selected_row.get("fecha_fin", ""), errors="coerce")
    if pd.isna(default_start):
        default_start = pd.Timestamp.today()
    if pd.isna(default_end):
        default_end = default_start
    default_half = str(selected_row.get("medio_dia", "")).strip().lower() == "true"
    default_comment = str(selected_row.get("comentario", "")).strip()
    default_tipo = str(selected_row.get("tipo", "vacaciones")).strip().lower()
    default_estado = str(selected_row.get("estado", "aprobado")).strip().lower()

    tipos = ["vacaciones", "ausencia", "teletrabajo"]
    estados = ["aprobado", "pendiente", "rechazado"]
    tipo_idx = tipos.index(default_tipo) if default_tipo in tipos else 0
    estado_idx = estados.index(default_estado) if default_estado in estados else 0

    with st.form("vac_absence_edit_form"):
        st.text_input("nombre_employee", value=nombre_employee, disabled=True)
        c1, c2 = st.columns(2)
        tipo = c1.selectbox("tipo", tipos, index=tipo_idx, key="vac_edit_tipo")
        estado = c2.selectbox("estado", estados, index=estado_idx, key="vac_edit_estado")
        c3, c4 = st.columns(2)
        fecha_inicio = c3.date_input("fecha_inicio", value=default_start.date(), key="vac_edit_inicio")
        fecha_fin = c4.date_input("fecha_fin", value=default_end.date(), key="vac_edit_fin")
        medio_dia = st.checkbox("medio_dia", value=default_half, key="vac_edit_medio")
        comentario = st.text_area("comentario", value=default_comment, key="vac_edit_comentario")
        b1, b2, b3 = st.columns(3)
        cancelar = b1.form_submit_button("Cancelar", key="vac_cancel_edit_btn")
        confirmar = b2.form_submit_button("Confirmar", type="primary", key="vac_confirm_edit_btn")
        eliminar = b3.form_submit_button("Eliminar", key="vac_delete_edit_btn")

    if cancelar:
        st.session_state[_VAC_OVERLAY_KEY] = False
        st.rerun()
    if confirmar:
        payload = {
            "leave_id": selected_leave_id,
            "employee_id": employee_id,
            "nombre_employee": nombre_employee,
            "tipo": tipo,
            "fecha_inicio": fecha_inicio.isoformat(),
            "fecha_fin": fecha_fin.isoformat(),
            "medio_dia": "TRUE" if medio_dia else "FALSE",
            "estado": estado,
            "comentario": comentario.strip(),
            "created_at": str(selected_row.get("created_at", "")).strip(),
        }
        saved_id = vs.upsert_absence(payload)
        st.success(f"Actualizado en Vacaciones_Ausencias ({saved_id}).")
        st.session_state["vacations_cache_version"] = st.session_state.get("vacations_cache_version", 0) + 1
        st.session_state[_VAC_OVERLAY_KEY] = False
        st.rerun()
    if eliminar:
        deleted = vs.delete_absence(selected_leave_id)
        if deleted:
            st.success("Ausencia eliminada.")
            st.session_state["vacations_cache_version"] = st.session_state.get("vacations_cache_version", 0) + 1
            st.session_state[_VAC_OVERLAY_KEY] = False
            st.rerun()
        st.error("No se pudo eliminar el registro.")


def _build_calendar_df(absences: pd.DataFrame, employees: pd.DataFrame) -> pd.DataFrame:
    if absences.empty:
        return pd.DataFrame(
            columns=[
                "leave_id",
                "employee_id",
                "nombre_employee",
                "tipo",
                "fecha_inicio",
                "fecha_fin",
                "estado",
                "comentario",
            ]
        )
    out = absences.copy()
    out["fecha_inicio"] = pd.to_datetime(out["fecha_inicio"], errors="coerce")
    out["fecha_fin"] = pd.to_datetime(out["fecha_fin"], errors="coerce")
    out = out.dropna(subset=["fecha_inicio", "fecha_fin"])
    if out.empty:
        return pd.DataFrame(
            columns=[
                "leave_id",
                "employee_id",
                "nombre_employee",
                "tipo",
                "fecha_inicio",
                "fecha_fin",
                "estado",
                "comentario",
            ]
        )
    name_by_id = {
        str(row.get("employee_id", "")): str(row.get("nombre", ""))
        for _, row in employees.iterrows()
    }
    out["nombre_employee"] = out["nombre_employee"].astype(str).str.strip()
    missing_name = out["nombre_employee"] == ""
    out.loc[missing_name, "nombre_employee"] = out.loc[missing_name, "employee_id"].astype(str).map(name_by_id).fillna(
        out.loc[missing_name, "employee_id"]
    )
    return out


def _render_year_calendar(calendar_df: pd.DataFrame, year: int, holiday_dates: set[date]) -> None:
    day_types = _expand_day_types(calendar_df, year)
    st.markdown(
        "<div style='font-size:0.9rem; margin-bottom:8px;'>"
        "<span style='display:inline-block;width:12px;height:12px;background:#fecaca;border:1px solid #fca5a5;margin-right:6px;'></span>Ausencia / vacaciones "
        "<span style='display:inline-block;width:12px;height:12px;background:#fef08a;border:1px solid #fde047;margin:0 6px 0 14px;'></span>Teletrabajo "
        "<span style='display:inline-block;width:12px;height:12px;background:#dbeafe;border:1px solid #93c5fd;margin:0 6px 0 14px;'></span>Festivo Leganes"
        "</div>",
        unsafe_allow_html=True,
    )
    months = [calendar.month_name[m] for m in range(1, 13)]
    for row_start in (1, 4, 7, 10):
        cols = st.columns(3)
        for offset, month in enumerate(range(row_start, row_start + 3)):
            with cols[offset]:
                st.markdown(f"**{months[month - 1]} {year}**")
                month_html = _month_table_html(year, month, day_types, holiday_dates)
                st.markdown(month_html, unsafe_allow_html=True)


def _expand_day_types(calendar_df: pd.DataFrame, year: int) -> dict[date, str]:
    out: dict[date, str] = {}
    if calendar_df.empty:
        return out
    for _, row in calendar_df.iterrows():
        start = row["fecha_inicio"].date()
        end = row["fecha_fin"].date()
        if end < start:
            start, end = end, start
        kind = str(row.get("tipo", "")).strip().lower()
        cursor = start
        while cursor <= end:
            if cursor.year == year:
                existing = out.get(cursor, "")
                if kind == "teletrabajo":
                    if existing == "":
                        out[cursor] = "teletrabajo"
                else:
                    out[cursor] = "ausencia"
            cursor += timedelta(days=1)
    return out


def _month_table_html(year: int, month: int, day_types: dict[date, str], holiday_dates: set[date]) -> str:
    cal = calendar.Calendar(firstweekday=0)  # Monday
    weeks = cal.monthdayscalendar(year, month)
    headers = ["L", "M", "X", "J", "V", "S", "D"]
    rows_html = [
        "<tr>" + "".join(f"<th style='padding:3px;text-align:center;font-size:11px;color:#475569;'>{h}</th>" for h in headers) + "</tr>"
    ]
    for week in weeks:
        cells = []
        for day_idx, day in enumerate(week):
            if day == 0:
                cells.append("<td style='padding:4px;border:1px solid #e2e8f0;background:#f8fafc;'>&nbsp;</td>")
                continue
            d = date(year, month, day)
            if day_types.get(d) == "ausencia":
                bg = "#fecaca"
            elif day_types.get(d) == "teletrabajo":
                bg = "#fef08a"
            elif d in holiday_dates:
                bg = "#dbeafe"
            elif day_idx >= 5:
                bg = "#f1f5f9"
            else:
                bg = "#ffffff"
            cells.append(
                f"<td style='padding:4px;border:1px solid #e2e8f0;background:{bg};text-align:center;font-size:12px;'>{day}</td>"
            )
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    return (
        "<table style='border-collapse:collapse;width:100%;margin-bottom:10px;'>"
        + "".join(rows_html)
        + "</table>"
    )


def _holiday_dates_for_year(holidays: pd.DataFrame, year: int) -> set[date]:
    if holidays.empty:
        return set()
    out: set[date] = set()
    filtered = holidays[holidays["anio"].astype(str) == str(year)]
    for raw in filtered["fecha"].astype(str).tolist():
        parsed = pd.to_datetime(raw, errors="coerce")
        if pd.isna(parsed):
            continue
        out.add(parsed.date())
    return out
