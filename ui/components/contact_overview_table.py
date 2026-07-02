"""HTML summary table for per-contact sensor overview."""
from __future__ import annotations

import html
from datetime import date

import pandas as pd
import streamlit as st

from services.contact_sensor_overview import OVERVIEW_COLUMNS
from services.contacts_export import build_overview_pdf_bytes, build_overview_xlsx_bytes
from services.sheet_date_format import parse_sheet_date
from ui.palette import STATUS_NEUTRAL, STATUS_SUCCESS, STATUS_WARNING

_CONTACTS_VIEW_MODE_KEY = "contacts.view_mode"
_CONTACTS_VIEW_FICHA = "ficha"

_SENSOR_SEMAFORO_ACTIVE = frozenset({"verde", "amarillo"})
_OVERVIEW_DIALOG_ONLY_SENSORS_KEY = "overview_dialog_only_with_sensors"

_OVERVIEW_TABLE_HEADER_HTML = (
    "<div class='sanzar-contact-row sanzar-contact-header sanzar-overview-header'>"
    "<span>Contacto</span><span>Sensores</span><span>Último contacto</span>"
    "<span>Próxima acción</span><span>Incidencias</span>"
    "</div>"
)


def semaforo_row_modifier(semaforo: str) -> str:
    sem = (semaforo or "").strip().lower()
    if sem == "verde":
        return "sanzar-overview-row--verde"
    if sem == "amarillo":
        return "sanzar-overview-row--amarillo"
    return "sanzar-overview-row--neutral"


def overview_row_inline_style(semaforo: str) -> str:
    sem = (semaforo or "").strip().lower()
    if sem == "verde":
        return STATUS_SUCCESS.css()
    if sem == "amarillo":
        return STATUS_WARNING.css()
    return STATUS_NEUTRAL.css()


def format_sensors_cell(num_sensores: object, sensor_sns: object) -> str:
    sns = str(sensor_sns or "").strip()
    if sns:
        return sns
    return "—"


def format_ultimo_contacto_cell(
    fecha: object,
    canal: object,
    detalle: object = "",
) -> str:
    detail = str(detalle or "").strip()
    if detail:
        return detail
    f = str(fecha or "").strip()
    c = str(canal or "").strip()
    if f and c:
        return f"{f} · {c}"
    return f or c or "—"


def format_proxima_accion_cell(fecha: object, detalle: object) -> str:
    f = str(fecha or "").strip()
    d = str(detalle or "").strip()
    if f and d:
        return f"{f} — {d}"
    return f or d or "—"


def format_incidencias_cell(count: object, detalle: object = "") -> str:
    text = str(detalle or "").strip()
    if text:
        return text
    try:
        n = int(count)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return "—"
    label = "abierta" if n == 1 else "abiertas"
    return f"{n} {label}"


def _proxima_sort_key(row: dict[str, object]) -> tuple[date, str]:
    parsed = parse_sheet_date(str(row.get("proxima_accion_fecha", "") or ""))
    sort_date = parsed or date.max
    cid = str(row.get("contact_id", "") or "").strip()
    return sort_date, cid


def sort_overview_by_proxima_accion(overview_df: pd.DataFrame) -> pd.DataFrame:
    if overview_df.empty:
        return overview_df.copy()
    rows = overview_df.fillna("").to_dict("records")
    sorted_rows = sorted(rows, key=_proxima_sort_key)
    return pd.DataFrame(sorted_rows, columns=list(overview_df.columns))


def filter_overview_by_contact_ids(
    overview: pd.DataFrame,
    contact_ids: list[str],
) -> pd.DataFrame:
    if overview.empty or not contact_ids:
        return overview.iloc[0:0].copy() if not overview.empty else pd.DataFrame(columns=OVERVIEW_COLUMNS)
    wanted = {str(cid).strip() for cid in contact_ids if str(cid).strip()}
    if not wanted or "contact_id" not in overview.columns:
        return overview.iloc[0:0].copy()
    col = overview["contact_id"].fillna("").astype(str).str.strip()
    return overview[col.isin(wanted)].copy()


def filter_overview_with_sensors_only(overview_df: pd.DataFrame) -> pd.DataFrame:
    if overview_df.empty or "semaforo" not in overview_df.columns:
        return overview_df.iloc[0:0].copy() if not overview_df.empty else overview_df
    sem = overview_df["semaforo"].fillna("").astype(str).str.strip().str.lower()
    return overview_df[sem.isin(_SENSOR_SEMAFORO_ACTIVE)].copy()


