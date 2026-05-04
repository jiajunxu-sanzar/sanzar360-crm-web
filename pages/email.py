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
from app.cache import sheets_service, load_users_cached
from app.state import bump_contacts_cache
from config.settings import (
    CONTACT_ESTADO_OPCIONES,
    PERSONA_COMERCIAL_OPCIONES,
)
from services.activity_log import append_activity
from services.contact_use_cases import save_contact_by_id
from services.email_service import render_template, send_email, validate_placeholders
from services.sheet_date_format import is_valid_dd_mm_yyyy
from ui.components.tables import filter_dataframe

# ---------------------------------------------------------------------------
# Session-state keys (all prefixed "email_" to avoid collisions)
# ---------------------------------------------------------------------------
_KEY_SELECTED = "email_selected_ids"    # set[str] — contact_ids selected in table
_KEY_FILTERS_OPEN = "email_filters_open"

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
    if col_toggle.button("⏬", key="email_toggle_filters", use_container_width=True, help="Filtros"):
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
    if ca.button("Seleccionar todos", use_container_width=True, key="email_select_all"):
        st.session_state[_KEY_SELECTED] = set(ids_with)
        st.rerun()
    if cb.button("Deseleccionar todos", use_container_width=True, key="email_deselect_all"):
        st.session_state[_KEY_SELECTED] = set()
        st.rerun()

    # --- Selectable table: contacts WITH email ---
    if df_with.empty:
        st.info("Ningún contacto visible tiene dirección de correo.")
    else:
        event = st.dataframe(
            _build_display_df(df_with),
            use_container_width=True,
            hide_index=True,
            height=min(400, 36 + len(df_with) * 35),
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
            use_container_width=True,
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

    # --- Seguimiento comercial (before send button) ---
    st.markdown("---")
    opts = [""] + list(PERSONA_COMERCIAL_OPCIONES)
    update_seg = st.checkbox(
        "Actualizar seguimiento comercial para contactos seleccionados",
        key="email_update_seguimiento",
    )
    if update_seg:
        c1, c2 = st.columns(2, gap="small")
        c1.selectbox("Persona último contacto", opts, key="seg_persona_ult")
        c2.text_input("Fecha último contacto (dd/mm/aaaa)", key="seg_fecha_ult")
        c3, c4 = st.columns(2, gap="small")
        c3.text_input("Fecha próxima acción (dd/mm/aaaa)", key="seg_prox_fecha")
        c4.selectbox("Persona próxima acción", opts, key="seg_persona_prox")
        st.text_area("Detalle próxima acción", key="seg_prox_detalle", height=80)

        # Inline date validation feedback (non-blocking, so user can still hit send)
        fecha_ult_val = st.session_state.get("seg_fecha_ult", "").strip()
        prox_fecha_val = st.session_state.get("seg_prox_fecha", "").strip()
        if fecha_ult_val and not is_valid_dd_mm_yyyy(fecha_ult_val):
            st.warning("Fecha último contacto no válida — usa dd/mm/aaaa.")
        if prox_fecha_val and not is_valid_dd_mm_yyyy(prox_fecha_val):
            st.warning("Fecha próxima acción no válida — usa dd/mm/aaaa.")

    # --- Send button ---
    st.markdown("---")
    n = len(selected_ids)
    label = f"Enviar emails ({n})" if n else "Enviar emails"
    if st.button(label, disabled=(bool(invalid) or n == 0), type="primary", use_container_width=True):
        with st.spinner("Enviando emails y actualizando seguimiento…"):
            _do_send(contacts, df_raw, selected_ids, subject, body)


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
) -> None:
    update_seg: bool = st.session_state.get("email_update_seguimiento", False)

    # Validate seguimiento dates before sending anything
    if update_seg:
        fecha_ult = st.session_state.get("seg_fecha_ult", "").strip()
        prox_fecha = st.session_state.get("seg_prox_fecha", "").strip()
        if fecha_ult and not is_valid_dd_mm_yyyy(fecha_ult):
            st.error("Fecha último contacto no válida. Corrige antes de enviar.")
            return
        if prox_fecha and not is_valid_dd_mm_yyyy(prox_fecha):
            st.error("Fecha próxima acción no válida. Corrige antes de enviar.")
            return

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
            send_email(to, render_template(subject, contact), render_template(body, contact))
            sent_ids.append(cid)
        except Exception as exc:
            send_errors.append(f"{contact.get('nombre', cid)}: {exc}")

    if sent_ids:
        st.success(f"Emails enviados: {len(sent_ids)} / {len(selected_ids)} seleccionados.")
    if send_errors:
        st.error("Errores al enviar:\n" + "\n".join(send_errors))

    if not update_seg or not sent_ids:
        return

    # ---- Bulk seguimiento update ----
    patch: dict[str, str] = {}
    persona_ult = st.session_state.get("seg_persona_ult", "")
    fecha_ult   = st.session_state.get("seg_fecha_ult", "").strip()
    prox_fecha  = st.session_state.get("seg_prox_fecha", "").strip()
    persona_prox = st.session_state.get("seg_persona_prox", "")
    prox_detalle = st.session_state.get("seg_prox_detalle", "").strip()

    if persona_ult:   patch["persona_ultimo_contacto"] = persona_ult
    if fecha_ult:     patch["fecha_ultimo_contacto"]   = fecha_ult
    if prox_fecha:    patch["proxima_accion_fecha"]     = prox_fecha
    if persona_prox:  patch["persona_proxima_accion"]   = persona_prox
    if prox_detalle:  patch["proxima_accion_detalle"]   = prox_detalle

    if not patch:
        return

    sheets = sheets_service()
    updated_df = df_raw.copy()
    ok = 0
    seg_errors: list[str] = []
    for cid in sent_ids:
        matches = updated_df[updated_df["contact_id"].astype(str) == str(cid)]
        if matches.empty:
            seg_errors.append(f"{cid}: no encontrado")
            continue
        row_idx = int(matches.index[0])
        contact_vals = matches.iloc[0].fillna("").astype(str).to_dict()
        contact_vals.update(patch)
        try:
            updated_df = save_contact_by_id(
                updated_df,
                row_idx=row_idx,
                contact_id=cid,
                values=contact_vals,
                sheets=sheets,
            )
            ok += 1
        except Exception as exc:
            seg_errors.append(f"{cid}: {exc}")

    bump_contacts_cache()
    if ok:
        st.success(f"Seguimiento comercial actualizado en {ok} contacto(s).")
        actor = _email_actor_name()
        for cid in sent_ids:
            matches = df_raw[df_raw["contact_id"].astype(str) == str(cid)]
            nombre_c = matches.iloc[0].get("nombre", cid) if not matches.empty else cid
            append_activity(
                sheets_service(),
                contact_id=cid,
                nombre_contacto=str(nombre_c),
                tipo_accion="batch email",
                detalle="email enviado + seguimiento comercial actualizado",
                persona=actor,
            )
    if seg_errors:
        st.error("Errores en seguimiento:\n" + "\n".join(seg_errors))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render(df: pd.DataFrame) -> None:
    st.title("Email")
    if df.empty:
        st.info("No hay contactos cargados.")
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
        _render_template_editor(contacts, df, selected_ids)
