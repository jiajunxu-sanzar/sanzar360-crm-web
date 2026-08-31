"""Pagina de control de asistencia: horas trabajadas, saldo y registro de dias.

Lee y escribe en el Google Sheet del CRM (hoja ``Asistencia_Registros``) y se
apoya en ``Usuarios CRM`` para las jornadas y en las hojas de Vacaciones para
descontar ausencias. Procesar informes, anadir dias y editar asistencia son
acciones de administrador; el resto del equipo ve el dashboard en solo lectura.
"""
from __future__ import annotations

import calendar
from datetime import date, time

import pandas as pd
import streamlit as st

from app import auth
from app.cache import load_users_cached, sheets_service
from app.navigation import ROLE_ADMIN, normalize_role
from ui.components.page_header import render_page_header
from services import attendance_service as core
from services.attendance_service import AttendanceService, AttendancePerson

_DIALOG_KEY = "asistencia.dialog_open"
_DAY_PREFIX = "asis_day_"
_DAY_CONTEXT_KEY = "asistencia.day_context"
_CACHE_KEY = "asistencia_cache_version"

# El sufijo de la clave del checkbox es lo que pinta cada estado en el
# calendario: el CSS de ``ui/theme.py`` engancha con ``st-key-asis_day_<sufijo>``.
_ESTADO_SUFIJO = {
    core.DAY_RECORDED: "reg_",
    core.DAY_ABSENCE: "aus_",
    core.DAY_REMOTE: "tel_",
    core.DAY_NON_WORKING: "fes_",
    core.DAY_FREE: "",
}

_AYUDA_ESTADO = {
    core.DAY_RECORDED: "Ese dia ya tiene registro. Cambialo desde 'Editar asistencia'.",
    core.DAY_ABSENCE: "Esa persona tiene vacaciones o ausencia aprobada ese dia. Cambialo primero en Vacaciones.",
    core.DAY_REMOTE: "Teletrabajo aprobado: ya cuenta como jornada completa. Si registras un horario, manda el horario.",
    core.DAY_NON_WORKING: "Fin de semana o festivo: no es un dia exigido, pero puedes registrarlo.",
}


def can_manage_asistencia(role: str) -> bool:
    """Solo administradores pueden procesar informes, anadir o editar dias."""
    return normalize_role(role) == ROLE_ADMIN


def _authenticated_user_id() -> str:
    return auth.get_authenticated_user_id()


def _authenticated_user_role(users: list[object]) -> str:
    uid = _authenticated_user_id()
    for user in users:
        if str(getattr(user, "employee_id", "")) == uid:
            return str(getattr(user, "role", "") or "")
    return ""


@st.cache_resource
def attendance_service() -> AttendanceService:
    return AttendanceService(sheets_service())


@st.cache_data(ttl=120, show_spinner=False)
def load_attendance_bundle(_version: int = 0) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    svc = attendance_service()
    return svc.records(), svc.absences(), svc.holidays()


def _bump_cache() -> None:
    st.session_state[_CACHE_KEY] = st.session_state.get(_CACHE_KEY, 0) + 1


def _close_dialog() -> None:
    st.session_state[_DIALOG_KEY] = ""


def _dismiss_dialog() -> None:
    """Cierre con la X: sin esto el dialogo se reabriria en el siguiente rerun."""
    _close_dialog()
    _clear_day_checkboxes()
    st.session_state.pop(_DAY_CONTEXT_KEY, None)


def _clear_day_checkboxes() -> None:
    for key in [k for k in st.session_state.keys() if str(k).startswith(_DAY_PREFIX)]:
        st.session_state.pop(key, None)


# ------------------------------------------------------------------ render


