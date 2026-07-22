from __future__ import annotations

import contextlib
import io
import tempfile
import traceback
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from app import auth
from app.cache import cultivos_kc_service, history_service, load_cultivos_kc_cached, load_history_rows_cached, load_users_cached
from app.state import bump_cultivos_kc_cache
from config.settings import CULTIVOS_KC_HEADERS
from services.incidencia_association_options import build_campana_history_options
from services.locale_numbers import parse_locale_float, parse_p_tabla
from services.riego_umbrales import (
    TABLA_TEXTURAS,
    ParametrosDeteccion,
    ParametrosPMP,
    calcular_kc_cultivo,
    dibujar_curva_kc,
    ejecutar_analisis_completo,
    guardar_excel_completo_bytes,
    imprimir_informe_completo,
)
from services.tecnico_campana_prefill import (
    build_tecnico_prefill,
    contacts_with_open_campaigns,
    csv_upload_date_range,
    open_campaigns_for_contact,
    textura_visible_name,
)
from services.usda_soil_texture import classify_soil_texture
from ui.components.cultivo_kc_form import render_cultivo_kc_fields, save_cultivo_kc
from ui.components.page_header import render_page_header

FAO56_PDF_URL = "https://www.fao.org/4/x0490s/x0490s.pdf"
INFO_SLIDER_SIEMBRA_COSECHA = (
    "0% = estima el día del ciclo solo desde la fecha de siembra "
    "(días transcurridos desde la siembra hasta la fecha de referencia). "
    "100% = solo desde la fecha de cosecha (asumiendo que la cosecha cae "
    "en el día L4 del ciclo). Valores intermedios mezclan ambas estimaciones: "
    "d = (1−w)·d_siembra + w·d_cosecha."
)

CULTIVOS_NEW_DIALOG_KEY = "tecnico_cultivos_new_dialog_open"
CULTIVOS_EDIT_DIALOG_KEY = "tecnico_cultivos_edit_dialog_open"
CULTIVOS_SELECTED_ID_KEY = "tecnico_cultivos_selected_id"
CULTIVOS_DELETE_STEP2_KEY = "tecnico_cultivos_delete_step2_id"
CULTIVOS_SUCCESS_KEY = "tecnico_cultivos_success_message"

# Copia fuera de keys de widgets: st.rerun() dentro de @st.dialog puede
# borrar el estado de number_input/selectbox de la página (bug Streamlit).
_TECNICO_FORM_BACKUP_KEYS = (
    "tecnico_kc",
    "tecnico_p_tabla",
    "tecnico_lat",
    "tecnico_lon",
    "tecnico_textura",
    "tecnico_coef_seguridad",
    "tecnico_fecha_inicio",
    "tecnico_fecha_fin",
    "tecnico_fecha_siembra_dialog",
    "tecnico_fecha_cosecha_dialog",
    "tecnico_cultivo_kc_sel",
)


def _form_backup_key(widget_key: str) -> str:
    return f"{widget_key}__saved"


def _snapshot_tecnico_form_backup() -> None:
    """Guarda valores actuales del formulario en keys que no son de widgets."""
    for key in _TECNICO_FORM_BACKUP_KEYS:
        if key in st.session_state:
            st.session_state[_form_backup_key(key)] = st.session_state[key]


def _restore_tecnico_form_from_backup() -> None:
    """Si Streamlit borró un widget key al cerrar el diálogo, recupéralo."""
    for key in _TECNICO_FORM_BACKUP_KEYS:
        saved = _form_backup_key(key)
        if key not in st.session_state and saved in st.session_state:
            st.session_state[key] = st.session_state[saved]


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "quota exceeded" in msg or "read requests" in msg


def _actor_name() -> str:
    uid = auth.get_authenticated_user_id()
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    for user in users:
        if user.employee_id == uid:
            return user.nombre
    return uid


def _nombre_visible_textura(clave: str) -> str:
    return textura_visible_name(clave)


def _texto_informe(informe) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        imprimir_informe_completo(informe)
    return buffer.getvalue()


def _crear_tabla_texturas() -> pd.DataFrame:
    filas = []
    for clave in TABLA_TEXTURAS:
        cc = TABLA_TEXTURAS[clave]["cc_teorica"]
        pmp = TABLA_TEXTURAS[clave]["pmp_teorica"]
        filas.append(
            {
                "Textura": _nombre_visible_textura(clave),
                "CC (%VWC)": cc,
                "PMP (%VWC)": pmp,
                "AD (%VWC)": cc - pmp,
            }
        )
    df = pd.DataFrame(filas)
    return df.sort_values("Textura").reset_index(drop=True)


def _guardar_csv_upload_temp(upload) -> str:
    tmp = tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False)
    try:
        tmp.write(upload.getbuffer())
        tmp.flush()
        return tmp.name
    finally:
        tmp.close()


