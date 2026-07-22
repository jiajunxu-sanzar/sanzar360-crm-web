"""Email page: envío individual y newsletter.

Layout (ambos modos)
---------------------
Left panel  (42 %): search + filters, all-contacts table with multi-row
                    selection, select-all / deselect-all buttons.
Right panel (58 %): editor del modo activo (plantilla individual, o bloque
                    de newsletter) + vista previa + botón de envío.

Modo "Newsletter": bloque único (imagen de cabecera, título, párrafo, texto
con enlace), con el logo de Sanzar y el botón de baja añadidos
automáticamente. Vista previa en pantalla, envío de prueba a una lista interna
fija, y envío masivo que excluye automáticamente a quien se haya dado de baja.
"""
from __future__ import annotations

import json
import uuid

import pandas as pd
import streamlit as st

from app import auth
from app.cache import blogs_service, history_service, load_users_cached
from ui.components.page_header import render_page_header
from app.smtp_profiles import (
    NEWSLETTER_SMTP_PROFILE_SLUG,
    SmtpResolved,
    resolve_smtp_detail,
    resolve_smtp_profile,
)
from app.state import bump_blogs_cache, bump_contacts_cache, bump_history_cache, set_contacts_df_override
from config.settings import (
    CONTACT_ESTADO_OPCIONES,
    EMAIL_CLASIFICACION_OPCIONES,
    NEWSLETTER_NOTIFY_EMAIL,
    NEWSLETTER_TEST_RECIPIENTS_DEFAULT,
)
from services.commercial_action_validation import validate_commercial_action_values
from services.email_service import (
    render_template,
    send_email,
    send_html_email,
    smtp_exception_user_message,
    validate_placeholders,
)
from services.newsletter_service import (
    NewsletterContent,
    TEST_CONTACT_ID,
    TEST_NEWSLETTER_ID,
    build_unsubscribe_url,
    data_uri,
    image_mime_subtype,
    is_newsletter_subscribed,
    load_linkedin_icon_bytes,
    load_logo_bytes,
    load_web_icon_bytes,
    public_base_url_configured,
    render_newsletter_html,
)
from services.sheet_date_format import is_valid_dd_mm_yyyy
from services.users_service import person_select_options
from ui.components.tables import filter_dataframe

# ---------------------------------------------------------------------------
# Session-state keys (all prefixed "email_" to avoid collisions)
# ---------------------------------------------------------------------------
_KEY_MODE = "email_mode"
_MODE_INDIVIDUAL = "Correo individual"
_MODE_NEWSLETTER = "Newsletter"

_KEY_SELECTED = "email_selected_ids"    # set[str] — contact_ids selected in table (modo individual)
_KEY_SELECTED_NEWSLETTER = "newsletter_selected_ids"  # set[str] — modo newsletter
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

_KEY_NL_ASUNTO = "newsletter_asunto"
_KEY_NL_TITULO = "newsletter_titulo"
_KEY_NL_PARRAFO = "newsletter_parrafo"
_KEY_NL_CTA_TEXTO = "newsletter_cta_texto"
_KEY_NL_CTA_URL = "newsletter_cta_url"
_KEY_NL_TEST_RECIPIENTS = "newsletter_test_recipients"
_KEY_NL_IMAGE_UPLOAD = "newsletter_image_upload"
_KEY_NL_SHOW_PREVIEW = "_newsletter_show_preview"
_KEY_NL_CONFIRM_OPEN = "_newsletter_confirm_open"
_KEY_NL_DRAFT_ID = "newsletter_planned_draft_id"
_KEY_NL_DRAFT_PREFILL_DONE = "_newsletter_draft_prefill_done"