def render(_: pd.DataFrame) -> None:
    render_page_header("Asistencia")

    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    people = core.people_from_users(users)
    is_admin = can_manage_asistencia(_authenticated_user_role(users))
    if not is_admin:
        st.session_state[_DIALOG_KEY] = ""

    records, absences, holidays = load_attendance_bundle(st.session_state.get(_CACHE_KEY, 0))

    _render_action_bar(is_admin)
    _render_open_dialog(people, records, absences, holidays, is_admin)

    sueltos = core.unmatched_absence_names(absences, people)
    if sueltos:
        st.warning(
            "Estas personas tienen ausencias en Vacaciones pero no cuadran con ningun "
            "usuario de `Usuarios CRM`, asi que sus vacaciones no se estan descontando: "
            + ", ".join(sueltos)
            + ". Revisa que el `employee_id` sea el mismo en las dos hojas."
        )

    anio, mes_num, persona = _render_filters(people, records)
    resumen = core.year_summary(people, anio, records, holidays, absences)

    if resumen.empty:
        st.info(
            "Todavia no hay nada que mostrar. Asigna la jornada de cada persona en la hoja "
            "`Usuarios CRM` y procesa el primer informe de fichajes."
        )
    elif persona:
        _render_person_dashboard(resumen, records, anio, mes_num, persona)
    else:
        _render_team_dashboard(resumen, anio, mes_num)

    _render_jornadas(people, anio, mes_num)


def _render_action_bar(is_admin: bool) -> None:
    info_col, proc_col, add_col, edit_col, _ = st.columns([1, 3, 3, 3, 6])
    with info_col:
        if st.button("ⓘ", key="btn_neutral_asis_info", help="Como se cuentan las horas", width="stretch"):
            st.session_state[_DIALOG_KEY] = "info"
    disabled_help = None if is_admin else "Solo el administrador puede modificar la asistencia."
    with proc_col:
        if st.button(
            "Procesar informes",
            key="btn_save_asis_procesar",
            disabled=not is_admin,
            help=disabled_help,
            width="stretch",
        ):
            st.session_state[_DIALOG_KEY] = "procesar"
    with add_col:
        if st.button(
            "Anadir dias",
            key="btn_save_asis_anadir",
            disabled=not is_admin,
            help=disabled_help,
            width="stretch",
        ):
            _clear_day_checkboxes()
            st.session_state[_DIALOG_KEY] = "anadir"
    with edit_col:
        if st.button(
            "Editar asistencia",
            key="btn_neutral_asis_editar",
            disabled=not is_admin,
            help=disabled_help,
            width="stretch",
        ):
            st.session_state[_DIALOG_KEY] = "editar"
    if not is_admin:
        st.caption("Vista de solo lectura: puedes consultar a cualquiera, pero no modificar registros.")


def _render_open_dialog(
    people: list[AttendancePerson],
    records: pd.DataFrame,
    absences: pd.DataFrame,
    holidays: pd.DataFrame,
    is_admin: bool,
) -> None:
    abierto = str(st.session_state.get(_DIALOG_KEY, "") or "")
    if abierto == "info":
        _info_dialog()
    elif abierto and is_admin:
        if abierto == "procesar":
            _procesar_dialog(people, holidays)
        elif abierto == "anadir":
            _anadir_dias_dialog(people, records, holidays, absences)
        elif abierto == "editar":
            _editar_dialog(people, records, absences, holidays)


# ----------------------------------------------------------------- filtros


def _years_available(records: pd.DataFrame) -> list[int]:
    hoy = date.today().year
    anios = {hoy}
    if records is not None and not records.empty:
        for raw in records["anio_mes"].astype(str).tolist():
            trozo = raw.split("-")[0].strip()
            if trozo.isdigit():
                anios.add(int(trozo))
    return sorted(anios, reverse=True)


def _render_filters(
    people: list[AttendancePerson], records: pd.DataFrame
) -> tuple[int, int | None, str]:
    anios = _years_available(records)
    col_anio, col_mes, col_persona = st.columns([1, 2, 3])
    with col_anio:
        anio = int(st.selectbox("Ano", anios, index=0, key="asis_filtro_anio"))
    meses = core.months_of_year(anio)
    with col_mes:
        opciones_mes = ["Todos"] + [core.MESES_ES[m] for m in meses]
        indice_defecto = len(opciones_mes) - 1 if meses else 0
        mes_label = st.selectbox("Mes", opciones_mes, index=indice_defecto, key="asis_filtro_mes")
    mes_num = None if mes_label == "Todos" else core.MESES_ES.index(mes_label)

    nombres = sorted({p.nombre for p in people})
    yo = next((p.nombre for p in people if p.employee_id == _authenticated_user_id()), "")
    opciones_persona = ["Todo el equipo"] + nombres
    indice_persona = opciones_persona.index(yo) if yo in opciones_persona else 0
    with col_persona:
        persona_label = st.selectbox(
            "Persona", opciones_persona, index=indice_persona, key="asis_filtro_persona"
        )
    persona = "" if persona_label == "Todo el equipo" else persona_label
    return anio, mes_num, persona