def _init_session_kc() -> None:
    # Primero: recuperar lo que el diálogo pudo borrar con st.rerun().
    _restore_tecnico_form_from_backup()
    if "tecnico_kc" not in st.session_state:
        st.session_state.tecnico_kc = 1.0
    if "tecnico_p_tabla" not in st.session_state:
        st.session_state.tecnico_p_tabla = 0.40
    if "tecnico_lat" not in st.session_state:
        st.session_state.tecnico_lat = 0.0
    if "tecnico_lon" not in st.session_state:
        st.session_state.tecnico_lon = 0.0
    if "tecnico_textura" not in st.session_state:
        st.session_state.tecnico_textura = _nombre_visible_textura(next(iter(TABLA_TEXTURAS.keys())))
    if "tecnico_dialog_kc_vista" not in st.session_state:
        st.session_state.tecnico_dialog_kc_vista = "calcular"
    if "tecnico_abrir_dialog_kc" not in st.session_state:
        st.session_state.tecnico_abrir_dialog_kc = False
    if "tecnico_prefill_missing" not in st.session_state:
        st.session_state.tecnico_prefill_missing = []
    if "tecnico_applied_campana_id" not in st.session_state:
        st.session_state.tecnico_applied_campana_id = ""
    if "tecnico_fecha_inicio" not in st.session_state:
        st.session_state.tecnico_fecha_inicio = None
    if "tecnico_fecha_fin" not in st.session_state:
        st.session_state.tecnico_fecha_fin = None


def _optional_date_input(label: str, *, key: str) -> date | None:
    """date_input opcional que respeta un valor ya prellenado en session_state.

    Si se pasa ``value=None`` cuando el key ya tiene una fecha (p.ej. desde
    campaña), Streamlit pisa ese valor al montar el widget. Solo usamos
    ``value=None`` cuando aún no hay nada en session_state.
    """
    existing = st.session_state.get(key)
    if isinstance(existing, date):
        return st.date_input(label, format="YYYY-MM-DD", key=key)
    return st.date_input(label, value=None, format="YYYY-MM-DD", key=key)


def _empty_cultivo_row() -> dict[str, str]:
    return {h: "" for h in CULTIVOS_KC_HEADERS}


def _row_dict(row: pd.Series) -> dict[str, str]:
    return {h: str(row.get(h, "") or "") for h in CULTIVOS_KC_HEADERS}


def _load_cultivos_df() -> pd.DataFrame:
    ver = st.session_state.get("cultivos_kc_cache_version", 0)
    svc = cultivos_kc_service()
    try:
        df = load_cultivos_kc_cached(ver)
        if df.empty:
            if svc.seed_if_empty(actor_name=_actor_name()):
                bump_cultivos_kc_cache()
                df = load_cultivos_kc_cached(st.session_state.get("cultivos_kc_cache_version", 0))
        return df
    except Exception as exc:
        if _is_quota_error(exc):
            st.error("Google Sheets sin cuota de lectura (429). Reintenta en unos segundos.")
            return pd.DataFrame(columns=list(CULTIVOS_KC_HEADERS))
        raise


def _list_cultivos_for_kc() -> list[dict]:
    df = _load_cultivos_df()
    return _cultivos_from_df(df)


def _cultivos_from_df(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    rows = df.fillna("").astype(str).to_dict("records")
    out: list[dict] = []
    for row in rows:
        nombre = str(row.get("nombre", "") or "").strip()
        if not nombre:
            continue
        try:
            item = {
                "cultivo_kc_id": str(row.get("cultivo_kc_id", "") or "").strip(),
                "nombre": nombre,
                "L1": parse_locale_float(row["L1"]),
                "L2": parse_locale_float(row["L2"]),
                "L3": parse_locale_float(row["L3"]),
                "L4": parse_locale_float(row["L4"]),
                "kc_ini": parse_locale_float(row["kc_ini"]),
                "kc_med": parse_locale_float(row["kc_med"]),
                "kc_fin": parse_locale_float(row["kc_fin"]),
            }
            if any(v is None for v in (item["L1"], item["L2"], item["L3"], item["L4"], item["kc_ini"], item["kc_med"], item["kc_fin"])):
                continue
            p_val = parse_p_tabla(row.get("p_tabla"))
            if p_val is not None:
                item["p_tabla"] = p_val
            out.append(item)
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda c: str(c["nombre"]).lower())
    return out


def _close_dialog_kc() -> None:
    # Antes de que Streamlit limpie widgets «stale» del fragment del diálogo.
    _snapshot_tecnico_form_backup()
    st.session_state.tecnico_abrir_dialog_kc = False
    st.session_state.tecnico_dialog_kc_vista = "calcular"


def _close_cultivos_new_dialog() -> None:
    st.session_state.pop(CULTIVOS_NEW_DIALOG_KEY, None)


def _close_cultivos_edit_dialog() -> None:
    st.session_state.pop(CULTIVOS_EDIT_DIALOG_KEY, None)
    st.session_state.pop(CULTIVOS_DELETE_STEP2_KEY, None)


def _close_all_tecnico_dialogs() -> None:
    """Cierra cualquier otro diálogo de Técnico antes de abrir uno nuevo.

    Streamlit solo permite un @st.dialog abierto por script-run; como las dos
    pestañas de esta página ejecutan su código en cada run (cambiar de pestaña
    es solo visual), hay que garantizar exclusión mutua explícita al abrir.
    """
    _close_dialog_kc()
    _close_cultivos_new_dialog()
    _close_cultivos_edit_dialog()