def _cell_html(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def build_overview_row_html(row: dict[str, object]) -> str:
    semaforo = str(row.get("semaforo", "") or "")
    modifier = semaforo_row_modifier(semaforo)
    inline_style = overview_row_inline_style(semaforo)
    nombre = html.escape(str(row.get("nombre", "") or "Sin nombre"))
    sensors = _cell_html(format_sensors_cell(row.get("num_sensores"), row.get("sensor_sns")))
    ultimo = _cell_html(
        format_ultimo_contacto_cell(
            row.get("ultimo_contacto"),
            row.get("ultimo_contacto_canal"),
            row.get("ultimo_contacto_detalle"),
        )
    )
    proxima = _cell_html(
        format_proxima_accion_cell(row.get("proxima_accion_fecha"), row.get("proxima_accion_detalle"))
    )
    incidencias = _cell_html(
        format_incidencias_cell(row.get("incidencias_abiertas"), row.get("incidencias_detalle"))
    )
    return (
        f"<div class='sanzar-contact-row sanzar-overview-row {modifier}' style='{inline_style}'>"
        f"<span class='sanzar-contact-cell'>{nombre}</span>"
        f"<span class='sanzar-contact-cell'>{sensors}</span>"
        f"<span class='sanzar-contact-cell'>{ultimo}</span>"
        f"<span class='sanzar-contact-cell'>{proxima}</span>"
        f"<span class='sanzar-contact-cell'>{incidencias}</span>"
        "</div>"
    )


def build_overview_table_html(overview_df: pd.DataFrame, *, expanded: bool = False) -> str:
    expanded_class = " sanzar-overview-table--expanded" if expanded else ""
    sorted_df = sort_overview_by_proxima_accion(overview_df)
    rows_html = "".join(
        build_overview_row_html(row)
        for row in sorted_df.fillna("").to_dict("records")
        if str(row.get("contact_id", "") or "").strip()
    )
    return (
        f"<div class='sanzar-contact-table sanzar-overview-table{expanded_class}'>"
        f"{_OVERVIEW_TABLE_HEADER_HTML}{rows_html}</div>"
    )


def render_contact_overview_dialog_content(overview_df: pd.DataFrame) -> None:
    if overview_df.empty:
        st.info("No hay contactos en el resumen.")
        return

    only_sensors = st.toggle("Con sensores", key=_OVERVIEW_DIALOG_ONLY_SENSORS_KEY)
    visible_df = filter_overview_with_sensors_only(overview_df) if only_sensors else overview_df
    if visible_df.empty:
        st.info(
            "No hay contactos con sensores en el resumen."
            if only_sensors
            else "No hay contactos en el resumen."
        )
        return

    sorted_df = sort_overview_by_proxima_accion(visible_df)
    st.caption(f"{len(sorted_df)} contactos (filtros aplicados)")

    xlsx_bytes, xlsx_name = build_overview_xlsx_bytes(visible_df)
    pdf_bytes, pdf_name = build_overview_pdf_bytes(visible_df)
    export_col1, export_col2 = st.columns(2, gap="small")
    export_col1.download_button(
        "Exportar Excel",
        data=xlsx_bytes,
        file_name=xlsx_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="contacts_export_overview_xlsx",
        width="stretch",
    )
    export_col2.download_button(
        "Exportar PDF",
        data=pdf_bytes,
        file_name=pdf_name,
        mime="application/pdf",
        key="contacts_export_overview_pdf",
        width="stretch",
    )

    options: list[str] = []
    id_by_label: dict[str, str] = {}
    for row in sorted_df.fillna("").to_dict("records"):
        contact_id = str(row.get("contact_id", "") or "").strip()
        if not contact_id:
            continue
        nombre = str(row.get("nombre", "") or "Sin nombre").strip() or "Sin nombre"
        label = f"{nombre} ({contact_id})"
        options.append(label)
        id_by_label[label] = contact_id

    st.markdown(build_overview_table_html(visible_df, expanded=True), unsafe_allow_html=True)

    if not options:
        return

    chosen = st.selectbox(
        "Abrir ficha de contacto",
        options=options,
        key="overview_dialog_contact_picker",
    )
    if st.button("Ver ficha", key="overview_dialog_open_ficha", width="stretch"):
        st.session_state["selected_contact_id"] = id_by_label[chosen]
        st.session_state[_CONTACTS_VIEW_MODE_KEY] = _CONTACTS_VIEW_FICHA
        st.rerun()


def render_contact_overview_table(
    overview_df: pd.DataFrame,
    on_select_key_prefix: str = "overview_ficha_",
) -> None:
    if overview_df.empty:
        st.info("No hay contactos en el resumen.")
        return

    sorted_df = sort_overview_by_proxima_accion(overview_df)
    st.markdown(
        "<div class='sanzar-contact-table sanzar-overview-table'>"
        "<div class='sanzar-contact-row sanzar-contact-header sanzar-overview-header'>"
        "<span>Contacto</span><span>Sensores</span><span>Último contacto</span>"
        "<span>Próxima acción</span><span>Incidencias</span>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    for row in sorted_df.fillna("").to_dict("records"):
        contact_id = str(row.get("contact_id", "") or "").strip()
        if not contact_id:
            continue
        row_col, btn_col = st.columns([0.9, 0.1], gap="small")
        with row_col:
            st.markdown(
                f"<div class='sanzar-contact-table sanzar-overview-table'>"
                f"{build_overview_row_html(row)}"
                "</div>",
                unsafe_allow_html=True,
            )
        with btn_col:
            if st.button("Ver ficha", key=f"{on_select_key_prefix}{contact_id}", width="stretch"):
                st.session_state["selected_contact_id"] = contact_id
                st.session_state[_CONTACTS_VIEW_MODE_KEY] = _CONTACTS_VIEW_FICHA
                st.rerun()