# -------------------------------------------------------------- dashboards


_COLUMNAS_VISIBLES = {
    "mes": "Mes",
    "nombre": "Nombre",
    "jornada": "Jornada",
    "dias_exigidos": "Dias exigidos",
    "dias_registrados": "Dias con registro",
    "horas_exigidas": "Horas exigidas",
    "horas_computadas": "Horas hechas",
    "saldo": "Saldo mes",
    "saldo_acumulado": "Saldo acumulado",
    "estado": "Estado",
}


def _estado_mes(fila: pd.Series) -> str:
    if bool(fila.get("sin_datos", False)):
        return "sin datos"
    if bool(fila.get("mes_en_curso", False)):
        return "en curso"
    return "cerrado"


def _render_person_dashboard(
    resumen: pd.DataFrame,
    records: pd.DataFrame,
    anio: int,
    mes_num: int | None,
    persona: str,
) -> None:
    del_persona = resumen[resumen["nombre"] == persona].sort_values("mes_num")
    if del_persona.empty:
        st.warning(
            f"{persona} no tiene jornada asignada en `Usuarios CRM`, asi que no se pueden "
            "calcular sus horas."
        )
        return

    con_datos = del_persona[~del_persona["sin_datos"].astype(bool)]

    if mes_num is not None:
        fila = del_persona[del_persona["mes_num"] == mes_num]
        if fila.empty:
            st.info("Ese mes todavia no tiene datos.")
        else:
            _render_month_metrics(fila.iloc[0])
    else:
        ultimo = del_persona.iloc[-1]
        total_exigidas = round(float(con_datos["horas_exigidas"].sum()), 2)
        total_hechas = round(float(con_datos["horas_computadas"].sum()), 2)
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas exigidas del ano", f"{total_exigidas:g} h")
        c2.metric("Horas hechas", f"{total_hechas:g} h")
        c3.metric("Saldo acumulado", f"{float(ultimo['saldo_acumulado']):+g} h")

    st.subheader("Mes a mes")
    tabla = del_persona.copy()
    tabla["estado"] = tabla.apply(_estado_mes, axis=1)
    tabla = tabla[
        ["mes", "jornada", "dias_exigidos", "dias_registrados", "horas_exigidas",
         "horas_computadas", "saldo", "saldo_acumulado", "estado"]
    ].rename(columns=_COLUMNAS_VISIBLES)
    col_tabla, col_grafico = st.columns([3, 2])
    with col_tabla:
        st.dataframe(tabla, width="stretch", hide_index=True)
    with col_grafico:
        st.bar_chart(con_datos.set_index("mes")[["saldo"]], height=300)

    de_mas = con_datos[con_datos["saldo"] > 0]["mes"].tolist()
    de_menos = con_datos[con_datos["saldo"] < 0]
    if de_mas:
        st.caption("Meses por encima de lo exigido: " + ", ".join(de_mas))
    if not de_menos.empty:
        faltan = ", ".join(
            f"{row['mes']} ({abs(float(row['saldo'])):g} h)" for _, row in de_menos.iterrows()
        )
        st.caption("Meses por debajo: " + faltan)
    vacios = del_persona[del_persona["sin_datos"].astype(bool)]["mes"].tolist()
    if vacios:
        st.caption(
            "Sin ningun registro (no suman al acumulado hasta que se procese el informe): "
            + ", ".join(vacios)
        )

    st.divider()
    _render_detalle(records, anio, mes_num, del_persona.iloc[0]["employee_id"])


