"""Tablas compactas con panel de detalle para los históricos de la ficha de contacto.

Sustituyen a las tarjetas paginadas: una fila por registro en un ``st.dataframe``
seleccionable y, al marcar una fila, un panel de detalle debajo con todos los
campos (incluido el bloque técnico de sensores) y el botón Editar.
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from services.contact_proxima_index import sort_commercial_rows_by_contact_date
from services.history_service import HISTORY_SPECS, HistoryKind
from ui import modal_state
from ui.components.history import (
    clear_history_table_selection,
    history_table_search_key,
    history_table_selection_key,
)
from ui.components.tables import filter_dataframe, _selected_row_positions

_NEW_LABELS: dict[str, str] = {
    "seguimiento_comercial": "Nuevo seguimiento",
    "sensores": "Nuevo histórico",
    "campanas": "Nuevo histórico",
    "suscripciones": "Nuevo histórico",
    "incidencias": "Nuevo histórico",
}

_EMPTY_MESSAGES: dict[str, str] = {
    "seguimiento_comercial": "Aún no hay seguimiento comercial. Usa **Nuevo seguimiento** para registrar el primer contacto.",
    "sensores": "Aún no hay histórico de sensores. Usa **Nuevo histórico** para registrar el primero.",
    "campanas": "Aún no hay histórico de campañas. Usa **Nuevo histórico** para registrar el primero.",
    "suscripciones": "Aún no hay histórico de suscripciones. Usa **Nuevo histórico** para registrar el primero.",
    "incidencias": "Aún no hay histórico de incidencias. Usa **Nuevo histórico** para registrar el primero.",
}

_FIELD_LABELS: dict[str, str] = {
    "fecha_contacto": "Fecha contacto",
    "hora_contacto": "Hora",
    "persona_contacto": "Persona",
    "canal_contacto": "Canal",
    "resultado_contacto": "Resultado",
    "notas_contacto": "Notas",
    "email_clasificacion": "Clasificación email",
    "email_url": "Email (URL)",
    "origen_registro": "Origen",
    "proxima_accion_fecha": "Próxima acción (fecha)",
    "proxima_accion_persona": "Próxima acción (persona)",
    "proxima_accion_canal": "Próxima acción (canal)",
    "proxima_accion_detalle": "Próxima acción (detalle)",
    "sensor_serial_number": "Sensor (SN)",
    "cantidad_sensores": "Nº sensores",
    "tipo_operacion": "Operación",
    "estado_sensor": "Estado sensor",
    "estado_cierre_sensor": "Estado",
    "ultima_revision": "Última revisión",
    "aws_user_id": "AWS user id",
    "projectiotid": "ProjectIoT",
    "cuenta_usuario": "Cuenta usuario",
    "red_otro": "Red (otro)",
    "nombre_campana": "Campaña",
    "fecha_campana_inicio": "Inicio campaña",
    "fecha_campana_fin": "Fin campaña",
    "dias_campana": "Días",
    "tipo_suelo": "Tipo de suelo",
    "coordenadas_parcela": "Coordenadas parcela",
    "historial_sensor_id": "Histórico sensor",
    "historial_campana_id": "Histórico campaña",
    "fecha_pago": "Fecha pago",
    "cantidad_pago": "Importe",
    "metodo_pago": "Método de pago",
    "estado_suscripcion": "Estado",
    "suscripcion_fecha_inicio": "Inicio suscripción",
    "suscripcion_fecha_fin": "Fin suscripción",
    "factura_url": "Factura (URL)",
    "factura_pago_url": "Pago (URL)",
    "fecha_apertura": "Apertura",
    "fecha_cierre": "Cierre",
    "tipo_incidencia": "Tipo",
    "estado_cierre_campana": "Estado",
    "created_at": "Creado",
    "updated_at": "Actualizado",
}

_LONG_FIELDS = frozenset(
    {
        "notas_contacto",
        "detalles",
        "detalle",
        "resolucion",
        "proxima_accion_detalle",
        "projectiotid",
    }
)
_SKIP_FIELDS = frozenset({"contact_id", "nombre_cliente"})

_GREEN = "color:#15803d;font-weight:600"
_RED = "color:#b91c1c;font-weight:600"
_AMBER = "color:#b45309;font-weight:600"
_MUTED = "color:#71717a"


def _esc(x: object) -> str:
    return html.escape(str(x or "").strip())


def _fmt(row: dict[str, str], key: str) -> str:
    return str(row.get(key, "") or "").strip()


def _short(text: str, max_chars: int = 90) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _label(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return "—"
    return v.replace("_", " ").capitalize()


def _canal(canal: str) -> str:
    c = (canal or "").strip().lower()
    labels = {"email": "Email", "llamada": "Llamada", "en_persona": "En persona", "whatsapp": "WhatsApp"}
    return labels.get(c, c or "—")


def _date_range(start: str, end: str) -> str:
    s = (start or "").strip()
    e = (end or "").strip()
    if s and e:
        return f"{s} – {e}"
    return s or e or "—"


def _when(row: dict[str, str]) -> str:
    fecha = _fmt(row, "fecha_contacto")
    hora = _fmt(row, "hora_contacto")
    return f"{fecha} · {hora}" if fecha and hora else fecha or hora or "—"


def _proxima(row: dict[str, str]) -> str:
    fecha = _fmt(row, "proxima_accion_fecha")
    detalle = _short(_fmt(row, "proxima_accion_detalle"), 60)
    if fecha and detalle:
        return f"{fecha} · {detalle}"
    return fecha or detalle or "—"


def _red_display(row: dict[str, str]) -> str:
    red = _fmt(row, "red")
    if red.lower() == "otro":
        otro = _fmt(row, "red_otro")
        if otro:
            return f"otro ({otro})"
    return red or "—"


def _importe(row: dict[str, str]) -> str:
    cantidad = _fmt(row, "cantidad_pago")
    moneda = _fmt(row, "moneda")
    if cantidad and moneda:
        return f"{cantidad} {moneda}"
    return cantidad or moneda or "—"


_TABLE_COLUMNS: dict[str, list[tuple[str, object]]] = {
    "seguimiento_comercial": [
        ("Fecha", _when),
        ("Resultado", lambda r: _label(_fmt(r, "resultado_contacto"))),
        ("Persona", lambda r: _fmt(r, "persona_contacto") or "—"),
        ("Canal", lambda r: _canal(_fmt(r, "canal_contacto"))),
        ("Notas", lambda r: _short(_fmt(r, "notas_contacto"), 110) or "—"),
        ("Próxima acción", _proxima),
    ],
    "sensores": [
        ("Periodo", lambda r: _date_range(_fmt(r, "fecha_inicio"), _fmt(r, "fecha_fin"))),
        ("Estado", lambda r: _label(_fmt(r, "estado_cierre_sensor")) if _fmt(r, "estado_cierre_sensor") else "Abierto"),
        ("Sensor (SN)", lambda r: _fmt(r, "sensor_serial_number") or "—"),
        ("Operación", lambda r: _label(_fmt(r, "tipo_operacion"))),
        ("Nº", lambda r: _fmt(r, "cantidad_sensores") or "—"),
        ("Estado sensor", lambda r: _label(_fmt(r, "estado_sensor"))),
        ("Red", _red_display),
        ("Últ. revisión", lambda r: _fmt(r, "ultima_revision") or "—"),
        ("Detalles", lambda r: _short(_fmt(r, "detalles"), 80) or "—"),
    ],
    "campanas": [
        ("Campaña", lambda r: _fmt(r, "nombre_campana") or "—"),
        ("Periodo", lambda r: _date_range(_fmt(r, "fecha_campana_inicio"), _fmt(r, "fecha_campana_fin"))),
        ("Días", lambda r: _fmt(r, "dias_campana") or "—"),
        ("Cultivo", lambda r: _fmt(r, "cultivo") or "—"),
        ("Parcela", lambda r: _fmt(r, "parcela") or "—"),
        ("Estado", lambda r: _label(_fmt(r, "estado_cierre_campana")) if _fmt(r, "estado_cierre_campana") else "Abierto"),
        ("Detalles", lambda r: _short(_fmt(r, "detalles"), 80) or "—"),
    ],
    "suscripciones": [
        ("Fecha pago", lambda r: _fmt(r, "fecha_pago") or "—"),
        ("Importe", _importe),
        ("Método", lambda r: _label(_fmt(r, "metodo_pago"))),
        ("Periodo", lambda r: _date_range(_fmt(r, "suscripcion_fecha_inicio"), _fmt(r, "suscripcion_fecha_fin"))),
        ("Estado", lambda r: _label(_fmt(r, "estado_suscripcion"))),
        ("Detalles", lambda r: _short(_fmt(r, "detalles"), 80) or "—"),
    ],
    "incidencias": [
        ("Apertura", lambda r: _fmt(r, "fecha_apertura") or "—"),
        ("Cierre", lambda r: _fmt(r, "fecha_cierre") or "—"),
        ("Tipo", lambda r: _label(_fmt(r, "tipo_incidencia"))),
        ("Estado", lambda r: _label(_fmt(r, "estado"))),
        ("Prioridad", lambda r: _label(_fmt(r, "prioridad"))),
        ("Detalle", lambda r: _short(_fmt(r, "detalle"), 100) or "—"),
        ("Sensor", lambda r: _fmt(r, "sensor_serial_number") or "—"),
    ],
}


def _accent_css(kind: str, column: str, value: str) -> str:
    """Acento de color por celda: neutro en general, color solo donde informa."""
    v = (value or "").strip().lower()
    if kind == "seguimiento_comercial" and column == "Resultado":
        if v == "exitoso":
            return _GREEN
        if v == "fallido":
            return _RED
        return _MUTED
    if column == "Estado":
        if kind in ("sensores", "campanas"):
            return _GREEN if v == "abierto" else _MUTED
        if kind == "suscripciones":
            if v == "activa":
                return _GREEN
            if v == "caduca pronto":
                return _AMBER
            if v == "inactiva":
                return _RED
        if kind == "incidencias":
            if v in ("abierta", "bloqueada"):
                return _RED
            if v == "en curso":
                return _AMBER
            if v == "cerrada":
                return _GREEN
    if kind == "incidencias" and column == "Prioridad":
        if v == "alta":
            return _RED
        if v == "media":
            return _AMBER
    return ""


def _selection_fingerprint_key(contact_id: str, kind: str) -> str:
    return f"hist_table_fp_{contact_id}_{kind}"


@st.fragment
def render_history_section(
    kind: HistoryKind,
    rows: list[dict[str, str]],
    contact_id: str,
) -> None:
    """Cabecera (nuevo + buscar), tabla seleccionable y detalle de la fila marcada.

    Fragment: teclear en el buscador o marcar una fila re-ejecuta solo esta
    sección, no las cinco. «Nuevo/Editar» abre un diálogo con st.rerun() de app
    completa para que el modal se pinte a nivel de página.
    """
    cid = str(contact_id or "").strip()
    spec = HISTORY_SPECS[kind]
    if kind == "seguimiento_comercial":
        rows = sort_commercial_rows_by_contact_date(rows)

    head = st.columns([0.24, 0.76], gap="small", vertical_alignment="center")
    with head[0]:
        if st.button(
            _NEW_LABELS.get(kind, "Nuevo histórico"),
            type="primary",
            key=f"hist_new_{kind}_{cid}",
            width="stretch",
            icon=":material/add:",
        ):
            modal_state.open_add_history_modal(kind, cid)
            st.rerun()
    with head[1]:
        query = st.text_input(
            "Buscar",
            placeholder="Filtrar por cualquier campo…",
            key=history_table_search_key(cid, kind),
            label_visibility="collapsed",
            icon=":material/search:",
        )

    if not rows:
        st.info(_EMPTY_MESSAGES.get(kind, "Sin registros todavía."))
        return

    df = pd.DataFrame(rows).fillna("").astype(str)
    filtered = filter_dataframe(df, query, list(df.columns))
    if query.strip() and filtered.empty:
        st.info(f"No hay coincidencias para «{query.strip()}».")
        return

    # Si cambia el filtro, las posiciones cambian: soltar la selección previa.
    fp_key = _selection_fingerprint_key(cid, kind)
    fp = query.strip()
    if st.session_state.get(fp_key) != fp:
        st.session_state[fp_key] = fp
        clear_history_table_selection(cid, kind)

    if query.strip() and len(filtered) < len(df):
        st.caption(f"Mostrando {len(filtered)} de {len(df)} registros · marca una fila para ver el detalle")
    else:
        n = len(filtered)
        st.caption(f"{n} registro{'s' if n != 1 else ''} · marca una fila para ver el detalle")

    frows = filtered.to_dict("records")
    columns = _TABLE_COLUMNS[kind]
    disp = pd.DataFrame({name: [builder(r) for r in frows] for name, builder in columns})

    def _row_styles(row: pd.Series) -> list[str]:
        return [_accent_css(kind, str(col), str(row[col])) for col in disp.columns]

    styler = disp.style.apply(_row_styles, axis=1)
    event = st.dataframe(
        styler,
        hide_index=True,
        width="stretch",
        height=int(min(35 * len(frows) + 41, 431)),
        on_select="rerun",
        selection_mode="single-row",
        key=history_table_selection_key(cid, kind),
    )
    positions = _selected_row_positions(event)
    if not positions:
        return
    pos = int(positions[0])
    if pos < 0 or pos >= len(frows):
        return
    _render_row_detail(kind, frows[pos], cid, spec)


def _render_row_detail(kind: str, row: dict[str, str], contact_id: str, spec) -> None:
    row_id = str(row.get(spec.id_column, "") or "").strip()
    with st.container(border=True):
        top = st.columns([0.78, 0.22], gap="small", vertical_alignment="center")
        top[0].markdown(f"**Detalle del registro** · `{_esc(row_id) or '—'}`")
        if top[1].button(
            "Editar",
            key=f"hist_tbl_edit_{kind}_{contact_id}",
            width="stretch",
            icon=":material/edit:",
        ):
            if row_id:
                modal_state.open_edit_history_modal(kind, contact_id, row_id)
                st.rerun()

        short_items: list[tuple[str, str]] = []
        long_items: list[tuple[str, str]] = []
        for header in spec.headers:
            if header in _SKIP_FIELDS or header == spec.id_column:
                continue
            value = str(row.get(header, "") or "").strip()
            if not value:
                continue
            label = _FIELD_LABELS.get(header, header.replace("_", " ").capitalize())
            if header in _LONG_FIELDS:
                long_items.append((label, value))
            else:
                short_items.append((label, value))

        if short_items:
            cols = st.columns(3, gap="small")
            for idx, (label, value) in enumerate(short_items):
                cols[idx % 3].markdown(
                    f"<div class='sanzar-detail-field'>"
                    f"<span class='sanzar-detail-label'>{_esc(label)}</span><br>"
                    f"<span class='sanzar-detail-value'>{_esc(value)}</span></div>",
                    unsafe_allow_html=True,
                )
        for label, value in long_items:
            st.markdown(
                f"<div class='sanzar-detail-field'>"
                f"<span class='sanzar-detail-label'>{_esc(label)}</span><br>"
                f"<span class='sanzar-detail-value'>{_esc(value).replace(chr(10), '<br>')}</span></div>",
                unsafe_allow_html=True,
            )