def _ensure_state() -> None:
    defaults = {
        _KEY_SELECTED: set(),
        _KEY_SELECTED_NEWSLETTER: set(),
        _KEY_FILTERS_OPEN: False,
        _KEY_MODE: _MODE_INDIVIDUAL,
        _KEY_NL_ASUNTO: "",
        _KEY_NL_TITULO: "",
        _KEY_NL_PARRAFO: "",
        _KEY_NL_CTA_TEXTO: "",
        _KEY_NL_CTA_URL: "",
        _KEY_NL_TEST_RECIPIENTS: NEWSLETTER_TEST_RECIPIENTS_DEFAULT,
        _KEY_NL_SHOW_PREVIEW: False,
        _KEY_NL_DRAFT_ID: "",
        _KEY_NL_DRAFT_PREFILL_DONE: "",
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


def _newsletter_eligible_mask(filtered: pd.DataFrame) -> pd.Series:
    if filtered.empty:
        return pd.Series(dtype=bool)
    return filtered.apply(lambda row: is_newsletter_subscribed(row.to_dict()), axis=1)


def _render_contact_table(filtered: pd.DataFrame, *, mode: str = "individual") -> None:
    """Render the selectable contact table and keep the selection state in sync.

    Contactos elegibles   → selectable st.dataframe (multi-row).
    Contactos NO elegibles → read-only st.dataframe styled in grey below it.

    En modo "individual" son elegibles los contactos con correo. En modo
    "newsletter" además se excluyen (en gris, no seleccionables) los que se
    hayan dado de baja (``newsletter_suscrito == "no"``), para que nadie los
    seleccione por error.
    """
    is_newsletter = mode == "newsletter"
    selected_key = _KEY_SELECTED_NEWSLETTER if is_newsletter else _KEY_SELECTED
    table_key = f"email_contact_table_{mode}"

    has_email_mask = filtered["correo"].fillna("").astype(str).str.strip().ne("")
    eligible_mask = has_email_mask
    if is_newsletter:
        eligible_mask = has_email_mask & _newsletter_eligible_mask(filtered)

    df_with    = filtered[eligible_mask].reset_index(drop=True)
    df_without = filtered[~eligible_mask].reset_index(drop=True)

    ids_with = df_with["contact_id"].tolist()

    # --- Select-all / deselect-all ---
    ca, cb = st.columns(2, gap="small")
    if ca.button("Seleccionar todos", width="stretch", key=f"{table_key}_select_all"):
        st.session_state[selected_key] = set(ids_with)
        st.rerun()
    if cb.button("Deseleccionar todos", width="stretch", key=f"{table_key}_deselect_all"):
        st.session_state[selected_key] = set()
        st.rerun()

    # --- Selectable table: contactos elegibles ---
    if df_with.empty:
        st.info("Ningún contacto visible es seleccionable con los filtros actuales.")
    else:
        event = st.dataframe(
            _build_display_df(df_with),
            width="stretch",
            hide_index=True,
            height=min(420, 36 + len(df_with) * 35),
            key=table_key,
            on_select="rerun",
            selection_mode="multi-row",
        )

        raw_positions: list[int] = (
            list(event.selection.rows)
            if event and hasattr(event, "selection") and event.selection
            else []
        )
        # Update selection: keep previously-selected that are outside current filter + new picks
        all_visible  = set(filtered["contact_id"].tolist())
        preserved = {
            cid for cid in st.session_state[selected_key]
            if cid not in all_visible          # outside current filter → keep
        }
        newly_selected = {
            ids_with[pos]
            for pos in raw_positions
            if 0 <= pos < len(ids_with)
        }
        if event:  # table rendered → sync (don't overwrite on first render without interaction)
            st.session_state[selected_key] = preserved | newly_selected

    # --- Static greyed-out table: contactos NO elegibles ---
    if not df_without.empty:
        caption = (
            "Sin correo o dado de baja de la newsletter — no seleccionables"
            if is_newsletter
            else "Sin correo — no seleccionables"
        )
        st.caption(f"{caption} ({len(df_without)})")
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

    n_sel = len(st.session_state[selected_key])
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
    with st.container(border=True):
        st.markdown("##### Plantilla")
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

    with st.container(border=True):
        st.markdown("##### Seguimiento")
        opts_persona = person_select_options(load_users_cached(st.session_state.get("users_cache_version", 0)))
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

    with st.container(border=True):
        st.markdown("##### Envío")
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
# Newsletter: editor de bloque único + vista previa + prueba + envío
# ---------------------------------------------------------------------------

def _parse_email_list(raw: str) -> list[str]:
    parts = [p.strip() for p in str(raw or "").replace(",", ";").split(";")]
    return [p for p in parts if p and "@" in p]


def _newsletter_content_from_state() -> NewsletterContent:
    return NewsletterContent(
        asunto=str(st.session_state.get(_KEY_NL_ASUNTO, "") or ""),
        titulo=str(st.session_state.get(_KEY_NL_TITULO, "") or ""),
        parrafo=str(st.session_state.get(_KEY_NL_PARRAFO, "") or ""),
        cta_texto=str(st.session_state.get(_KEY_NL_CTA_TEXTO, "") or ""),
        cta_url=str(st.session_state.get(_KEY_NL_CTA_URL, "") or ""),
    )


def _newsletter_email_subject(content: NewsletterContent) -> str:
    return str(content.asunto or content.titulo or "Newsletter").strip() or "Newsletter"


def _hero_image_bytes_and_subtype(uploaded_file: object) -> tuple[bytes, str] | None:
    if uploaded_file is None:
        return None
    data = uploaded_file.getvalue()
    if not data:
        return None
    subtype = image_mime_subtype(uploaded_file.name)
    return data, subtype


def _do_send_newsletter_test(
    content: NewsletterContent,
    hero: tuple[bytes, str] | None,
    smtp_detail: SmtpResolved,
) -> None:
    recipients = _parse_email_list(st.session_state.get(_KEY_NL_TEST_RECIPIENTS, ""))
    if not recipients:
        st.error("No hay ninguna dirección de prueba válida (usa ; para separar varias).")
        return

    inline_images: dict[str, tuple[bytes, str]] = {
        "logo": (load_logo_bytes(), "png"),
        "icon_web": (load_web_icon_bytes(), "png"),
        "icon_linkedin": (load_linkedin_icon_bytes(), "png"),
    }
    hero_src = None
    if hero:
        inline_images["hero"] = hero
        hero_src = "cid:hero"
    unsubscribe_url = build_unsubscribe_url(TEST_CONTACT_ID, TEST_NEWSLETTER_ID)
    html = render_newsletter_html(
        content,
        logo_src="cid:logo",
        hero_src=hero_src,
        unsubscribe_url=unsubscribe_url,
        icon_web_src="cid:icon_web",
        icon_linkedin_src="cid:icon_linkedin",
    )

    sent, errors = 0, []
    for to in recipients:
        try:
            send_html_email(
                to,
                f"[PRUEBA] {_newsletter_email_subject(content)}",
                html,
                inline_images=inline_images,
                delivery=smtp_detail.delivery,
            )
            sent += 1
        except Exception as exc:
            friendly = smtp_exception_user_message(exc, routed_profile_slug=smtp_detail.routed_profile_slug)
            errors.append(f"{to}: {friendly}")

    if sent:
        st.success(f"Prueba enviada a {sent}/{len(recipients)} direcciones.")
    if errors:
        st.error("Errores en el envío de prueba:\n" + "\n".join(errors))


def _do_send_newsletter(
    contacts: pd.DataFrame,
    selected_ids: list[str],
    content: NewsletterContent,
    hero: tuple[bytes, str] | None,
    smtp_detail: SmtpResolved,
    *,
    newsletter_id: str | None = None,
) -> None:
    actor = _email_actor_name()
    planned_id = str(newsletter_id or "").strip()
    newsletter_id = planned_id or str(uuid.uuid4())
    logo_bytes = load_logo_bytes()
    hero_src = "cid:hero" if hero else None

    sent_records: list[dict[str, str]] = []
    send_errors: list[str] = []
    for cid in selected_ids:
        row = contacts[contacts["contact_id"] == cid]
        if row.empty:
            continue
        contact = row.iloc[0].to_dict()
        to = contact.get("correo", "")
        if not to:
            continue
        if not is_newsletter_subscribed(contact):
            # Doble comprobación de seguridad: la tabla ya los excluye, pero por
            # si acaso alguien quedó seleccionado antes de darse de baja.
            continue

        inline_images: dict[str, tuple[bytes, str]] = {
            "logo": (logo_bytes, "png"),
            "icon_web": (load_web_icon_bytes(), "png"),
            "icon_linkedin": (load_linkedin_icon_bytes(), "png"),
        }
        if hero:
            inline_images["hero"] = hero
        unsubscribe_url = build_unsubscribe_url(cid, newsletter_id)
        html = render_newsletter_html(
            content,
            logo_src="cid:logo",
            hero_src=hero_src,
            unsubscribe_url=unsubscribe_url,
            icon_web_src="cid:icon_web",
            icon_linkedin_src="cid:icon_linkedin",
        )
        try:
            send_html_email(
                to,
                _newsletter_email_subject(content),
                html,
                inline_images=inline_images,
                delivery=smtp_detail.delivery,
            )
            sent_records.append(
                {"contact_id": str(cid), "nombre": str(contact.get("nombre", "") or ""), "correo": str(to)}
            )
        except Exception as exc:
            friendly = smtp_exception_user_message(exc, routed_profile_slug=smtp_detail.routed_profile_slug)
            send_errors.append(f"{contact.get('nombre', cid)}: {friendly}")

    if sent_records:
        st.success(f"Newsletter enviada: {len(sent_records)} / {len(selected_ids)} seleccionados.")
    if send_errors:
        st.error("Errores al enviar:\n" + "\n".join(send_errors))

    if sent_records:
        try:
            blogs_service().log_newsletter_send(
                titulo=content.titulo,
                texto=content.parrafo,
                enviado_por=actor,
                destinatarios=sent_records,
                newsletter_id=newsletter_id,
                asunto=content.asunto,
                cta_texto=content.cta_texto,
                cta_url=content.cta_url,
                tiene_imagen=hero is not None,
            )
            bump_blogs_cache()
            st.session_state[_KEY_NL_DRAFT_ID] = ""
            st.session_state[_KEY_NL_DRAFT_PREFILL_DONE] = ""
        except Exception as exc:
            st.warning(f"El envío se realizó pero no se pudo registrar en Blogs: {exc}")


def _render_newsletter_history() -> None:
    try:
        rows = blogs_service().newsletter_rows()
    except Exception:
        return
    if not rows:
        return
    with st.expander(f"Historial de newsletters enviadas ({len(rows)})", expanded=False):
        for row in rows[:20]:
            titulo = str(row.get("titulo", "") or "Newsletter")
            fecha = str(row.get("newsletter_fecha_envio", "") or "—")
            enviado_por = str(row.get("newsletter_enviado_por", "") or "—")
            num_dest = str(row.get("newsletter_num_destinatarios", "") or "0")
            try:
                num_bajas = len(json.loads(row.get("newsletter_bajas_json", "") or "[]"))
            except (TypeError, ValueError):
                num_bajas = 0
            st.markdown(
                f"**{titulo}** — {fecha} · enviada por {enviado_por} · "
                f"{num_dest} destinatario(s) · {num_bajas} baja(s)"
            )


def _render_newsletter_panel(
    contacts: pd.DataFrame,
    selected_ids: list[str],
    smtp_detail: SmtpResolved,
) -> None:
    with st.container(border=True):
        st.markdown("##### Planning (Blogs)")
        draft_rows: list[dict[str, str]] = []
        try:
            draft_rows = blogs_service().newsletter_draft_rows()
        except Exception:
            draft_rows = []
        options = [""] + [
            str(r.get("historial_blog_id", "") or "").strip()
            for r in draft_rows
            if str(r.get("historial_blog_id", "") or "").strip()
        ]
        labels = {
            "": "Ninguna (envío nuevo)",
            **{
                str(r.get("historial_blog_id", "") or "").strip(): (
                    f"{str(r.get('titulo', '') or 'Newsletter').strip()} · "
                    f"prevista {str(r.get('fecha_publicacion_prevista', '') or '—').strip() or '—'}"
                )
                for r in draft_rows
                if str(r.get("historial_blog_id", "") or "").strip()
            },
        }
        selected_draft = st.selectbox(
            "Newsletter planificada (opcional)",
            options,
            key=_KEY_NL_DRAFT_ID,
            format_func=lambda x: labels.get(x, x),
            help="Si eliges un borrador de Blogs, al enviar se actualizará esa misma fila en HistorialBlog.",
        )
        if selected_draft:
            draft = next(
                (r for r in draft_rows if str(r.get("historial_blog_id", "") or "").strip() == selected_draft),
                None,
            )
            if draft is not None:
                draft_titulo = str(draft.get("titulo", "") or "").strip()
                prefill_for = str(st.session_state.get(_KEY_NL_DRAFT_PREFILL_DONE, "") or "")
                if draft_titulo and prefill_for != selected_draft:
                    if not str(st.session_state.get(_KEY_NL_TITULO, "") or "").strip():
                        st.session_state[_KEY_NL_TITULO] = draft_titulo
                    st.session_state[_KEY_NL_DRAFT_PREFILL_DONE] = selected_draft
                st.caption(
                    f"Se actualizará el planning «{draft_titulo or selected_draft[:8]}» "
                    f"(id `{selected_draft[:8]}…`)."
                )
        else:
            st.session_state[_KEY_NL_DRAFT_PREFILL_DONE] = ""

    with st.container(border=True):
        st.markdown("##### Contenido")
        st.text_input(
            "Asunto del email",
            key=_KEY_NL_ASUNTO,
            placeholder="Novedades Sanzar · verano 2026",
            help="Texto que aparece en la bandeja de entrada del destinatario.",
        )
        st.text_input(
            "Título de la newsletter",
            key=_KEY_NL_TITULO,
            placeholder="Un verano sobre ruedas",
            help="Título grande (H1) dentro del cuerpo del correo.",
        )
        uploaded = st.file_uploader(
            "Imagen de cabecera (opcional)", type=["png", "jpg", "jpeg"], key=_KEY_NL_IMAGE_UPLOAD
        )
        st.text_area("Párrafo", key=_KEY_NL_PARRAFO, height=140, placeholder="Cuéntales la novedad...")
        st.caption(
            "Formato: `**negrita**`, `++subrayado++`, `[texto](https://enlace.com)`. "
            "Los saltos de línea se respetan."
        )
        c1, c2 = st.columns(2, gap="small")
        c1.text_input("Texto del botón/enlace (opcional)", key=_KEY_NL_CTA_TEXTO, placeholder="Ver más")
        c2.text_input("URL del enlace", key=_KEY_NL_CTA_URL, placeholder="https://...")

        cta_texto = str(st.session_state.get(_KEY_NL_CTA_TEXTO, "") or "").strip()
        cta_url = str(st.session_state.get(_KEY_NL_CTA_URL, "") or "").strip()
        cta_mismatch = bool(cta_texto) != bool(cta_url)
        if cta_mismatch:
            st.warning("El texto y la URL del botón deben rellenarse los dos juntos, o dejarse los dos vacíos.")

        if not public_base_url_configured():
            st.warning(
                "Falta configurar `APP_PUBLIC_URL` (la URL pública de esta app desplegada) en secrets/.env. "
                "Sin ella, el botón de baja no puede ser una página de un clic: los correos mostrarán en su "
                f"lugar un contacto directo a {NEWSLETTER_NOTIFY_EMAIL}."
            )

        hero = _hero_image_bytes_and_subtype(uploaded)
        content = _newsletter_content_from_state()
        content_ok = bool(content.asunto.strip()) and bool(content.titulo.strip())
        can_send = content_ok and not cta_mismatch
        planned_id = str(st.session_state.get(_KEY_NL_DRAFT_ID, "") or "").strip()

        if st.button("Vista previa", width="stretch", disabled=not content_ok):
            st.session_state[_KEY_NL_SHOW_PREVIEW] = True
        if st.session_state.get(_KEY_NL_SHOW_PREVIEW) and content_ok:
            logo_src = data_uri(load_logo_bytes(), "png")
            hero_src = data_uri(*hero) if hero else None
            preview_html = render_newsletter_html(
                content,
                logo_src=logo_src,
                hero_src=hero_src,
                unsubscribe_url=build_unsubscribe_url(TEST_CONTACT_ID, TEST_NEWSLETTER_ID) or "#",
                icon_web_src=data_uri(load_web_icon_bytes(), "png"),
                icon_linkedin_src=data_uri(load_linkedin_icon_bytes(), "png"),
            )
            with st.expander("Vista previa del correo", expanded=True):
                st.caption(f"**Asunto:** {_newsletter_email_subject(content)}")
                st.components.v1.html(preview_html, height=650, scrolling=True)

    with st.container(border=True):
        st.markdown("##### Prueba")
        st.text_input(
            "Enviarme una prueba a (direcciones separadas por ;)",
            key=_KEY_NL_TEST_RECIPIENTS,
        )
        if st.button("Enviarme una prueba", width="stretch", disabled=not can_send):
            with st.spinner("Enviando prueba…"):
                _do_send_newsletter_test(content, hero, smtp_detail)

    with st.container(border=True):
        st.markdown("##### Envío")
        n = len(selected_ids)
        label = f"Enviar newsletter ({n})" if n else "Enviar newsletter"
        if st.button(label, type="primary", width="stretch", disabled=(n == 0 or not can_send)):
            st.session_state[_KEY_NL_CONFIRM_OPEN] = True
        if st.session_state.get(_KEY_NL_CONFIRM_OPEN):
            _newsletter_confirm_send_dialog(
                contacts, selected_ids, content, hero, smtp_detail, newsletter_id=planned_id or None
            )
        _render_newsletter_history()


@st.dialog("Confirmar envío de newsletter")
def _newsletter_confirm_send_dialog(
    contacts: pd.DataFrame,
    selected_ids: list[str],
    content: NewsletterContent,
    hero: tuple[bytes, str] | None,
    smtp_detail: SmtpResolved,
    *,
    newsletter_id: str | None = None,
) -> None:
    n = len(selected_ids)
    st.markdown(
        f"Vas a enviar la newsletter a **{n}** contacto(s) desde "
        f"**{smtp_detail.delivery.user}**."
    )
    st.markdown(f"**Asunto:** {_newsletter_email_subject(content)}")
    if newsletter_id:
        st.caption(f"Se actualizará la fila planificada `{newsletter_id[:8]}…` en HistorialBlog.")
    else:
        st.caption("Se creará una fila nueva en HistorialBlog.")
    st.caption("Revisa que los destinatarios y el contenido sean correctos antes de confirmar.")
    c1, c2 = st.columns(2)
    if c1.button("Confirmar envío", type="primary", width="stretch", key="nl_confirm_yes"):
        st.session_state.pop(_KEY_NL_CONFIRM_OPEN, None)
        with st.spinner("Enviando newsletter…"):
            _do_send_newsletter(
                contacts,
                selected_ids,
                content,
                hero,
                smtp_detail,
                newsletter_id=newsletter_id,
            )
        st.rerun()
    if c2.button("Cancelar", width="stretch", key="nl_confirm_no"):
        st.session_state.pop(_KEY_NL_CONFIRM_OPEN, None)
        st.rerun()


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
        "Así se confirma que eres tú antes de usar el envío de correos."
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
    render_page_header("Email")
    if df.empty:
        st.info("No hay contactos cargados.")
        return

    if not _render_email_password_gate():
        return

    st.warning(
        "Esta funcionalidad debe usarse con cuidado. "
        "No envíes correos ni newsletters a destinatarios equivocados."
    )

    uid = auth.get_authenticated_user_id()
    actor_nombre = ""
    app_role = ""
    for u in load_users_cached(st.session_state.get("users_cache_version", 0)):
        if u.employee_id == uid:
            actor_nombre = u.nombre
            app_role = u.role
            break

    user_smtp = resolve_smtp_detail(
        employee_id=uid, nombre=actor_nombre, app_role=app_role
    )
    newsletter_smtp = resolve_smtp_profile(NEWSLETTER_SMTP_PROFILE_SLUG)

    _ensure_state()

    contacts = df.fillna("").astype(str)

    st.radio(
        "Modo",
        [_MODE_INDIVIDUAL, _MODE_NEWSLETTER],
        key=_KEY_MODE,
        horizontal=True,
        label_visibility="collapsed",
    )
    mode = st.session_state[_KEY_MODE]
    is_newsletter = mode == _MODE_NEWSLETTER

    left, right = st.columns([0.42, 0.58], gap="large")

    with left:
        with st.container(border=True):
            st.markdown("##### Contactos")
            _render_filter_bar(contacts)
            filtered = _apply_filters(contacts)
            _render_contact_table(filtered, mode="newsletter" if is_newsletter else "individual")

    selected_key = _KEY_SELECTED_NEWSLETTER if is_newsletter else _KEY_SELECTED
    selected_ids = sorted(
        cid for cid in st.session_state[selected_key]
        if cid in contacts["contact_id"].values
    )

    with right:
        if is_newsletter:
            if not newsletter_smtp.profile_complete:
                st.error(
                    "No se puede enviar la newsletter: falta configurar el perfil SMTP **info** "
                    f"(`SMTP_PROFILE_INFO_*` / `[smtp_profiles.{NEWSLETTER_SMTP_PROFILE_SLUG}]` "
                    "con host, usuario y contraseña de aplicación)."
                )
            else:
                st.caption(
                    f"Enviando como **{newsletter_smtp.delivery.user}** "
                    f"(perfil «{NEWSLETTER_SMTP_PROFILE_SLUG}»)."
                )
                _render_newsletter_panel(contacts, selected_ids, newsletter_smtp)
        else:
            if not user_smtp.profile_complete:
                st.info(
                    "Actualmente no tienes acceso al correo individual. "
                    "Consulta con el administrador para activarlo."
                )
            else:
                if user_smtp.routed_profile_slug:
                    st.caption(
                        f"Enviando como **{user_smtp.delivery.user}** "
                        f"(perfil «{user_smtp.routed_profile_slug}»)."
                    )
                _render_template_editor(contacts, df, selected_ids, user_smtp)