def _render_month_metrics(fila: pd.Series) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Horas exigidas", f"{float(fila['horas_exigidas']):g} h")
    c2.metric("Horas hechas", f"{float(fila['horas_computadas']):g} h")
    saldo = float(fila["saldo"])
    c3.metric(
        "Saldo del mes",
        f"{saldo:+g} h",
        help="Positivo: horas de mas. Negativo: horas que faltan para cumplir.",
    )
    c4.metric("Saldo acumulado del ano", f"{float(fila['saldo_acumulado']):+g} h")
    if bool(fila.get("sin_datos", False)):
        st.info(
            "Ese mes no tiene ningun registro, asi que no cuenta en el saldo acumulado. "
            "Procesa su informe de fichajes para que entre."
        )
    detalle = [f"Jornada de {float(fila['jornada']):g} h", f"{int(fila['dias_exigidos'])} dias exigidos"]
    if bool(fila.get("mes_en_curso", False)):
        detalle.append("mes en curso: solo se exigen los dias ya pasados")
    if int(fila["dias_ausencia"]):
        detalle.append(f"{int(fila['dias_ausencia'])} dias de vacaciones o ausencia descontados")
    if int(fila["dias_teletrabajo_auto"]):
        detalle.append(f"{int(fila['dias_teletrabajo_auto'])} dias de teletrabajo dados por cumplidos")
    st.caption(". ".join(detalle) + ".")


def _render_team_dashboard(resumen: pd.DataFrame, anio: int, mes_num: int | None) -> None:
    if mes_num is not None:
        vista = resumen[resumen["mes_num"] == mes_num].copy()
        if not vista.empty:
            vista["estado"] = vista.apply(_estado_mes, axis=1)
        titulo = f"Resumen de {core.MESES_ES[mes_num]} {anio}"
    else:
        # La jornada puede cambiar de un mes a otro, asi que el resumen anual
        # se agrupa solo por persona y se muestra la jornada del ultimo mes.
        ultimo_mes = resumen.groupby("employee_id")["mes_num"].transform("max")
        ultimos = resumen[resumen["mes_num"] == ultimo_mes][
            ["employee_id", "jornada", "saldo_acumulado"]
        ]
        # Los meses sin ningun registro no aportan nada a los totales, igual
        # que no aportan al acumulado.
        aportan = resumen.copy()
        vacios = aportan["sin_datos"].astype(bool)
        for columna in ("dias_exigidos", "dias_registrados", "horas_exigidas", "horas_computadas", "saldo"):
            aportan.loc[vacios, columna] = 0
        vista = (
            aportan.groupby(["employee_id", "nombre"], as_index=False)
            .agg(
                dias_exigidos=("dias_exigidos", "sum"),
                dias_registrados=("dias_registrados", "sum"),
                horas_exigidas=("horas_exigidas", "sum"),
                horas_computadas=("horas_computadas", "sum"),
                saldo=("saldo", "sum"),
            )
            .merge(ultimos, on="employee_id", how="left")
        )
        titulo = f"Resumen del ano {anio}"

    if vista.empty:
        st.info("Ese mes todavia no tiene datos.")
        return

    vista = vista.sort_values("nombre")
    for columna in ("horas_exigidas", "horas_computadas", "saldo", "saldo_acumulado"):
        if columna in vista.columns:
            vista[columna] = vista[columna].astype(float).round(2)

    st.subheader(titulo)
    col_tabla, col_grafico = st.columns([3, 2])
    with col_tabla:
        columnas = [c for c in _COLUMNAS_VISIBLES if c in vista.columns and c != "mes"]
        st.dataframe(
            vista[columnas].rename(columns=_COLUMNAS_VISIBLES),
            width="stretch",
            hide_index=True,
        )
    with col_grafico:
        st.bar_chart(vista.set_index("nombre")[["saldo"]], height=320)
    st.caption(
        "Saldo positivo: horas de mas. Saldo negativo: horas que faltan para cumplir. "
        "Del mes en curso solo se exigen los dias que ya han pasado, y los meses sin "
        "ningun registro no cuentan hasta que se procese su informe."
    )