def _render_cultivo_form(values: dict[str, str], *, mode: str) -> None:
    prefix = f"tecnico_cultivo_{mode}"
    cultivo_id = str(values.get("cultivo_kc_id", "") or "").strip()
    draft = render_cultivo_kc_fields({**values, "cultivo_kc_id": cultivo_id}, key_prefix=prefix)
    draft["cultivo_kc_id"] = cultivo_id

    save_col, cancel_col = st.columns(2)
    if save_col.button("Guardar", type="primary", key=f"{prefix}_save", use_container_width=True):
        try:
            saved_id = save_cultivo_kc(
                draft,
                actor_name=_actor_name(),
                mode="create" if mode == "new" else "edit",
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            if _is_quota_error(exc):
                st.error("Google Sheets sin cuota (429). Reintenta en unos segundos.")
                return
            raise
        st.session_state[CULTIVOS_SUCCESS_KEY] = "Cultivo guardado."
        st.session_state[CULTIVOS_SELECTED_ID_KEY] = saved_id
        st.session_state["tecnico_cultivo_kc_sel"] = str(draft.get("nombre", "") or "").strip()
        if mode == "edit":
            _close_cultivos_edit_dialog()
        else:
            _close_cultivos_new_dialog()
        st.rerun()

    if cancel_col.button("Cancelar", key=f"{prefix}_cancel", use_container_width=True):
        if mode == "edit":
            _close_cultivos_edit_dialog()
        else:
            _close_cultivos_new_dialog()
        st.rerun()

    if mode == "edit" and cultivo_id:
        st.divider()
        if st.button("Eliminar cultivo", key=f"{prefix}_delete_step1", type="secondary"):
            st.session_state[CULTIVOS_DELETE_STEP2_KEY] = cultivo_id
            st.session_state[CULTIVOS_EDIT_DIALOG_KEY] = True
            st.rerun()
        if str(st.session_state.get(CULTIVOS_DELETE_STEP2_KEY, "") or "").strip() == cultivo_id:
            d1, d2 = st.columns(2)
            if d1.button("Confirmar eliminación", key=f"{prefix}_delete_confirm", type="primary", use_container_width=True):
                deleted = cultivos_kc_service().delete_cultivo_by_id(cultivo_id)
                if not deleted:
                    st.warning("No se encontró el cultivo.")
                    return
                bump_cultivos_kc_cache()
                st.session_state[CULTIVOS_SELECTED_ID_KEY] = ""
                st.session_state.pop(CULTIVOS_DELETE_STEP2_KEY, None)
                _close_cultivos_edit_dialog()
                st.session_state[CULTIVOS_SUCCESS_KEY] = "Cultivo eliminado."
                st.rerun()
            if d2.button("Cancelar eliminación", key=f"{prefix}_delete_cancel", use_container_width=True):
                st.session_state.pop(CULTIVOS_DELETE_STEP2_KEY, None)
                st.session_state[CULTIVOS_EDIT_DIALOG_KEY] = True
                st.rerun()


def _num(value: object, default: float) -> float:
    try:
        raw = str(value or "").strip()
        if not raw:
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


@st.dialog("Nuevo cultivo Kc", width="large", on_dismiss=_close_cultivos_new_dialog)
def _cultivos_new_dialog() -> None:
    head1, head2 = st.columns([1, 0.22])
    with head1:
        st.markdown("### Alta de cultivo")
    with head2:
        if st.button("Cerrar", key="tecnico_cultivos_new_close", use_container_width=True):
            _close_cultivos_new_dialog()
            st.rerun()
    _render_cultivo_form(_empty_cultivo_row(), mode="new")


@st.dialog("Editar cultivo Kc", width="large", on_dismiss=_close_cultivos_edit_dialog)
def _cultivos_edit_dialog(cultivos_df: pd.DataFrame) -> None:
    cultivo_id = str(st.session_state.get(CULTIVOS_SELECTED_ID_KEY, "") or "").strip()
    if not cultivo_id:
        st.warning("No hay cultivo seleccionado.")
        return
    matches = cultivos_df[cultivos_df["cultivo_kc_id"].astype(str).str.strip() == cultivo_id]
    if matches.empty:
        st.warning("El cultivo ya no existe.")
        return
    values = _row_dict(matches.iloc[0])
    head1, head2 = st.columns([1, 0.22])
    with head1:
        st.markdown(f"### {values.get('nombre') or cultivo_id[:8]}")
    with head2:
        if st.button("Cerrar", key="tecnico_cultivos_edit_close", use_container_width=True):
            _close_cultivos_edit_dialog()
            st.rerun()
    _render_cultivo_form(values, mode="edit")


def _vista_crear_cultivo_en_dialog_kc() -> None:
    st.markdown("### Crear nuevo cultivo")
    if st.button("← Volver al cálculo de Kc"):
        st.session_state.tecnico_dialog_kc_vista = "calcular"
        st.rerun()

    # Fuera del form: st.link_button no es form_submit_button.
    st.link_button(
        "FAO-56: L en pág. 125 · Kc en pág. 131",
        FAO56_PDF_URL,
        use_container_width=True,
    )

    with st.form("tecnico_form_nuevo_cultivo_dialog"):
        draft = render_cultivo_kc_fields(
            {},
            key_prefix="tecnico_dialog_nuevo_cultivo",
            show_fao_link=False,
        )
        enviado = st.form_submit_button("Guardar cultivo", type="primary")

    if enviado:
        try:
            save_cultivo_kc(draft, actor_name=_actor_name(), mode="create")
            st.session_state.tecnico_dialog_kc_vista = "calcular"
            st.session_state["tecnico_cultivo_kc_sel"] = str(draft.get("nombre", "") or "").strip()
            st.success(f"Cultivo «{str(draft.get('nombre', '') or '').strip()}» guardado.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _vista_calcular_kc_en_dialog() -> None:
    cultivos = _list_cultivos_for_kc()
    nombres = [c["nombre"] for c in cultivos]
    cultivo_por_nombre = {c["nombre"]: c for c in cultivos}

    if not nombres:
        st.warning("No hay cultivos. Pulsa + para crear uno.")
        if st.button("＋ Crear cultivo", key="tecnico_btn_crear_cultivo_empty"):
            st.session_state.tecnico_dialog_kc_vista = "crear"
            st.rerun()
        return

    col_sel, col_plus = st.columns([0.85, 0.15])
    with col_sel:
        default_idx = 0
        if "tecnico_cultivo_kc_sel" in st.session_state and st.session_state.tecnico_cultivo_kc_sel in nombres:
            default_idx = nombres.index(st.session_state.tecnico_cultivo_kc_sel)
        nombre_sel = st.selectbox("Cultivo", options=nombres, index=default_idx, key="tecnico_select_cultivo_dialog")
        st.session_state.tecnico_cultivo_kc_sel = nombre_sel
    with col_plus:
        st.write("")
        if st.button("＋", help="Crear nuevo cultivo", key="tecnico_btn_plus_cultivo"):
            st.session_state.tecnico_dialog_kc_vista = "crear"
            st.rerun()

    cultivo = cultivo_por_nombre[nombre_sel]

    fecha_ref = st.date_input("Fecha de referencia", value=date.today(), format="YYYY-MM-DD", key="tecnico_fecha_ref_dialog")

    # Siempre visibles (opcionales). Si hay campaña, llegan prellenadas desde
    # fecha_campana_inicio / fecha_campana_fin — sin checkboxes intermedios
    # (Streamlit no sincroniza bien flag+date al abrir el diálogo).
    st.caption("Siembra / cosecha: se rellenan solas al elegir una campaña; déjalas vacías si no aplican.")
    col_siembra, col_cosecha = st.columns(2)
    with col_siembra:
        fecha_siembra = _optional_date_input("Fecha de siembra", key="tecnico_fecha_siembra_dialog")
    with col_cosecha:
        fecha_cosecha = _optional_date_input("Fecha de cosecha", key="tecnico_fecha_cosecha_dialog")

    col_slider, col_info = st.columns([0.9, 0.1])
    with col_slider:
        prioridad_pct = st.slider(
            "Prioridad siembra ↔ cosecha",
            min_value=0,
            max_value=100,
            value=0,
            key="tecnico_slider_prioridad_dialog",
        )
    with col_info:
        st.write("")
        with st.popover("ℹ️"):
            st.markdown(INFO_SLIDER_SIEMBRA_COSECHA)

    peso_cosecha = prioridad_pct / 100.0
    puede_calcular = (fecha_siembra is not None) or (fecha_cosecha is not None)

    resultado = None
    if puede_calcular:
        resultado = calcular_kc_cultivo(cultivo, fecha_ref, fecha_siembra, fecha_cosecha, peso_cosecha)
        m1, m2, m3 = st.columns(3)
        m1.metric("Día del ciclo", f"{resultado['dia_ciclo']:.1f}")
        m2.metric("Etapa", str(resultado["etapa"]))
        m3.metric("Kc calculado", f"{resultado['kc']:.3f}")
    else:
        st.info("Indica al menos fecha de siembra o de cosecha, luego pulsa Procesar.")

    dia_marca = resultado["dia_ciclo"] if resultado else None
    fig = dibujar_curva_kc(cultivo, dia_ciclo_val=dia_marca)
    st.pyplot(fig, clear_figure=True)
    plt.close(fig)

    if st.button("Procesar", type="primary", key="tecnico_btn_procesar_kc"):
        if not puede_calcular or resultado is None or resultado["kc"] is None:
            st.error("Necesitas fecha de siembra y/o cosecha para calcular el Kc.")
        else:
            st.session_state.tecnico_kc = float(resultado["kc"])
            # Snapshot antes del rerun: el cierre del diálogo puede borrar
            # lat/lon/etc. de session_state (widgets fuera del fragment).
            _snapshot_tecnico_form_backup()
            st.session_state.tecnico_abrir_dialog_kc = False
            st.rerun()


@st.dialog("Calcular Kc FAO-56", width="large", on_dismiss=_close_dialog_kc)
def _dialog_calcular_kc() -> None:
    if st.session_state.tecnico_dialog_kc_vista == "crear":
        _vista_crear_cultivo_en_dialog_kc()
    else:
        _vista_calcular_kc_en_dialog()


def _apply_campana_prefill(result) -> None:
    vals = result.values
    if "cultivo_nombre" in vals:
        st.session_state["tecnico_cultivo_kc_sel"] = str(vals["cultivo_nombre"])
    if "p_tabla" in vals:
        p_ok = parse_p_tabla(vals["p_tabla"])
        if p_ok is not None:
            st.session_state["tecnico_p_tabla"] = float(p_ok)
    if "lat" in vals:
        st.session_state["tecnico_lat"] = float(vals["lat"])
    if "lon" in vals:
        st.session_state["tecnico_lon"] = float(vals["lon"])
    if "textura" in vals:
        st.session_state["tecnico_textura"] = _nombre_visible_textura(str(vals["textura"]))
    # Fechas de campaña → diálogo Calcular Kc (siembra/cosecha).
    if "fecha_siembra" in vals:
        st.session_state["tecnico_fecha_siembra_dialog"] = vals["fecha_siembra"]
    else:
        st.session_state.pop("tecnico_fecha_siembra_dialog", None)
    if "fecha_cosecha" in vals:
        st.session_state["tecnico_fecha_cosecha_dialog"] = vals["fecha_cosecha"]
    else:
        st.session_state.pop("tecnico_fecha_cosecha_dialog", None)
    st.session_state.pop("tecnico_hay_siembra_dialog", None)
    st.session_state.pop("tecnico_hay_cosecha_dialog", None)
    st.session_state["tecnico_prefill_missing"] = list(result.missing)
    _snapshot_tecnico_form_backup()


def _render_umbrales_origen(contacts_df: pd.DataFrame) -> None:
    with st.container(border=True):
        st.markdown("##### Origen de datos")
        modo = st.radio(
            "Origen de datos",
            options=["manual", "cliente"],
            format_func=lambda x: "Formulario manual" if x == "manual" else "Desde cliente / campaña",
            horizontal=True,
            key="tecnico_modo_campana",
            label_visibility="collapsed",
        )
        if modo != "cliente":
            st.session_state["tecnico_prefill_missing"] = []
            st.session_state["tecnico_applied_campana_id"] = ""
            st.caption("Introduce los parámetros a mano en los bloques siguientes.")
            return

        try:
            campanas_rows = load_history_rows_cached("campanas", st.session_state.get("history_cache_version", 0))
        except Exception:
            history_service().load_kind("campanas")
            campanas_rows = history_service().rows("campanas")

        contact_opts = contacts_with_open_campaigns(contacts_df, campanas_rows)
        if not contact_opts:
            st.info("No hay contactos con campaña activa.")
            return

        st.caption("Solo salen clientes con campaña activa.")
        labels = {c.contact_id: c.nombre for c in contact_opts}
        contact_ids = [c.contact_id for c in contact_opts]
        selected_contact = st.selectbox(
            "Cliente",
            options=contact_ids,
            format_func=lambda cid: labels.get(cid, cid),
            key="tecnico_campana_contact_id",
        )
        open_rows = open_campaigns_for_contact(campanas_rows, selected_contact)
        camp_opts = build_campana_history_options(open_rows)
        if not camp_opts:
            st.warning("Este cliente no tiene campañas abiertas.")
            return

        camp_labels = {o.id: o.label for o in camp_opts}
        camp_ids = [o.id for o in camp_opts]
        selected_campana_id = st.selectbox(
            "Campaña",
            options=camp_ids,
            format_func=lambda cid: camp_labels.get(cid, cid),
            key="tecnico_campana_id",
        )
        campana = next(
            (r for r in open_rows if str(r.get("historial_campana_id", "")).strip() == selected_campana_id),
            None,
        )
        contact_row = {}
        if not contacts_df.empty and "contact_id" in contacts_df.columns:
            matches = contacts_df[contacts_df["contact_id"].astype(str).str.strip() == str(selected_contact)]
            if not matches.empty:
                contact_row = matches.iloc[0].fillna("").astype(str).to_dict()

        if selected_campana_id and selected_campana_id != st.session_state.get("tecnico_applied_campana_id"):
            cultivos = _list_cultivos_for_kc()
            result = build_tecnico_prefill(campana, contact_row, cultivos)
            _apply_campana_prefill(result)
            st.session_state["tecnico_applied_campana_id"] = selected_campana_id

        missing = list(st.session_state.get("tecnico_prefill_missing") or [])
        if missing:
            st.warning("Campos pendientes de completar:\n\n- " + "\n- ".join(missing))
        else:
            st.success("Campaña cargada: todos los campos disponibles se rellenaron.")


def _render_umbrales_sensor() -> tuple[object, bool, object, object]:
    with st.container(border=True):
        st.markdown("##### Sensor y periodo")
        csv_upload = st.file_uploader("CSV del sensor", type=["csv"], key="tecnico_csv_upload")
        con_cabecera = st.checkbox("El CSV tiene fila de cabecera", value=False, key="tecnico_con_cabecera")

        if csv_upload is not None:
            fp = f"{getattr(csv_upload, 'name', '')}:{getattr(csv_upload, 'size', 0)}:{bool(con_cabecera)}"
            if st.session_state.get("tecnico_csv_range_fp") != fp:
                try:
                    d0, d1 = csv_upload_date_range(csv_upload, con_cabecera=bool(con_cabecera))
                except Exception:
                    d0, d1 = None, None
                if d0 is not None:
                    st.session_state["tecnico_fecha_inicio"] = d0
                if d1 is not None:
                    st.session_state["tecnico_fecha_fin"] = d1
                st.session_state["tecnico_csv_range_fp"] = fp

        col_fi, col_ff = st.columns(2)
        with col_fi:
            fecha_inicio = st.date_input("Fecha inicio (opcional)", format="YYYY-MM-DD", key="tecnico_fecha_inicio")
        with col_ff:
            fecha_fin = st.date_input("Fecha fin (opcional)", format="YYYY-MM-DD", key="tecnico_fecha_fin")
        st.caption("Si subes un CSV, inicio/fin se rellenan con el rango del fichero (editables).")
    return csv_upload, bool(con_cabecera), fecha_inicio, fecha_fin


def _render_umbrales_suelo() -> str:
    with st.container(border=True):
        st.markdown("##### Suelo")
        texture_key_por_visible = {_nombre_visible_textura(k): k for k in TABLA_TEXTURAS}
        visibles = list(texture_key_por_visible.keys())
        if st.session_state.get("tecnico_textura") not in visibles:
            st.session_state.tecnico_textura = visibles[0]
        textura_visible = st.selectbox(
            "Textura del suelo",
            options=visibles,
            key="tecnico_textura",
        )
        textura_key = texture_key_por_visible[textura_visible]

        cc_teorica = TABLA_TEXTURAS[textura_key]["cc_teorica"]
        pmp_teorica = TABLA_TEXTURAS[textura_key]["pmp_teorica"]
        ad_teorica = cc_teorica - pmp_teorica
        m1, m2, m3 = st.columns(3)
        m1.metric("CC teórica", f"{cc_teorica} %VWC")
        m2.metric("PMP teórica", f"{pmp_teorica} %VWC")
        m3.metric("AD teórica", f"{ad_teorica} %VWC")
        st.caption("Consulta la pestaña **Texturas** para la tabla completa.")
    return textura_key


def _render_umbrales_cultivo() -> tuple[float, float, float]:
    with st.container(border=True):
        st.markdown("##### Parámetros de cultivo")
        # Evita crash si session_state quedó con p mangled (p.ej. 3.0 por locale Sheets).
        p_session = parse_p_tabla(st.session_state.get("tecnico_p_tabla", 0.40))
        if p_session is None:
            st.session_state["tecnico_p_tabla"] = 0.40
        elif float(st.session_state.get("tecnico_p_tabla", 0.40)) != p_session:
            st.session_state["tecnico_p_tabla"] = p_session

        col_p, col_kc, col_coef = st.columns(3)
        with col_p:
            p_tabla = st.number_input(
                "p de tabla FAO-56 (0-1)",
                min_value=0.0,
                max_value=1.0,
                step=0.01,
                key="tecnico_p_tabla",
            )
            st.link_button("Cuadro 22 (pág. 184)", FAO56_PDF_URL)
        with col_kc:
            col_kc_in, col_lupa = st.columns([0.82, 0.18])
            with col_kc_in:
                kc = st.number_input(
                    "Kc (coef. de cultivo)",
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    key="tecnico_kc",
                    help="Usa la lupa para calcularlo con la curva FAO-56 (prioridad siembra/cosecha).",
                )
            with col_lupa:
                st.write("")
                if st.button("🔍", help="Calcular Kc FAO-56", key="tecnico_btn_lupa_kc"):
                    _close_all_tecnico_dialogs()
                    st.session_state.tecnico_dialog_kc_vista = "calcular"
                    st.session_state.tecnico_abrir_dialog_kc = True
                    st.rerun()
        with col_coef:
            coef_seguridad_vwc = st.number_input(
                "Coeficiente de seguridad (%VWC)",
                min_value=0.0,
                value=2.0,
                step=0.1,
                format="%.1f",
                key="tecnico_coef_seguridad",
                help="Se suma a la CC óptima para obtener el umbral superior final (puntos de %VWC).",
            )
        st.caption(
            "Consulta el **Cuadro 22** en la **página 184** del manual FAO-56 "
            "(*Riego y drenaje*) para elegir el valor de **p** según el cultivo."
        )
    return float(p_tabla), float(kc), float(coef_seguridad_vwc)


def _render_umbrales_ubicacion() -> tuple[float, float]:
    with st.container(border=True):
        st.markdown("##### Ubicación")
        col_lat, col_lon = st.columns(2)
        with col_lat:
            lat = st.number_input(
                "Latitud",
                min_value=-90.0,
                max_value=90.0,
                step=0.0001,
                format="%.6f",
                key="tecnico_lat",
            )
        with col_lon:
            lon = st.number_input(
                "Longitud",
                min_value=-180.0,
                max_value=180.0,
                step=0.0001,
                format="%.6f",
                key="tecnico_lon",
            )
    return float(lat), float(lon)


def _render_umbrales_avanzadas() -> tuple[float, float, bool]:
    with st.expander("Opciones avanzadas", expanded=False):
        umbral_lluvia_mm = st.number_input(
            "Umbral de lluvia (mm)", min_value=0.0, value=1.0, step=0.1, key="tecnico_umbral_lluvia"
        )
        percentil_valle = st.number_input(
            "Percentil del valle de seguridad",
            min_value=0.0,
            max_value=100.0,
            value=75.0,
            step=1.0,
            key="tecnico_percentil_valle",
            help=(
                "Percentil de la humedad justo antes de cada riego real ya practicado. "
                "P75 (75) es el valor conservador por defecto."
            ),
        )
        excluir_posible_lluvia = st.checkbox(
            "Excluir del cálculo los eventos que puedan ser lluvia",
            value=False,
            key="tecnico_excluir_lluvia",
        )
    return float(umbral_lluvia_mm), float(percentil_valle), bool(excluir_posible_lluvia)


def _render_tab_umbrales(contacts_df: pd.DataFrame) -> None:
    _init_session_kc()

    _render_umbrales_origen(contacts_df)
    csv_upload, con_cabecera, fecha_inicio, fecha_fin = _render_umbrales_sensor()
    textura_key = _render_umbrales_suelo()
    p_tabla, kc, coef_seguridad_vwc = _render_umbrales_cultivo()
    lat, lon = _render_umbrales_ubicacion()
    umbral_lluvia_mm, percentil_valle, excluir_posible_lluvia = _render_umbrales_avanzadas()
    # Mantener backup fresco por si el siguiente interacción es el diálogo Kc.
    _snapshot_tecnico_form_backup()

    ejecutar = st.button(
        "Calcular umbrales y generar Excel",
        type="primary",
        use_container_width=True,
        key="tecnico_btn_calcular",
    )
    if not ejecutar:
        return

    if csv_upload is None:
        st.error("Selecciona primero un CSV.")
        return
    if float(lat) == 0.0 and float(lon) == 0.0:
        st.error("Indica latitud y longitud reales del sensor (no dejes 0.0 / 0.0).")
        return
    if fecha_inicio is not None and fecha_fin is not None and fecha_fin < fecha_inicio:
        st.error("La fecha fin no puede ser anterior a la fecha inicio.")
        return

    try:
        fecha_inicio_val = fecha_inicio.strftime("%Y-%m-%d") if fecha_inicio is not None else None
        fecha_fin_val = fecha_fin.strftime("%Y-%m-%d") if fecha_fin is not None else None
        st.info(f"Calculando con Kc = {float(kc):.3f} (puede tardar unos segundos por Open-Meteo)...")
        with st.spinner("Procesando..."):
            ruta_csv_temp = _guardar_csv_upload_temp(csv_upload)
            try:
                informe = ejecutar_analisis_completo(
                    csv_path=ruta_csv_temp,
                    p_tabla=float(p_tabla),
                    textura=str(textura_key),
                    kc=float(kc),
                    coef_seguridad_vwc=float(coef_seguridad_vwc),
                    lat=float(lat),
                    lon=float(lon),
                    fecha_inicio=fecha_inicio_val,
                    fecha_fin=fecha_fin_val,
                    umbral_lluvia_mm=float(umbral_lluvia_mm),
                    excluir_posible_lluvia=bool(excluir_posible_lluvia),
                    percentil_valle=float(percentil_valle),
                    params_cc=ParametrosDeteccion(),
                    params_pmp=ParametrosPMP(),
                    con_cabecera=bool(con_cabecera),
                )
                with st.container(border=True):
                    st.markdown("##### Informe")
                    texto = _texto_informe(informe)
                    st.text_area("Salida", value=texto, height=320, key="tecnico_informe_texto")
                    data = guardar_excel_completo_bytes(informe)
                    st.download_button(
                        label="Descargar Excel",
                        data=data,
                        file_name=f"informe_umbrales_{lat}_{lon}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="tecnico_download_excel",
                    )
            finally:
                with contextlib.suppress(Exception):
                    Path(ruta_csv_temp).unlink(missing_ok=True)
    except Exception as exc:
        st.error("Error durante el cálculo.")
        with st.expander("Detalle técnico"):
            st.code(traceback.format_exc())
            st.caption(str(exc))


def _render_tab_texturas() -> None:
    st.subheader("Tabla de referencia de texturas")
    st.caption("Elige la textura en **Calcular umbrales**; aquí solo es consulta.")
    st.dataframe(_crear_tabla_texturas(), use_container_width=True, hide_index=True)
    st.caption("CC = capacidad de campo teórica, PMP = punto de marchitez fisiológica teórico.")


def _render_tab_triangulo_usda() -> None:
    st.subheader("Triángulo textural USDA")
    st.caption(
        "Introduce el % de arcilla, limo y arena (USDA-NRCS). "
        "Si la suma no es exactamente 100, se normaliza de forma proporcional."
    )

    with st.container(border=True):
        st.markdown("##### Porcentajes de la muestra")
        c1, c2, c3 = st.columns(3)
        with c1:
            clay = st.number_input(
                "Arcilla %",
                min_value=0.0,
                max_value=100.0,
                value=20.0,
                step=0.1,
                format="%.1f",
                key="tecnico_usda_clay",
            )
        with c2:
            silt = st.number_input(
                "Limo %",
                min_value=0.0,
                max_value=100.0,
                value=60.0,
                step=0.1,
                format="%.1f",
                key="tecnico_usda_silt",
            )
        with c3:
            sand = st.number_input(
                "Arena %",
                min_value=0.0,
                max_value=100.0,
                value=20.0,
                step=0.1,
                format="%.1f",
                key="tecnico_usda_sand",
            )
        total = float(clay) + float(silt) + float(sand)
        st.caption(f"Suma actual: **{total:.1f}** %")

        if st.button("Clasificar textura", type="primary", key="tecnico_usda_clasificar"):
            try:
                resultado = classify_soil_texture(float(clay), float(silt), float(sand))
                st.session_state["tecnico_usda_last_result"] = resultado
            except ValueError as exc:
                st.session_state.pop("tecnico_usda_last_result", None)
                st.error(str(exc))

    resultado = st.session_state.get("tecnico_usda_last_result")
    if not isinstance(resultado, dict):
        return

    with st.container(border=True):
        st.markdown("##### Resultado")
        clase_es = str(resultado.get("clase_es", "") or "")
        clase_crm = str(resultado.get("clase_crm", "") or "")
        st.success(f"Clase textural: **{clase_es}**")
        st.caption(
            f"Clave CRM: `{clase_crm}` · "
            f"Arcilla {resultado.get('clay')}% · "
            f"Limo {resultado.get('silt')}% · "
            f"Arena {resultado.get('sand')}%"
        )
        candidatos = list(resultado.get("candidatos") or [])
        if len(candidatos) > 1:
            st.caption(
                "El punto cae justo en el límite entre varias clases: "
                + ", ".join(str(c) for c in candidatos)
            )

        if st.button("Usar en Calcular umbrales", key="tecnico_usda_aplicar"):
            if clase_crm not in TABLA_TEXTURAS:
                st.error(f"La clase «{clase_crm}» no está en la tabla de texturas del CRM.")
            else:
                st.session_state["tecnico_textura"] = _nombre_visible_textura(clase_crm)
                _snapshot_tecnico_form_backup()
                st.toast(f"Textura «{clase_es}» aplicada en Calcular umbrales.", icon="✅")


def _render_tab_cultivos() -> None:
    success = str(st.session_state.pop(CULTIVOS_SUCCESS_KEY, "") or "").strip()
    if success:
        st.success(success)

    cultivos_df = _load_cultivos_df()
    display_cols = [
        "nombre",
        "L1",
        "L2",
        "L3",
        "L4",
        "kc_ini",
        "kc_med",
        "kc_fin",
        "p_tabla",
        "creado_por",
        "created_at",
        "updated_at",
    ]
    view = cultivos_df.copy()
    if not view.empty:
        for col in display_cols + ["cultivo_kc_id"]:
            if col not in view.columns:
                view[col] = ""
        view = view[display_cols + ["cultivo_kc_id"]].fillna("").astype(str)
        view = view.sort_values("nombre", key=lambda s: s.str.lower()).reset_index(drop=True)

    toolbar1, toolbar2 = st.columns([3, 1])
    with toolbar1:
        st.caption("Cultivos Kc FAO-56 persistidos en Google Sheets.")
    with toolbar2:
        if st.button("+ Nuevo cultivo", type="primary", use_container_width=True, key="tecnico_btn_nuevo_cultivo"):
            _close_all_tecnico_dialogs()
            st.session_state[CULTIVOS_NEW_DIALOG_KEY] = True
            st.rerun()

    selected_id = ""
    if view.empty:
        st.info("No hay cultivos. Crea el primero con «Nuevo cultivo».")
    else:
        table_view = view.drop(columns=["cultivo_kc_id"]).rename(
            columns={
                "nombre": "Nombre",
                "kc_ini": "Kc ini",
                "kc_med": "Kc med",
                "kc_fin": "Kc fin",
                "p_tabla": "p_tabla",
                "creado_por": "Creado por",
                "created_at": "Creado",
                "updated_at": "Actualizado",
            }
        )
        event = st.dataframe(
            table_view,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tecnico_cultivos_table",
        )
        selected_rows = event.selection.rows if event else []
        if selected_rows:
            idx = int(selected_rows[0])
            if 0 <= idx < len(view):
                selected_id = str(view.iloc[idx]["cultivo_kc_id"]).strip()
                st.session_state[CULTIVOS_SELECTED_ID_KEY] = selected_id
                st.caption(f"Seleccionado: {view.iloc[idx]['nombre']}")

        actions = st.columns([1, 1, 3])
        if actions[0].button("Editar", use_container_width=True, disabled=not selected_id, key="tecnico_btn_edit_cultivo"):
            _close_all_tecnico_dialogs()
            st.session_state[CULTIVOS_SELECTED_ID_KEY] = selected_id
            st.session_state[CULTIVOS_EDIT_DIALOG_KEY] = True
            st.rerun()
        if actions[1].button("Eliminar", use_container_width=True, disabled=not selected_id, key="tecnico_btn_delete_cultivo"):
            _close_all_tecnico_dialogs()
            st.session_state[CULTIVOS_SELECTED_ID_KEY] = selected_id
            st.session_state[CULTIVOS_DELETE_STEP2_KEY] = selected_id
            st.session_state[CULTIVOS_EDIT_DIALOG_KEY] = True
            st.rerun()


def _render_tecnico_dialogs() -> None:
    """Único punto de apertura de diálogos de Técnico.

    Streamlit solo permite un @st.dialog abierto por script-run y las pestañas
    de esta página ejecutan su código en cada run (cambiar de pestaña es solo
    visual), así que aquí se decide, con prioridad única (elif), cuál de los
    diálogos (si alguno) se abre en este run.
    """
    if st.session_state.get(CULTIVOS_EDIT_DIALOG_KEY, False):
        _cultivos_edit_dialog(_load_cultivos_df())
    elif st.session_state.get(CULTIVOS_NEW_DIALOG_KEY, False):
        _cultivos_new_dialog()
    elif st.session_state.get("tecnico_abrir_dialog_kc", False):
        _dialog_calcular_kc()


def render(contacts_df: pd.DataFrame) -> None:
    render_page_header("Técnico")
    st.caption(
        "Cálculo de umbrales de riego, cultivos Kc FAO-56, texturas de referencia "
        "y clasificador del triángulo USDA."
    )
    tab_calc, tab_cult, tab_tex, tab_usda = st.tabs(
        ["Calcular umbrales", "Cultivos Kc", "Texturas", "Triángulo USDA"]
    )
    with tab_calc:
        _render_tab_umbrales(contacts_df if isinstance(contacts_df, pd.DataFrame) else pd.DataFrame())
    with tab_cult:
        _render_tab_cultivos()
    with tab_tex:
        _render_tab_texturas()
    with tab_usda:
        _render_tab_triangulo_usda()
    _render_tecnico_dialogs()
