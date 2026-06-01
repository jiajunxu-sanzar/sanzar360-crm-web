"""Email mass-send page.

Layout
------
Left panel  (42 %): search + filters, all-contacts table with multi-row
                    selection, select-all / deselect-all buttons.
Right panel (58 %): template editor, preview, seguimiento comercial checkbox
                    (optional bulk follow-up update), and send button.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import auth
from app.cache import history_service, load_users_cached
from app.navigation import ROLE_SALES, normalize_role, page_menu_title
from app.smtp_profiles import SmtpResolved, resolve_smtp_detail
from app.state import bump_contacts_cache, bump_history_cache, set_contacts_df_override
from config.settings import (
    CONTACT_ESTADO_OPCIONES,
    EMAIL_CLASIFICACION_OPCIONES,
    PERSONA_COMERCIAL_OPCIONES,
)
from services.commercial_action_validation import validate_commercial_action_values
from services.email_service import render_template, send_email, smtp_exception_user_message, validate_placeholders
from services.sheet_date_format import is_valid_dd_mm_yyyy
from ui.components.tables import filter_dataframe

# ---------------------------------------------------------------------------
# Session-state keys (all prefixed "email_" to avoid collisions)
# ---------------------------------------------------------------------------
_KEY_SELECTED = "email_selected_ids"    # set[str] — contact_ids selected in table
_KEY_FILTERS_OPEN = "email_filters_open"
_KEY_SEG_EMAIL_CLAS = "email_seg_email_clasificacion"
_KEY_SEG_EMAIL_URL = "email_seg_email_url"
_KEY_SEG_NOTAS = "email_seg_notas"
_KEY_SEG_PROX_FECHA = "email_seg_prox_fecha"
_KEY_SEG_PROX_CANAL = "email_seg_prox_canal"
_KEY_SEG_PERSONA_PROX = "email_seg_persona_prox"
_KEY_SEG_PROX_DETALLE = "email_seg_prox_detalle"

_DEFAULT_SUBJECT = "Hola {Nombre}"
_DEFAULT_BODY = "Hola {Nombre},\n\nTe escribimos desde Sanzar."

# Columns shown in the contact table
_TABLE_COLS = ["Nombre", "Estado", "Provincia", "Municipio", "Cultivos", "Correo"]


# ---------------------------------------------------------------------------
# State initialisation
# ---------------------------------------------------------------------------

def _ensure_state() -> None:
    defaults = {
        _KEY_SELECTED: set(),
        _KEY_FILTERS_OPEN: False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

def _unique_sorted(series: pd.Series) -> list[str]:
    return sorted([x for x in series.fillna("").astype(str).unique() if x])


def _render_filter_bar(df: pd.DataFrame) -> None:
    col_search, col_toggle = st.columns([0.84, 0.16], gap="small")
    col_search.text_input(
        "Buscar",
        key="email_filter_text",
        label_visibility="collapsed",
        placeholder="Nombre, correo, municipio, provincia...",
    )
    if col_toggle.button("⏬", key="email_toggle_filters", width="stretch", help="Filtros"):
        st.session_state[_KEY_FILTERS_OPEN] = not st.session_state[_KEY_FILTERS_OPEN]
        st.rerun()

    if not st.session_state[_KEY_FILTERS_OPEN]:
        return

    r1 = st.columns(3, gap="small")
    r1[0].selectbox("Estado", [""] + list(CONTACT_ESTADO_OPCIONES), key="email_filter_status")
    r1[1].selectbox("Provincia", [""] + _unique_sorted(df["provincia"]), key="email_filter_province")
    r1[2].selectbox("Tipo entidad", [""] + _unique_sorted(df["tipo_entidad"]), key="email_filter_entity")

    r2 = st.columns(2, gap="small")
    r2[0].selectbox("Municipio", [""] + _unique_sorted(df["municipio"]), key="email_filter_municipio")
    r2[1].text_input("Cultivos contiene", key="email_filter_cultivos")


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    text = st.session_state.get("email_filter_text", "")
    status = st.session_state.get("email_filter_status", "")
    province = st.session_state.get("email_filter_province", "")
    entity = st.session_state.get("email_filter_entity", "")
    municipio = st.session_state.get("email_filter_municipio", "")
    cultivos = st.session_state.get("email_filter_cultivos", "")

    out = df.copy()
    if text.strip():
        out = filter_dataframe(out, text.strip(),
            ["nombre", "municipio", "provincia", "correo", "telefono", "cultivos", "contact_id"])
    if status:
        out = out[out["estado"].astype(str) == status]
    if province:
        out = out[out["provincia"].astype(str) == province]
    if entity:
        out = out[out["tipo_entidad"].astype(str) == entity]
    if municipio:
        out = out[out["municipio"].astype(str) == municipio]
    if cultivos.strip():
        out = out[out["cultivos"].fillna("").astype(str).str.contains(cultivos.strip(), case=False, na=False)]
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Contact table
# ---------------------------------------------------------------------------

def _build_display_df(df_subset: pd.DataFrame) -> pd.DataFrame:
    """Return a display-ready DataFrame with friendly column names."""
    correo_col = df_subset["correo"].fillna("").astype(str).str.strip()
    return pd.DataFrame({
        "Nombre":    df_subset["nombre"].fillna("").astype(str),
        "Estado":    df_subset["estado"].fillna("").astype(str),
        "Provincia": df_subset["provincia"].fillna("").astype(str),
        "Municipio": df_subset["municipio"].fillna("").astype(str),
        "Cultivos":  df_subset["cultivos"].fillna("").astype(str),
        "Correo":    correo_col.where(correo_col != "", "—"),
    })


def _render_contact_table(filtered: pd.DataFrame) -> None:
    """Render the selectable contact table and keep email_selected_ids in sync.

    Contacts WITH email  → selectable st.dataframe (multi-row).
    Contacts WITHOUT email → read-only st.dataframe styled in grey below it.
    """
    has_email_mask = filtered["correo"].fillna("").astype(str).str.strip().ne("")
    df_with    = filtered[has_email_mask].reset_index(drop=True)
    df_without = filtered[~has_email_mask].reset_index(drop=True)

    ids_with = df_with["contact_id"].tolist()

    # --- Select-all / deselect-all ---
    ca, cb = st.columns(2, gap="small")
    if ca.button("Seleccionar todos", width="stretch", key="email_select_all"):
        st.session_state[_KEY_SELECTED] = set(ids_with)
        st.rerun()
    if cb.button("Deseleccionar todos", width="stretch", key="email_deselect_all"):
        st.session_state[_KEY_SELECTED] = set()
        st.rerun()

    # --- Selectable table: contacts WITH email ---
    if df_with.empty:
        st.info("Ningún contacto visible tiene dirección de correo.")
    else:
        event = st.dataframe(
            _build_display_df(df_with),
            width="stretch",
            hide_index=True,
            height=min(420, 36 + len(df_with) * 35),
            key="email_contact_table",
            on_select="rerun",
            selection_mode="multi-row",
        )

        raw_positions: list[int] = (
            list(event.selection.rows)
            if event and hasattr(event, "selection") and event.selection
            else []
        )
        # Update selection: keep previously-selected that are outside current filter + new picks
        visible_with = set(ids_with)
        all_visible  = set(filtered["contact_id"].tolist())
        preserved = {
            cid for cid in st.session_state[_KEY_SELECTED]
            if cid not in all_visible          # outside current filter → keep
        }
        newly_selected = {
            ids_with[pos]
            for pos in raw_positions
            if 0 <= pos < len(ids_with)
        }
        if event:  # table rendered → sync (don't overwrite on first render without interaction)
            st.session_state[_KEY_SELECTED] = preserved | newly_selected

    # --- Static greyed-out table: contacts WITHOUT email ---
    if not df_without.empty:
        st.caption(
            f"Sin correo — no seleccionables ({len(df_without)})"
        )
        grey_df = _build_display_df(df_without)
        styled = grey_df.style.set_properties(**{
            "color": "#c0c8d0",
            "font-style": "italic",
        })
        st.dataframe(
            styled,
            width="stretch",
            hide_index=True,
            height=min(220, 36 + len(df_without) * 35),
        )

    n_sel = len(st.session_state[_KEY_SELECTED])
    st.caption(f"{len(filtered)} contactos · {n_sel} seleccionados")


# ---------------------------------------------------------------------------
# Template editor + seguimiento checkbox + send (all in one right panel)
# ---------------------------------------------------------------------------

def _render_template_editor(
    contacts: pd.DataFrame,
    df_raw: pd.DataFrame,
    selected_ids: list[str],
    smtp_detail: SmtpResolved,
) -> None:
    subject = st.text_input("Asunto", value=_DEFAULT_SUBJECT, key="email_subject")
    body = st.text_area("Cuerpo", value=_DEFAULT_BODY, height=220, key="email_body")

    invalid = validate_placeholders(subject + "\n" + body)
    if invalid:
        st.error("Placeholders no válidos: " + ", ".join(invalid))

    if selected_ids:
        preview_row = contacts[contacts["contact_id"] == selected_ids[0]]
        if not preview_row.empty:
            preview_contact = preview_row.iloc[0].to_dict()
            with st.expander("Vista previa (primer contacto seleccionado)", expanded=True):
                st.caption(f"**Asunto:** {render_template(subject, preview_contact)}")
                st.text(render_template(body, preview_contact))

    # --- Seguimiento comercial (histórico Acciones) ---
    st.markdown("---")
    opts_persona = [""] + list(PERSONA_COMERCIAL_OPCIONES)
    opts_clas = list(EMAIL_CLASIFICACION_OPCIONES)
    update_seg = st.checkbox(
        "Registrar seguimiento comercial (histórico) para contactos con envío OK",
        key="email_update_seguimiento",
    )
    if update_seg:
        st.selectbox(
            "Clasificación del email",
            opts_clas,
            index=1 if "seguimiento" in opts_clas else 0,
            key=_KEY_SEG_EMAIL_CLAS,
        )
        st.text_input("URL del correo (opcional)", key=_KEY_SEG_EMAIL_URL)
        st.text_area("Resumen / de qué se habló", key=_KEY_SEG_NOTAS, height=80, placeholder="Asunto o notas del envío")
        st.markdown("**Próxima acción pendiente** (opcional)")
        p1, p2 = st.columns(2, gap="small")
        p1.text_input("Fecha próxima acción (dd/mm/aaaa)", key=_KEY_SEG_PROX_FECHA)
        p2.selectbox("Persona próxima acción", opts_persona, key=_KEY_SEG_PERSONA_PROX)
        p3, p4 = st.columns(2, gap="small")
        p3.selectbox(
            "Canal próxima acción",
            [""] + ["email", "llamada", "en_persona"],
            key=_KEY_SEG_PROX_CANAL,
        )
        p4.text_area("Detalle próxima acción", key=_KEY_SEG_PROX_DETALLE, height=60)
        prox_fecha_val = st.session_state.get(_KEY_SEG_PROX_FECHA, "").strip()
        if prox_fecha_val and not is_valid_dd_mm_yyyy(prox_fecha_val):
            st.warning("Fecha próxima acción no válida — usa dd/mm/aaaa.")

    # --- Send button ---
    st.markdown("---")
    n = len(selected_ids)
    label = f"Enviar emails ({n})" if n else "Enviar emails"
    if st.button(label, disabled=(bool(invalid) or n == 0), type="primary", width="stretch"):
        with st.spinner("Enviando emails y actualizando seguimiento…"):
            _do_send(contacts, df_raw, selected_ids, subject, body, smtp_detail)


def _email_actor_name() -> str:
    uid = auth.get_authenticated_user_id()
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    for u in users:
        if u.employee_id == uid:
            return u.nombre
    return uid


def _do_send(
    contacts: pd.DataFrame,
    df_raw: pd.DataFrame,
    selected_ids: list[str],
    subject: str,
    body: str,
    smtp_detail: SmtpResolved,
) -> None:
    from datetime import date, datetime

    update_seg: bool = st.session_state.get("email_update_seguimiento", False)
    actor = _email_actor_name()
    now = datetime.now()
    fecha_hoy = date.today().strftime("%d/%m/%Y")
    hora_ahora = now.strftime("%H:%M")

    if update_seg:
        sample_row = {
            "resultado_contacto": "exitoso",
            "fecha_contacto": fecha_hoy,
            "hora_contacto": hora_ahora,
            "persona_contacto": actor,
            "canal_contacto": "email",
            "email_url": str(st.session_state.get(_KEY_SEG_EMAIL_URL, "") or "").strip(),
            "email_clasificacion": str(st.session_state.get(_KEY_SEG_EMAIL_CLAS, "") or "seguimiento"),
            "notas_contacto": str(st.session_state.get(_KEY_SEG_NOTAS, "") or subject).strip(),
            "proxima_accion_fecha": str(st.session_state.get(_KEY_SEG_PROX_FECHA, "") or "").strip(),
            "proxima_accion_persona": str(st.session_state.get(_KEY_SEG_PERSONA_PROX, "") or "").strip(),
            "proxima_accion_canal": str(st.session_state.get(_KEY_SEG_PROX_CANAL, "") or "").strip(),
            "proxima_accion_detalle": str(st.session_state.get(_KEY_SEG_PROX_DETALLE, "") or "").strip(),
            "origen_registro": "email_batch",
        }
        validation_error = validate_commercial_action_values(sample_row)
        if validation_error:
            st.error(validation_error)
            return

    delivery = smtp_detail.delivery

    # ---- Send loop ----
    sent_ids: list[str] = []
    send_errors: list[str] = []
    for cid in selected_ids:
        row = contacts[contacts["contact_id"] == cid]
        if row.empty:
            continue
        contact = row.iloc[0].to_dict()
        to = contact.get("correo", "")
        if not to:
            continue
        try:
            send_email(
                to,
                render_template(subject, contact),
                render_template(body, contact),
                delivery=delivery,
            )
            sent_ids.append(cid)
        except Exception as exc:
            friendly = smtp_exception_user_message(
                exc,
                routed_profile_slug=smtp_detail.routed_profile_slug,
            )
            send_errors.append(f"{contact.get('nombre', cid)}: {friendly}")

    if sent_ids:
        st.success(f"Emails enviados: {len(sent_ids)} / {len(selected_ids)} seleccionados.")
    if send_errors:
        st.error("Errores al enviar:\n" + "\n".join(send_errors))

    if not update_seg or not sent_ids:
        return

    hs = history_service()
    ok = 0
    seg_errors: list[str] = []
    notas_base = str(st.session_state.get(_KEY_SEG_NOTAS, "") or subject).strip()
    for cid in sent_ids:
        matches = contacts[contacts["contact_id"].astype(str) == str(cid)]
        nombre_c = str(matches.iloc[0].get("nombre", cid)) if not matches.empty else cid
        row = {
            "contact_id": cid,
            "nombre_cliente": nombre_c,
            "resultado_contacto": "exitoso",
            "fecha_contacto": fecha_hoy,
            "hora_contacto": hora_ahora,
            "persona_contacto": actor,
            "canal_contacto": "email",
            "email_url": str(st.session_state.get(_KEY_SEG_EMAIL_URL, "") or "").strip(),
            "email_clasificacion": str(st.session_state.get(_KEY_SEG_EMAIL_CLAS, "") or "seguimiento"),
            "notas_contacto": notas_base,
            "proxima_accion_fecha": str(st.session_state.get(_KEY_SEG_PROX_FECHA, "") or "").strip(),
            "proxima_accion_persona": str(st.session_state.get(_KEY_SEG_PERSONA_PROX, "") or "").strip(),
            "proxima_accion_canal": str(st.session_state.get(_KEY_SEG_PROX_CANAL, "") or "").strip(),
            "proxima_accion_detalle": str(st.session_state.get(_KEY_SEG_PROX_DETALLE, "") or "").strip(),
            "origen_registro": "email_batch",
        }
        try:
            hs.add_row("seguimiento_comercial", row)
            ok += 1
        except Exception as exc:
            seg_errors.append(f"{nombre_c}: {exc}")

    bump_history_cache()
    if ok:
        st.success(f"Histórico de seguimiento registrado para {ok} contacto(s).")
    if seg_errors:
        st.error("Errores al registrar seguimiento:\n" + "\n".join(seg_errors))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_EMAIL_PORTAL_UID_KEY = "_email_portal_unlocked_uid"


def _render_email_password_gate() -> bool:
    """Return True when the current user has confirmed their CRM password for this visit."""
    uid = auth.get_authenticated_user_id()
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    me = next((u for u in users if u.employee_id == uid), None)
    if me is None:
        st.error("No se encontró tu usuario en «Usuarios CRM».")
        return False

    if st.session_state.get(_EMAIL_PORTAL_UID_KEY) == uid:
        return True

    st.info(
        "Introduce la **misma contraseña** que en la hoja «Usuarios CRM» para este usuario. "
        "Así se confirma que eres tú y el envío usará el buzón SMTP que te corresponde (Jiajun / Kabir / …)."
    )
    with st.form("email_portal_password", clear_on_submit=False):
        pw = st.text_input("Contraseña de Usuarios CRM", type="password", key="_email_portal_pw_input")
        submitted = st.form_submit_button("Desbloquear envío de emails", width="stretch")
    if submitted:
        if pw == me.password:
            st.session_state[_EMAIL_PORTAL_UID_KEY] = uid
            st.session_state.pop("login_error", None)
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    return False


def render(df: pd.DataFrame) -> None:
    st.title(page_menu_title("Email"))
    if df.empty:
        st.info("No hay contactos cargados.")
        return

    if not _render_email_password_gate():
        return

    uid = auth.get_authenticated_user_id()
    actor_nombre = ""
    app_role = ""
    for u in load_users_cached(st.session_state.get("users_cache_version", 0)):
        if u.employee_id == uid:
            actor_nombre = u.nombre
            app_role = u.role
            break
    smtp_detail = resolve_smtp_detail(
        employee_id=uid, nombre=actor_nombre, app_role=app_role
    )

    if not smtp_detail.profile_complete:
        if smtp_detail.routed_profile_slug:
            slug = smtp_detail.routed_profile_slug
            st.error(
                f"No se pueden enviar correos: tu usuario está enlazado al perfil SMTP «{slug}» (por ejemplo "
                f"la cuenta de correo de **{actor_nombre or uid}**), pero ese perfil **no está bien configurado** "
                "o falta en secrets / `.env` (host, usuario SMTP, contraseña de aplicación)."
            )
        elif normalize_role(app_role) == ROLE_SALES:
            st.error(
                "No se pueden enviar correos: con rol **sales** hace falta una **ruta SMTP propia** para tu usuario. "
                f"Tu `employee_id` en «Usuarios CRM» es **`{uid}`**; en `.env`/secretos debe existir "
                f"`SMTP_ROUTE_BY_EMPLOYEE_{uid}=kabir` (o el perfil que corresponda) "
                "y además el bloque `SMTP_PROFILE_KABIR_*` / `[smtp_profiles.kabir]` con usuario y contraseña. "
                "Si el `employee_id` no coincide con `EMP002` de tu `.env`, la app no te asigna Kabir y antes "
                "podía caer en el SMTP global (p. ej. Jiajun)."
            )
        else:
            st.error(
                "No se pueden enviar correos: **SMTP global no configurado** (`SMTP_HOST`, `SMTP_USER`, etc.) "
                "o no tienes ruta a un perfil (`SMTP_ROUTE_BY_EMPLOYEE_…` / `[smtp_route_by_*]`)."
            )
        return

    _ensure_state()

    contacts = df.fillna("").astype(str)

    left, right = st.columns([0.42, 0.58], gap="large")

    with left:
        st.subheader("Contactos")
        _render_filter_bar(contacts)
        filtered = _apply_filters(contacts)
        _render_contact_table(filtered)

    selected_ids = sorted(
        cid for cid in st.session_state[_KEY_SELECTED]
        if cid in contacts["contact_id"].values
    )

    with right:
        st.subheader("Plantilla")
        if smtp_detail.routed_profile_slug:
            st.caption(
                f"Enviando como **{smtp_detail.delivery.user}** (perfil «{smtp_detail.routed_profile_slug}»)."
            )
        _render_template_editor(contacts, df, selected_ids, smtp_detail)