def _render_detalle(records: pd.DataFrame, anio: int, mes_num: int | None, employee_id: str) -> None:
    st.subheader("Detalle dia a dia")
    if records is None or records.empty:
        st.write("Sin dias registrados.")
        return
    detalle = records[records["employee_id"].astype(str).str.strip() == str(employee_id)].copy()
    if mes_num is not None:
        detalle = detalle[detalle["anio_mes"] == f"{anio}-{mes_num:02d}"]
    else:
        detalle = detalle[detalle["anio_mes"].astype(str).str.startswith(f"{anio}-")]
    if detalle.empty:
        st.write("Sin dias registrados en ese periodo.")
        return
    detalle = core.sort_records(detalle)
    st.dataframe(
        detalle[["fecha", "entrada", "salida", "horas", "origen", "nota"]].rename(
            columns={
                "fecha": "Fecha",
                "entrada": "Entrada",
                "salida": "Salida",
                "horas": "Horas brutas",
                "origen": "Origen",
                "nota": "Nota",
            }
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Horas brutas: de la entrada a la salida. La media hora de comida se descuenta al sumar el mes."
    )


def _render_jornadas(people: list[AttendancePerson], anio: int, mes_num: int | None) -> None:
    st.divider()
    with st.expander("Jornadas actuales"):
        referencia = mes_num or date.today().month
        filas = []
        for person in people:
            jornada = person.jornada_for(anio, referencia)
            filas.append(
                {
                    "Nombre": person.nombre,
                    "Nombre en la maquina de fichar": person.nombre_fichaje or "sin asignar",
                    "Jornada habitual": person.jornada or "sin asignar",
                    "Excepciones por mes": person.jornada_excepciones or "",
                    f"Jornada en {core.MESES_ES[referencia]}": "sin jornada" if jornada is None else f"{jornada:g} h",
                }
            )
        st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)
        st.caption(
            "Las jornadas se editan en la hoja `Usuarios CRM`: columnas `jornada` "
            "(horas al dia) y `jornada_excepciones` (por ejemplo `2026-07:8, 2026-08:8`). "
            "La columna `nombre_fichaje` enlaza a cada persona con el nombre que usa la "
            "maquina de fichar."
        )


# ----------------------------------------------------------------- dialogos


@st.dialog("Como se cuentan las horas", on_dismiss=_dismiss_dialog)
def _info_dialog() -> None:
    st.markdown(
        """
**Dias con fichaje.** Se cuenta de la primera marca del dia a la ultima.

**Dias con un solo fichaje.** Se sabe que la persona vino pero no cuando salio,
asi que el dia se da por jornada completa (aparece como origen `estimado`).

**Comida.** A las jornadas de 8 h o mas se les restan 30 minutos por cada dia
con registro. Por eso un dia completo se guarda con 8,5 h brutas: al descontar
la comida queda en las 8 h de jornada.

**Dias sin ningun fichaje.** No se registran. El dia sigue contando como
exigido, asi que aparece como horas que faltan.

**Horas exigidas del mes.** Jornada de la persona por los dias laborables del
mes (lunes a viernes, sin los festivos de la hoja `Vacaciones_Festivos`),
descontando los dias de vacaciones y ausencias aprobadas en Vacaciones. Del mes
en curso solo se exigen los dias que ya han pasado.

**Teletrabajo.** Los dias de teletrabajo aprobado se dan por cumplidos con la
jornada completa aunque no haya fichaje. Si ademas hay registro de ese dia,
manda el registro.

**Saldo.** Horas hechas menos horas exigidas. El acumulado suma los saldos de
los meses del ano, de enero al mes en curso. Los meses que no tienen ningun
registro se marcan como "sin datos" y no suman: un mes vacio casi siempre
significa que falta subir su informe, no que no se trabajara. En cuanto se
procesa, entra solo.

**Dias sueltos anadidos a mano.** Se marcan como origen `manual` y no se pierden
al reprocesar un informe: al volver a subir un mes solo se reescriben los dias
que vienen en el informe. En el calendario de alta no se pueden marcar los dias
que ya tienen registro ni los de vacaciones o ausencia aprobada, para no tener
un horario y una ausencia diciendo cosas contrarias del mismo dia.
        """.strip()
    )
    if st.button("Cerrar", key="btn_neutral_asis_info_close"):
        _close_dialog()
        st.rerun()


@st.dialog("Procesar informes de fichaje", width="large", on_dismiss=_dismiss_dialog)
def _procesar_dialog(people: list[AttendancePerson], holidays: pd.DataFrame) -> None:
    st.caption(
        "Sube uno o varios informes (.xls o .xlsx) con la hoja "
        "'Registros de asistencia'. Se leen, se vuelcan al Google Sheet y se "
        "descartan: no se guarda ninguna copia."
    )
    archivos = st.file_uploader(
        "Informes de asistencia",
        type=["xls", "xlsx"],
        accept_multiple_files=True,
        key="asis_uploader",
    )

    col_cancelar, col_procesar = st.columns(2)
    if col_cancelar.button("Cancelar", key="btn_neutral_asis_proc_cancel", width="stretch"):
        _close_dialog()
        st.rerun()
    procesar = col_procesar.button(
        "Procesar",
        key="btn_save_asis_proc_run",
        type="primary",
        disabled=not archivos,
        width="stretch",
    )
    if not procesar:
        return

    svc = attendance_service()
    registros: list[dict[str, str]] = []
    resumen: list[dict[str, object]] = []
    sin_usuario: set[str] = set()
    sin_jornada: set[str] = set()

    with st.spinner("Leyendo informes…"):
        for archivo in archivos:
            try:
                informe = core.parse_attendance_report(archivo.getvalue(), archivo.name)
            except ValueError as exc:
                st.error(f"{archivo.name}: {exc}")
                continue
            festivos = core.holiday_dates_for_year(holidays, informe.anio)
            nuevos, faltan_usuario, faltan_jornada = core.records_from_report(
                informe, people, festivos
            )
            registros.extend(nuevos)
            sin_usuario.update(faltan_usuario)
            sin_jornada.update(faltan_jornada)
            resumen.append(
                {
                    "Informe": archivo.name,
                    "Mes": informe.mes_label,
                    "Personas": len({r["employee_id"] for r in nuevos}),
                    "Dias": len(nuevos),
                }
            )

    if registros:
        with st.spinner("Guardando en el Google Sheet…"):
            svc.save_records(registros)
        _bump_cache()
        st.success(f"Guardados {len(registros)} dias.")
        st.dataframe(pd.DataFrame(resumen), width="stretch", hide_index=True)
    elif not sin_usuario and not sin_jornada:
        st.warning("Los informes no contenian ningun dia con fichajes.")

    if sin_usuario:
        st.warning(
            "Estos nombres del informe no estan enlazados con ningun usuario: "
            + ", ".join(sorted(sin_usuario))
            + ". Rellena su `nombre_fichaje` en la hoja `Usuarios CRM` y vuelve a procesar."
        )
    if sin_jornada:
        st.warning(
            "Estos usuarios no tienen jornada asignada y se han quedado fuera: "
            + ", ".join(sorted(sin_jornada))
            + ". Rellena su columna `jornada` en la hoja `Usuarios CRM`."
        )


@st.dialog("Anadir dias a mano", width="large", on_dismiss=_dismiss_dialog)
def _anadir_dias_dialog(
    people: list[AttendancePerson],
    records: pd.DataFrame,
    holidays: pd.DataFrame,
    absences: pd.DataFrame,
) -> None:
    st.caption(
        "Para dias sin fichaje: teletrabajo, visita a cliente, feria. Marca en el "
        "calendario todos los dias que llevan la misma entrada y salida."
    )
    if not people:
        st.error("No hay usuarios cargados.")
        return

    nombres = sorted({p.nombre for p in people})
    persona_nombre = st.selectbox("Persona", nombres, key="asis_add_persona")
    person = next(p for p in people if p.nombre == persona_nombre)

    hoy = date.today()
    col_anio, col_mes = st.columns(2)
    anio = int(col_anio.number_input("Ano", min_value=2020, max_value=2100, value=hoy.year, step=1, key="asis_add_anio"))
    mes_label = col_mes.selectbox(
        "Mes", core.MESES_ES[1:], index=hoy.month - 1, key="asis_add_mes"
    )
    mes = core.MESES_ES.index(mes_label)

    jornada = person.jornada_for(anio, mes)
    if jornada is None:
        st.error(
            f"{person.nombre} no tiene jornada para {mes_label} {anio}. Rellena su columna "
            "`jornada` en la hoja `Usuarios CRM`."
        )
        return

    contexto = f"{person.employee_id}|{anio}-{mes:02d}"
    if st.session_state.get(_DAY_CONTEXT_KEY) != contexto:
        _clear_day_checkboxes()
        st.session_state[_DAY_CONTEXT_KEY] = contexto

    tipo = st.radio(
        "Horario",
        [f"Jornada completa ({jornada:g} h)", "Entrada y salida concretas"],
        key="asis_add_tipo",
        horizontal=True,
    )
    entrada = salida = None
    if tipo == "Entrada y salida concretas":
        col_entrada, col_salida = st.columns(2)
        entrada = col_entrada.time_input("Entrada", value=time(9, 0), key="asis_add_entrada").strftime("%H:%M")
        salida = col_salida.time_input("Salida", value=time(17, 0), key="asis_add_salida").strftime("%H:%M")
    nota = st.text_input("Nota", value="Teletrabajo", key="asis_add_nota")

    ocupados = core.recorded_dates(records, person.employee_id)
    festivos = core.holiday_dates_for_year(holidays, anio)
    ausencias = core.absence_days_by_employee(absences, anio, festivos).get(
        person.employee_id, {}
    )
    seleccionados = _render_day_picker(anio, mes, ocupados, festivos, ausencias)

    if seleccionados:
        st.success(
            f"{len(seleccionados)} dia(s) seleccionados: "
            + ", ".join(d.strftime("%d/%m") for d in seleccionados)
        )
    else:
        st.caption(
            "Los dias bloqueados o ya tienen registro (cambialos desde 'Editar asistencia') "
            "o son vacaciones o ausencia aprobada de esa persona en Vacaciones."
        )

    col_cancelar, col_guardar = st.columns(2)
    if col_cancelar.button("Cancelar", key="btn_neutral_asis_add_cancel", width="stretch"):
        _clear_day_checkboxes()
        _close_dialog()
        st.rerun()
    if col_guardar.button(
        "Guardar dias",
        key="btn_save_asis_add",
        type="primary",
        disabled=not seleccionados,
        width="stretch",
    ):
        nuevos = [
            core.manual_record(person, dia, jornada, entrada=entrada, salida=salida, nota=nota)
            for dia in seleccionados
        ]
        attendance_service().save_records(nuevos)
        _bump_cache()
        _clear_day_checkboxes()
        st.session_state.pop(_DAY_CONTEXT_KEY, None)
        _close_dialog()
        st.rerun()


def _render_day_picker(
    anio: int,
    mes: int,
    ocupados: set[date],
    festivos: set[date],
    ausencias: dict[date, str],
) -> list[date]:
    """Calendario del mes con una casilla por dia.

    Se bloquean los dias que ya tienen registro y los de vacaciones o ausencia
    aprobada: meter entrada y salida en un dia de vacaciones seria decir dos
    cosas contrarias a la vez.
    """
    st.markdown(
        "<div class='sanzar-legend-row'>"
        "<span class='sanzar-legend-item sanzar-legend-ocupado'>Ya tiene registro</span>"
        "<span class='sanzar-legend-item sanzar-legend-ausencia'>Vacaciones o ausencia</span>"
        "<span class='sanzar-legend-item sanzar-legend-teletrabajo'>Teletrabajo aprobado</span>"
        "<span class='sanzar-legend-item sanzar-legend-festivo'>Festivo o fin de semana</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    cabeceras = ["L", "M", "X", "J", "V", "S", "D"]
    columnas = st.columns(7)
    for col, titulo in zip(columnas, cabeceras):
        col.markdown(f"<p class='asis-cal-head'>{titulo}</p>", unsafe_allow_html=True)

    seleccionados: list[date] = []
    for semana in calendar.Calendar(firstweekday=0).monthdayscalendar(anio, mes):
        columnas = st.columns(7)
        for col, dia in zip(columnas, semana):
            if dia == 0:
                col.markdown("<p class='asis-cal-empty'>&nbsp;</p>", unsafe_allow_html=True)
                continue
            actual = date(anio, mes, dia)
            estado = core.day_picker_state(actual, ocupados, festivos, ausencias)
            marcado = col.checkbox(
                f"{dia}",
                key=f"{_DAY_PREFIX}{_ESTADO_SUFIJO[estado]}{anio}{mes:02d}{dia:02d}",
                disabled=not core.is_day_selectable(estado),
                help=_AYUDA_ESTADO.get(estado),
            )
            if marcado and core.is_day_selectable(estado):
                seleccionados.append(actual)
    return seleccionados


@st.dialog("Editar asistencia", on_dismiss=_dismiss_dialog)
def _editar_dialog(
    people: list[AttendancePerson],
    records: pd.DataFrame,
    absences: pd.DataFrame,
    holidays: pd.DataFrame,
) -> None:
    st.caption("Corrige la entrada y la salida de un dia concreto, o borralo.")
    if not people:
        st.error("No hay usuarios cargados.")
        return

    nombres = sorted({p.nombre for p in people})
    persona_nombre = st.selectbox("Persona", nombres, key="asis_edit_persona")
    person = next(p for p in people if p.nombre == persona_nombre)
    fecha = st.date_input("Dia", value=date.today(), key="asis_edit_fecha", format="DD/MM/YYYY")

    registro_id = core.record_id(person.employee_id, fecha)
    existente = pd.DataFrame()
    if records is not None and not records.empty:
        existente = records[records["registro_id"].astype(str).str.strip() == registro_id]

    if existente.empty:
        st.info(
            f"{person.nombre} no tiene registro el {fecha.strftime('%d/%m/%Y')}. "
            "Usa 'Anadir dias' para darlo de alta."
        )
        if st.button("Cerrar", key="btn_neutral_asis_edit_close"):
            _close_dialog()
            st.rerun()
        return

    festivos = core.holiday_dates_for_year(holidays, fecha.year)
    ausencias = core.absence_days_by_employee(absences, fecha.year, festivos).get(
        person.employee_id, {}
    )
    if ausencias.get(fecha) == "ausencia":
        st.warning(
            "Ese dia consta como vacaciones o ausencia aprobada en Vacaciones. Si el "
            "horario es correcto, quita la ausencia; si no, elimina el registro."
        )

    fila = existente.iloc[0]
    st.caption(
        f"Origen actual: {fila.get('origen', '')}. Horas brutas guardadas: {fila.get('horas', '')} h."
    )
    col_entrada, col_salida = st.columns(2)
    entrada = col_entrada.text_input("Entrada (HH:MM)", value=str(fila.get("entrada", "")), key="asis_edit_entrada")
    salida = col_salida.text_input("Salida (HH:MM)", value=str(fila.get("salida", "")), key="asis_edit_salida")
    nota = st.text_input("Nota", value=str(fila.get("nota", "")), key="asis_edit_nota")

    col_cancelar, col_guardar, col_borrar = st.columns(3)
    if col_cancelar.button("Cancelar", key="btn_neutral_asis_edit_cancel", width="stretch"):
        _close_dialog()
        st.rerun()
    if col_guardar.button("Guardar", key="btn_save_asis_edit", type="primary", width="stretch"):
        try:
            horas = core.hours_between(entrada.strip(), salida.strip())
        except (ValueError, IndexError):
            st.error("La entrada y la salida deben tener formato HH:MM.")
            return
        registro = core.build_record(
            person,
            fecha,
            entrada.strip(),
            salida.strip(),
            horas,
            core.ORIGEN_MANUAL,
            nota=nota,
            created_at=str(fila.get("created_at", "")),
        )
        attendance_service().save_record(registro)
        _bump_cache()
        _close_dialog()
        st.rerun()
    if col_borrar.button("Eliminar", key="btn_destruct_asis_edit", width="stretch"):
        attendance_service().delete_record(registro_id)
        _bump_cache()
        _close_dialog()
        st.rerun()
